"""API spend from the cost ledger, in USD and INR (Phase 3 / proto20 P2).

    python scripts\\ledger_report.py                       # spend by key label, stage, run and model
    python scripts\\ledger_report.py --simulate-spend 32.01 # would the next call be blocked? (no real spend)

Shows remaining budget per key label and funding stage, and the prompt-cache read share.
Never shows any key: the ledger stores only key LABELS.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from quantagents.config import CONFIG_DIR, load_config  # noqa: E402
from quantagents.llm.ledger import BudgetExceeded, Ledger, Limits  # noqa: E402
from quantagents.paths import Paths  # noqa: E402


def table(df: pd.DataFrame, by: str, rate: float) -> pd.DataFrame:
    """Token columns count API calls only (a cache hit repeats the stored usage but costs nothing)."""
    df = df.copy()
    for c in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"):
        df[c] = df[c].where(df["cache_hit"] == 0, 0)
    g = df.groupby(by).agg(calls=("usd", "size"), api_calls=("cache_hit", lambda s: int((s == 0).sum())),
                           cache_hits=("cache_hit", "sum"), input_tokens=("input_tokens", "sum"),
                           cache_read=("cache_read_input_tokens", "sum"),
                           cache_write=("cache_creation_input_tokens", "sum"), output_tokens=("output_tokens", "sum"),
                           usd=("usd", "sum")).reset_index()
    g["inr"] = (g["usd"] * rate).round(2)
    g["usd"] = g["usd"].round(4)
    return g


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(CONFIG_DIR / "base.yaml"))
    ap.add_argument("--simulate-spend", type=float, help="pretend this much more USD was spent in the active stage")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    lim = Limits.from_config(cfg)
    path = Paths.from_config(cfg).ledger
    ledger = Ledger(path) if path.exists() else Ledger(":memory:")
    df = ledger.frame()
    rate = lim.inr_per_usd
    pd.set_option("display.width", 200)
    print(f"Ledger: {path}{'' if path.exists() else ' (no calls yet)'}")
    if len(df):
        df["cache_hit"] = df["cache_hit"].astype(int)
        for by in ("key_label", "stage", "run_id", "model"):
            print(f"\nBy {by}:")
            print(table(df, by, rate).to_string(index=False))
        miss = df[df["cache_hit"] == 0]
        tot_in = miss[["input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"]].sum().sum()
        share = miss["cache_read_input_tokens"].sum() / tot_in if tot_in else 0.0
        print(f"\nResponse cache: {int(df['cache_hit'].sum())} of {len(df)} calls served free; "
              f"prompt-cache read share of input tokens on API calls: {share:.0%}")
    key = ledger.spent(key_label=lim.key_label)
    stage = ledger.spent(stage=lim.stage, key_label=lim.key_label)
    print(f"\nKey '{lim.key_label}': spent ${key:.4f} (Rs {key * rate:.2f}) of ${lim.key_budget:.2f}; "
          f"automatic stop at ${lim.key_stop:.2f}; ${max(lim.key_stop - key, 0):.4f} left before the stop")
    print(f"Stage '{lim.stage}': spent ${stage:.4f} (Rs {stage * rate:.2f}) of ${lim.stage_budget:.2f}; "
          f"automatic stop at ${lim.stage_stop:.2f}; ${max(lim.stage_stop - stage, 0):.4f} left before the stop")
    if args.simulate_spend is not None:
        sim = ledger.copy_to_memory()          # the real ledger is never touched
        sim.record(run_id="__simulation__", node="simulation", model="none", key_label=lim.key_label,
                   stage=lim.stage, variant="none", usage={}, cache_hit=False, usd=args.simulate_spend,
                   inr_per_usd=rate)
        try:
            sim.check(lim, run_id="__next_call__", worst_case_usd=0.0001)
            print(f"\nSimulated +${args.simulate_spend:.2f}: OK, the next call would be allowed")
        except BudgetExceeded as e:
            print(f"\nSimulated +${args.simulate_spend:.2f}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
