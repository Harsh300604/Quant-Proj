"""The one wrapper every agent node uses to call Claude (brief section 8).

What it guarantees:
- requests are built from an allow-list of parameters: never ``temperature``, ``top_p`` or
  ``top_k``, never ``tool_choice``; ``max_tokens`` always set; only allowed model IDs;
- structured output: the reply must match a pydantic schema (``output_config.format`` with
  ``anthropic.transform_schema``); it is validated here, and an invalid reply is retried, then
  returned as a failure so the caller can fall back to "no view";
- the stable system prompt carries ``cache_control`` (prompt caching);
- ``stop_reason`` is checked before the content is read (refusal / max_tokens count as failures);
- every response goes into the SQLite response cache (key excludes the API key) and every call,
  hit or miss, into the cost ledger; the ledger refuses a call that could pass a budget stop;
- the SDK retries 429 / 5xx itself with backoff; errors are re-raised without request details,
  so a key can never appear in an exception.

Thinking: ``thinking_off=True`` maps to the setting each model accepts (Sonnet 5.5:
``between_tools``; Haiku 5.5: ``disabled``; Opus 5.5 cannot turn it off, so it is omitted and
effort is the only control). ``thinking_off=False`` omits the parameter (the model's default).
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from quantagents.config import ALLOWED_MODELS, FORBIDDEN_SAMPLING_KEYS, Config
from quantagents.llm.cache import ResponseCache, request_key
from quantagents.llm.ledger import Ledger, Limits
from quantagents.llm.pricing import cost_usd, load_pricing, worst_case_usd
from quantagents.paths import Paths

log = logging.getLogger(__name__)

ALLOWED_REQUEST_KEYS = {"model", "max_tokens", "system", "messages", "output_config", "thinking"}
EFFORTS = ("low", "medium", "high", "xhigh", "max")
SDK_MAX_RETRIES = 4


class LLMError(RuntimeError):
    pass


def thinking_param(model: str, thinking_off: bool, effort: str) -> dict | None:
    if not thinking_off:
        return None
    if model == "claude-sonnet-5-5":
        if EFFORTS.index(effort) > EFFORTS.index("high"):
            raise ValueError("Sonnet 5.5 accepts thinking 'between_tools' only at effort 'high' or below")
        return {"type": "between_tools"}
    if model == "claude-haiku-5-5":
        if EFFORTS.index(effort) > EFFORTS.index("high"):
            raise ValueError("Haiku 5.5 accepts thinking 'disabled' only at effort 'high' or below")
        return {"type": "disabled"}
    return None          # Opus 5.5: thinking cannot be disabled; effort controls depth


def build_request(*, model: str, system: str, user: str | list, schema: type[BaseModel], max_tokens: int,
                  effort: str, thinking_off: bool) -> dict:
    """The exact request body (also the response-cache key). Pure: no network."""
    import anthropic
    if model not in ALLOWED_MODELS:
        raise ValueError(f"model {model!r} is not allowed; use one of {sorted(ALLOWED_MODELS)}")
    if effort not in EFFORTS:
        raise ValueError(f"effort {effort!r} is not one of {EFFORTS}")
    if not (isinstance(max_tokens, int) and max_tokens > 0):
        raise ValueError("max_tokens must be a positive integer")
    content = user if isinstance(user, list) else [{"type": "text", "text": user}]
    req: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": content}],
        "output_config": {"effort": effort,
                          "format": {"type": "json_schema", "schema": anthropic.transform_schema(schema)}},
    }
    t = thinking_param(model, thinking_off, effort)
    if t is not None:
        req["thinking"] = t
    _assert_allowed(req)
    return req


def _assert_allowed(req: dict) -> None:
    extra = set(req) - ALLOWED_REQUEST_KEYS
    if extra:
        raise ValueError(f"request parameters not on the allow-list: {sorted(extra)}")
    bad = (FORBIDDEN_SAMPLING_KEYS | {"tool_choice"}) & set(_all_keys(req))
    if bad:
        raise ValueError(f"forbidden request parameter(s): {sorted(bad)}")


def _all_keys(obj):
    """Every dict key in the request EXCEPT inside the output schema (schemas may name fields freely)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "schema":
                continue
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_keys(v)


def normalise_response(resp) -> dict:
    """SDK Message (or a test double) -> a plain dict we can cache."""
    blocks = getattr(resp, "content", None) or []
    text = next((getattr(b, "text", "") for b in blocks if getattr(b, "type", "") == "text"), "")
    u = getattr(resp, "usage", None)
    usage = {k: int(getattr(u, k, 0) or 0) for k in ("input_tokens", "output_tokens",
                                                     "cache_creation_input_tokens", "cache_read_input_tokens")}
    sd = getattr(resp, "stop_details", None)
    return {"id": getattr(resp, "id", ""), "model": getattr(resp, "model", ""),
            "stop_reason": getattr(resp, "stop_reason", ""), "text": text, "usage": usage,
            "refusal_category": getattr(sd, "category", None) if sd is not None else None}


@dataclass
class CallResult:
    ok: bool
    parsed: BaseModel | None
    attempts: int
    api_calls: int
    cache_hits: int
    usd: float
    usage: dict = field(default_factory=dict)
    error: str = ""


