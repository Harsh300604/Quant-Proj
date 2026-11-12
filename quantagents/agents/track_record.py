"""Track-record memory (D34): how the committee's own past views turned out.

A view made at a rebalance is scored over ``horizon_months`` (3): from the close of that day to
the close of the first trading day ``horizon_months`` months later. It enters the track record
only once that end date is at or before today's decision time, so every outcome shown is fully
known. For example, the 4 Jan 2021 views end on 1 Apr 2021 and first appear on 1 Apr 2021.

A view is a multiplier of benchmark weight: above 1 = overweight (expects to beat the benchmark),
below 1 = underweight, exactly 1 = no view (not scored). Excess return = the stock's total return
minus the benchmark's over the same window (the benchmark held at that day's weights).
Identical for the baseline and the enhanced variant.

``history`` comes from the engine: [{"rebalance": "YYYY-MM-DD", "views": {id: multiplier},
"bench": {id: weight}}, ...] for earlier rebalances of the same run.
"""
from __future__ import annotations

import pandas as pd

from quantagents.data import calendar as cal

NEUTRAL_EPS = 1e-9


def outcome_end(day, horizon_months: int) -> pd.Timestamp:
    d = pd.Timestamp(day)
    m = (d + pd.DateOffset(months=horizon_months))
    return cal.first_trading_day_of_month(m.year, m.month)


def outcomes(gw, history: list[dict], as_of, horizon_months: int = 3) -> pd.DataFrame:
    """One row per scored view (non-neutral, outcome fully known at ``as_of``)."""
    cols = ["made", "ends", "company_id", "multiplier", "stock_return", "benchmark_return", "excess", "right"]
    t = cal.require_utc(as_of)
    today = pd.Timestamp(t.tz_convert(cal.ET).date())
    known = [h for h in history if outcome_end(h["rebalance"], horizon_months) <= today]
    if not known:
        return pd.DataFrame(columns=cols)
    ids = sorted({c for h in known for c in list(h["views"]) + list(h["bench"])})
    first = min(pd.Timestamp(h["rebalance"]) for h in known)
    p = gw.get_prices(ids, t, lookback_days=(today - first).days + 10)
    r = p.pivot_table(index="date", columns="company_id", values="ret")
    r.index = pd.DatetimeIndex(r.index)
    tri = (1 + r.fillna(0.0)).cumprod()
    rows = []
    for h in known:
        d0, d1 = pd.Timestamp(h["rebalance"]), outcome_end(h["rebalance"], horizon_months)
        a, b = tri.loc[:d0], tri.loc[:d1]
        if a.empty or b.empty:
            continue
        growth = b.iloc[-1] / a.iloc[-1] - 1
        bench = pd.Series(h["bench"], dtype=float)
        bench = bench[bench.index.isin(growth.dropna().index)]
        if bench.sum() <= 0:
            continue
        bret = float((bench / bench.sum() * growth.reindex(bench.index)).sum())
        for c, m in sorted(h["views"].items()):
            if abs(m - 1.0) <= NEUTRAL_EPS or c not in growth or pd.isna(growth[c]):
                continue
            ex = float(growth[c] - bret)
            rows.append({"made": str(d0.date()), "ends": str(d1.date()), "company_id": c, "multiplier": float(m),
                         "stock_return": float(growth[c]), "benchmark_return": bret, "excess": ex,
                         "right": bool((m > 1) == (ex > 0))})
    return pd.DataFrame(rows, columns=cols)


def format_track_record(df: pd.DataFrame, as_of, horizon_months: int = 3, last_n: int = 3,
                        first_rebalance: str | None = None) -> str:
    t = cal.require_utc(as_of)
    if df.empty:
        first = f" (the first one ends on {outcome_end(first_rebalance, horizon_months).date()})" if first_rebalance else ""
        return (f"No track record yet: a view counts only once its {horizon_months}-month outcome is fully known "
                f"at this decision time{first}.")
    hits, n = int(df["right"].sum()), len(df)
    ow, uw = df[df["multiplier"] > 1], df[df["multiplier"] < 1]
    lines = [f"All scored views so far: {hits} of {n} right ({hits / n:.0%}). Overweights averaged "
             f"{ow['excess'].mean():+.1%} vs the benchmark ({len(ow)} views); underweights averaged "
             f"{uw['excess'].mean():+.1%} ({len(uw)} views)." if len(ow) and len(uw) else
             f"All scored views so far: {hits} of {n} right ({hits / n:.0%})."]
    for made in sorted(df["made"].unique(), reverse=True)[:last_n]:
        g = df[df["made"] == made].sort_values("multiplier", ascending=False)
        lines.append(f"Views made {made} (outcome to {g['ends'].iloc[0]}; benchmark {g['benchmark_return'].iloc[0]:+.1%}):")
        lines += [f"- {r.company_id} x{r.multiplier:.2f}: stock {r.stock_return:+.1%}, {r.excess:+.1%} vs benchmark "
                  f"({'right' if r.right else 'wrong'})" for r in g.itertuples()]
    lines.append(f"(Decision time now: {t.tz_convert(cal.ET).date()}; only outcomes that ended by then are shown.)")
    return "\n".join(lines)
