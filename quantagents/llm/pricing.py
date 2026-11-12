"""Token prices (configs/pricing.yaml) and the cost of one call."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from quantagents.config import CONFIG_DIR

PER_TOKEN = 1e-6


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_write: float
    cache_read: float


@lru_cache(maxsize=4)
def load_pricing(path: str | Path = CONFIG_DIR / "pricing.yaml") -> dict[str, Price]:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return {m: Price(**v) for m, v in raw.items()}


def cost_usd(model: str, usage: dict, prices: dict[str, Price] | None = None) -> float:
    """USD for one call from its four token counts (missing counts are 0)."""
    p = (prices or load_pricing())[model]
    u = {k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens",
                                              "cache_creation_input_tokens", "cache_read_input_tokens")}
    return PER_TOKEN * (u["input_tokens"] * p.input + u["output_tokens"] * p.output
                        + u["cache_creation_input_tokens"] * p.cache_write
                        + u["cache_read_input_tokens"] * p.cache_read)


def worst_case_usd(model: str, est_input_tokens: int, max_tokens: int,
                   prices: dict[str, Price] | None = None) -> float:
    """Upper bound before a call: all input billed at the dearer of input / cache-write,
    and every allowed output token used."""
    p = (prices or load_pricing())[model]
    return PER_TOKEN * (est_input_tokens * max(p.input, p.cache_write) + max_tokens * p.output)