class LLMClient:
    """One per run. ``sdk`` can be injected (tests); otherwise the official SDK client is created
    on first use with the key from .env."""

    def __init__(self, cfg: Config, run_id: str, *, sdk=None, paths: Paths | None = None, variant: str | None = None,
                 limits: Limits | None = None):
        self.cfg = cfg
        self.run_id = run_id
        self.variant = variant or cfg.variant
        self.paths = paths or Paths.from_config(cfg)
        self.cache = ResponseCache(self.paths.response_cache)
        self.ledger = Ledger(self.paths.ledger)
        self.limits = limits or Limits.from_config(cfg)
        self.prices = load_pricing()
        self._sdk = sdk
        # Memo calls run in parallel threads (agent graph): the budget check must count calls that
        # are still in flight, and the counters must not race.
        self._lock = threading.Lock()
        self._in_flight_usd = 0.0
        self.stats = {"api_calls": 0, "cache_hits": 0, "usd": 0.0, "input_tokens": 0, "cache_read_input_tokens": 0,
                      "cache_creation_input_tokens": 0, "output_tokens": 0}

    def _client(self):
        if self._sdk is None:
            import anthropic
            from quantagents.env_secrets import load_secrets
            key = load_secrets().get("ANTHROPIC_API_KEY")
            self._sdk = anthropic.Anthropic(api_key=key, max_retries=SDK_MAX_RETRIES)
        return self._sdk

    def _record(self, node: str, model: str, usage: dict, hit: bool, usd: float) -> None:
        with self._lock:
            self.ledger.record(run_id=self.run_id, node=node, model=model, key_label=self.limits.key_label,
                               stage=self.limits.stage, variant=self.variant, usage=usage, cache_hit=hit, usd=usd,
                               inr_per_usd=self.limits.inr_per_usd)
            self.stats["cache_hits" if hit else "api_calls"] += 1
            self.stats["usd"] += usd
            if not hit:
                for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"):
                    self.stats[k] += int(usage.get(k) or 0)

    def structured(self, *, node: str, model: str, system: str, user: str | list, schema: type[BaseModel],
                   max_tokens: int, effort: str, thinking_off: bool = True, replicate: int = 0,
                   attempts: int = 2) -> CallResult:
        req = build_request(model=model, system=system, user=user, schema=schema, max_tokens=max_tokens,
                            effort=effort, thinking_off=thinking_off)
        result = CallResult(False, None, 0, 0, 0, 0.0)
        for attempt in range(attempts):
            result.attempts = attempt + 1
            key = request_key(req, replicate, attempt)
            resp = self.cache.get(key)
            if resp is not None:
                self._record(node, model, resp["usage"], True, 0.0)
                result.cache_hits += 1
            else:
                est_in = len(json.dumps(req)) // 3 + 50
                worst = worst_case_usd(model, est_in, max_tokens, self.prices)
                with self._lock:      # reserve the worst case until the call is recorded
                    self.ledger.check(self.limits, self.run_id, worst + self._in_flight_usd)
                    self._in_flight_usd += worst
                try:
                    resp = self._call(req)
                    usd = cost_usd(model, resp["usage"], self.prices)
                    self.cache.put(key, model, resp)
                    self._record(node, model, resp["usage"], False, usd)
                finally:
                    with self._lock:
                        self._in_flight_usd -= worst
                result.api_calls += 1
                result.usd += usd
            result.usage = resp["usage"]
            parsed, err = self._parse(resp, schema)
            if parsed is not None:
                result.ok, result.parsed, result.error = True, parsed, ""
                return result
            result.error = err
            log.warning("%s: attempt %d failed: %s", node, attempt + 1, err)
        log.warning("%s: no valid answer after %d attempts; caller uses its 'no view' default", node, attempts)
        return result

    def _call(self, req: dict) -> dict:
        import anthropic
        try:
            resp = self._client().messages.create(**req)
        except anthropic.APIStatusError as e:   # 4xx/5xx after the SDK's own retries
            raise LLMError(f"Claude API error {e.status_code} ({type(e).__name__})") from None
        except anthropic.APIConnectionError as e:
            raise LLMError(f"Claude API connection failed ({type(e).__name__})") from None
        except Exception as e:                  # anything else: no message text, it could hold request details
            raise LLMError(f"Claude API call failed ({type(e).__name__})") from None
        return normalise_response(resp)

    @staticmethod
    def _parse(resp: dict, schema: type[BaseModel]) -> tuple[BaseModel | None, str]:
        if resp["stop_reason"] == "refusal":
            return None, f"refusal (category {resp.get('refusal_category')})"
        if resp["stop_reason"] == "max_tokens":
            return None, "reply cut off at max_tokens"
        try:
            return schema.model_validate_json(resp["text"]), ""
        except (ValidationError, ValueError) as e:
            return None, f"reply does not match the schema ({type(e).__name__})"

    def summary(self) -> str:
        s = self.stats
        tot_in = s["input_tokens"] + s["cache_read_input_tokens"] + s["cache_creation_input_tokens"]
        rate = s["cache_read_input_tokens"] / tot_in if tot_in else 0.0
        return (f"cache hits: {s['cache_hits']}, API calls: {s['api_calls']}, cost: ${s['usd']:.4f} "
                f"(Rs {s['usd'] * self.limits.inr_per_usd:.2f}); prompt-cache read share: {rate:.0%}")
