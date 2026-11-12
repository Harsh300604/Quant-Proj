"""Cost forecast from measured token counts (brief section 8; P4 forecast v1).

Method:
1. Take the API calls (cache misses) of a measured run from the ledger. Per node (memo, emily, bob,
   dave, otto_draft, otto_final): calls per rebalance (retries included) and average tokens per
   call: fresh input, prompt-cache writes, prompt-cache reads, output.
2. Price the same token profile with another model (e.g. Sonnet for the committee on the paper
   tier) using configs/pricing.yaml.
3. Scale: memo calls with the number of companies; committee calls with the number of rebalances.
   For a 100-company universe the committee briefing also carries 80 one-line summaries (about
   ``ONE_LINER_TOKENS`` each), added to the cached block.
4. Range +-20%: Sonnet may write longer answers than Haiku, and news volume varies by month.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quantagents.llm.pricing import cost_usd

TOKENS = ["input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"]
COMMITTEE_NODES = ("emily", "bob", "dave", "otto_draft", "otto_final")
ONE_LINER_TOKENS = 40
RANGE = 0.20


def profile(ledger: pd.DataFrame, run_id: str, rebalances: int, companies: int) -> pd.DataFrame:
    """Per node: calls per rebalance (memo: per company per rebalance) and mean tokens per API call."""
    rows = ledger[(ledger["run_id"] == run_id) & (ledger["cache_hit"] == 0)]
    if rows.empty:
        raise ValueError(f"no API calls for run {run_id!r} in the ledger")
    out = rows.groupby("node")[TOKENS].mean()
    n = rows.groupby("node").size()
    out["calls_per_rebalance"] = n / rebalances
    out.loc[out.index == "memo", "calls_per_rebalance"] = n.get("memo", 0) / (rebalances * companies)
    out["measured_calls"] = n
    out["model"] = rows.groupby("node")["model"].first()
    return out


@dataclass
class Projection:
    usd: float
    memo_usd: float
    committee_usd: float
    low: float
    high: float


def project(prof: pd.DataFrame, *, rebalances: int, companies: int, memo_model: str, committee_model: str,
            prices: dict, selected: int = 20) -> Projection:
    memo_usd = committee_usd = 0.0
    extra = max(0, companies - selected) * ONE_LINER_TOKENS          # one-liners in the cached briefing
    for node, r in prof.iterrows():
        usage = {k: round(float(r[k])) for k in TOKENS}
        if node == "memo":
            memo_usd += cost_usd(memo_model, usage, prices) * r["calls_per_rebalance"] * companies * rebalances
            continue
        if extra:
            if usage["cache_creation_input_tokens"] > usage["cache_read_input_tokens"]:
                usage["cache_creation_input_tokens"] += extra
            else:
                usage["cache_read_input_tokens"] += extra
        committee_usd += cost_usd(committee_model, usage, prices) * r["calls_per_rebalance"] * rebalances
    total = memo_usd + committee_usd
    return Projection(total, memo_usd, committee_usd, total * (1 - RANGE), total * (1 + RANGE))


def cache_read_share(prof: pd.DataFrame, nodes=COMMITTEE_NODES) -> float:
    p = prof[prof.index.isin(nodes)]
    w = p["calls_per_rebalance"]
    total = sum(float((p[k] * w).sum()) for k in TOKENS[:3])
    return float((p["cache_read_input_tokens"] * w).sum()) / total if total else 0.0
