"""Test double for the Anthropic SDK client: records every request, returns scripted replies."""
from __future__ import annotations

import json
from types import SimpleNamespace


def reply(text: str | dict, stop_reason: str = "end_turn", input_tokens: int = 1000, output_tokens: int = 200,
          cache_read: int = 0, cache_write: int = 0, model: str = "claude-haiku-5-5"):
    if isinstance(text, dict):
        text = json.dumps(text)
    return SimpleNamespace(id="msg_test", model=model, stop_reason=stop_reason, stop_details=None,
                           content=[SimpleNamespace(type="text", text=text)],
                           usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                                                 cache_read_input_tokens=cache_read,
                                                 cache_creation_input_tokens=cache_write))


class FakeMessages:
    def __init__(self, replies, raise_exc: Exception | None = None):
        self.replies = list(replies)
        self.calls: list[dict] = []
        self.raise_exc = raise_exc

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_exc is not None:
            raise self.raise_exc
        if not self.replies:
            raise AssertionError("no scripted reply left")
        return self.replies.pop(0)


class FakeSDK:
    def __init__(self, replies=(), raise_exc: Exception | None = None):
        self.messages = FakeMessages(replies, raise_exc)


def node_of(req: dict) -> str:
    system = req["system"][0]["text"]
    user = req["messages"][0]["content"][0]["text"]
    if system.startswith("You are a junior equity research analyst"):
        return "memo"
    for key, node in (("You are Emily", "emily"), ("You are Bob", "bob"), ("You are Dave", "dave"),
                      ("STRATEGY MEETING", "otto_draft"), ("DECISION MEETING", "otto_final")):
        if key in user:
            return node
    raise AssertionError("unknown request")


def companies_of(req: dict) -> list[str]:
    user = req["messages"][0]["content"][0]["text"]
    line = [ln for ln in user.splitlines() if ln.startswith("Company list (in order):")][-1]
    return [c.strip() for c in line.split(":", 1)[1].split(",")]


def default_answer(node: str, req: dict, tilt=None) -> dict:
    if node == "memo":
        return GOOD_MEMO
    cs = companies_of(req)
    if node in ("emily", "bob"):
        head = "market_summary" if node == "emily" else "simulated_trading_takeaway"
        return {head: f"{node} summary.", "assessments": [
            {"company_id": c, "view": "neutral", "conviction": "low", "reason": "Mixed evidence."} for c in cs]}
    if node == "dave":
        return {"portfolio_risk_summary": "Close to the benchmark.", "concerns": ["none major"],
                "stocks": [{"company_id": c, "risk": "medium", "note": "Average risk."} for c in cs]}
    tilt = tilt or (lambda i, n: 1.5 if i == 0 else (0.5 if i == n - 1 else 1.0))
    return {"summary": f"{node} decision.", "tilts": [
        {"company_id": c, "multiplier": tilt(i, len(cs)), "reason": "Because."} for i, c in enumerate(cs)]}


class CommitteeFake:
    """Fake SDK for the whole agent graph: answers each request by node (memo, emily, bob, dave,
    otto_draft, otto_final). ``answers[node]`` overrides: a dict/str reply, or a function(req) -> dict/str.
    Thread-safe (memos run in parallel)."""

    def __init__(self, answers: dict | None = None, tilt=None):
        import threading
        self.answers = answers or {}
        self.tilt = tilt
        self.calls: list[dict] = []
        self._lock = threading.Lock()
        self.messages = self

    def nodes(self) -> list[str]:
        return [node_of(r) for r in self.calls]

    def create(self, **req):
        with self._lock:
            self.calls.append(req)
        node = node_of(req)
        a = self.answers.get(node)
        body = a(req) if callable(a) else a if a is not None else default_answer(node, req, self.tilt)
        cached = node not in ("memo", "emily")
        return reply(body, input_tokens=800 if cached else 5000, output_tokens=600,
                     cache_read=4000 if cached else 0, cache_write=0 if cached else 4000)


GOOD_MEMO = {"business_summary": "Makes phones.", "price_and_technicals": "Up 9% in a month.",
             "fundamentals": "Revenue $74.60B.", "news": "No major news.", "positives": ["strong margins"],
             "risks": ["high expectations"], "outlook_3m": "slightly_positive", "conviction": "medium",
             "data_gaps": []}
