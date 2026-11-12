"""Red-flag checks (brief section 9): they replace a human reviewer. Run after every backtest;
any hit means "stop and investigate before showing results".

1. Annualised Sharpe ratio above 2 (daily returns over the T-bill rate).
2. No losing calendar year. Checked only when the run has at least 2 full calendar years: with
   one year, a winning year is normal (proto20's 2021 slice: the benchmark rose 33%).
3. A single-day portfolio move above 15% without a matching benchmark move (the portfolio's
   move differs from the benchmark's by more than half of it, i.e. more than 7.5 pp).
4. Weights outside 0x-2x of the benchmark weight, a sector outside its band, or weights not
   adding up to 1 (tolerance 1e-6).
5. Monthly turnover above 100% (the first rebalance buys from cash: exactly 100%, allowed).
6. Any gateway read with a time later than the rebalance's decision time.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

TOL = 1e-6
SHARPE_LIMIT = 2.0
BIG_DAY = 0.15
FULL_YEAR_DAYS = 240


def check_run(run_dir: Path, *, min_mult: float, max_mult: float, band_pp: float,
              riskfree: pd.Series | None = None) -> list[dict]:
    """``riskfree``: daily risk-free returns indexed by date (optional; 0 if missing)."""
    run_dir = Path(run_dir)
    flags: list[dict] = []
    nav = pd.read_csv(run_dir / "nav.csv", index_col="date", parse_dates=True)
    r = nav["nav"].pct_change().dropna()
    rb = nav["benchmark_nav"].pct_change().dropna()

    rf = riskfree.reindex(r.index).ffill().fillna(0.0) if riskfree is not None and len(riskfree) else 0.0
    ex = r - rf
    if len(ex) > 20 and ex.std() > 0:
        sharpe = float(ex.mean() / ex.std() * math.sqrt(252))
        if sharpe > SHARPE_LIMIT:
            flags.append({"flag": "sharpe_above_2", "detail": f"annualised Sharpe {sharpe:.2f}"})

    by_year = nav["nav"].groupby(nav.index.year)
    ends = by_year.last()
    yearly_all = ends / ends.shift(1, fill_value=float(nav["nav"].iloc[0])) - 1
    full = [y for y, n in by_year.size().items() if n >= FULL_YEAR_DAYS]
    if len(full) >= 2:
        yearly = {int(y): float(yearly_all[y]) for y in full}
        if all(v >= 0 for v in yearly.values()):
            flags.append({"flag": "no_losing_year",
                          "detail": "; ".join(f"{y} {v:+.1%}" for y, v in yearly.items())})

    both = pd.concat([r, rb], axis=1, keys=["p", "b"]).dropna()
    big = both[(both["p"].abs() > BIG_DAY) & ((both["p"] - both["b"]).abs() > both["p"].abs() / 2)]
    for d, row in big.iterrows():
        flags.append({"flag": "big_day_without_benchmark", "detail": f"{d.date()}: portfolio {row.p:+.1%}, "
                                                                     f"benchmark {row.b:+.1%}"})

    w = pd.read_csv(run_dir / "weights.csv")
    for reb, g in w.groupby("rebalance"):
        ratio = g["weight"] / g["benchmark"]
        bad = g[(ratio < min_mult - TOL) | (ratio > max_mult + TOL)]
        for row in bad.itertuples():
            flags.append({"flag": "weight_outside_range", "detail": f"{reb} {row.company_id}: "
                                                                    f"x{row.weight / row.benchmark:.4f}"})
        sec = g.groupby("sector")[["weight", "benchmark"]].sum()
        for s, row in sec.iterrows():
            if abs(row.weight - row.benchmark) > band_pp / 100 + TOL:
                flags.append({"flag": "sector_outside_band",
                              "detail": f"{reb} {s}: {row.weight:.2%} vs benchmark {row.benchmark:.2%}"})
        if abs(g["weight"].sum() - 1) > TOL:
            flags.append({"flag": "weights_do_not_sum_to_1", "detail": f"{reb}: {g['weight'].sum():.6f}"})

    ev = pd.read_csv(run_dir / "rebalances.csv")
    if len(ev):
        reb = ev[ev["event"] == "rebalance"]
        for row in reb.itertuples():
            if row.turnover > 1.0 + TOL:
                flags.append({"flag": "turnover_above_100pct", "detail": f"{row.date}: {row.turnover:.1%}"})

    ck = run_dir / "checks.csv"
    if ck.exists():
        c = pd.read_csv(ck)
        for row in c.itertuples():
            if isinstance(row.max_read, str) and pd.Timestamp(row.max_read) > pd.Timestamp(row.as_of):
                flags.append({"flag": "read_after_decision_time",
                              "detail": f"{row.rebalance}: read {row.max_read}, decision {row.as_of}"})
    else:
        flags.append({"flag": "no_gateway_log", "detail": "checks.csv missing: cannot verify gateway reads"})
    return flags


def format_flags(flags: list[dict]) -> str:
    if not flags:
        return "red flags: 0 hits"
    lines = [f"red flags: {len(flags)} hit(s), investigate before sharing results:"]
    lines += [f"  - {f['flag']}: {f['detail']}" for f in flags[:20]]
    if len(flags) > 20:
        lines.append(f"  ... and {len(flags) - 20} more (see red_flags.json)")
    return "\n".join(lines)


def riskfree_daily(gw, as_of) -> pd.Series:
    rf = gw.get_riskfree(as_of)
    if rf.empty:
        return pd.Series(dtype=float)
    s = pd.Series(rf["rf_daily"].to_numpy(), index=pd.DatetimeIndex(rf["date"]))
    return s[~s.index.duplicated()].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
