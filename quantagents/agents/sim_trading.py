"""Simulated trading for Bob (D32): Python backtests a fixed pool of simple rules over the last
12 months, using only data known at each step, and Bob reads the results table.

The pool (each rule tilts the benchmark; no LLM involved):
- momentum_12_1: overweight the past winners (return from 12 months to 1 month ago)
- reversal_1m:   overweight last month's losers (short-term bounce)
- low_volatility: overweight the calmest stocks (3-month daily volatility)
- quality:       overweight the highest operating margin (latest filed annual figures, else quarterly)
- index_hold:    the benchmark itself (the yardstick)

Every month in the look-back, at the close of that month's first trading day, each rule ranks
the companies on its signal: the top third gets 1.5x its benchmark weight, the bottom third
0.5x, the rest 1x (a missing signal counts as 1x). The tilted weights are renormalised to sum
to 1 (sector bands are not applied here), held until the next month's first trading day, and
the return is recorded. The companies are today's universe (the paper also tests its pool on
the current stocks).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from quantagents.data import calendar as cal
from quantagents.eval.benchmarks import renormalise

POOL = ("momentum_12_1", "reversal_1m", "low_volatility", "quality", "index_hold")
DESCRIPTION = {"momentum_12_1": "past 12-month winners (skipping the last month)",
               "reversal_1m": "last month's losers",
               "low_volatility": "the calmest stocks (3-month volatility)",
               "quality": "the highest operating margin (latest filings)",
               "index_hold": "the benchmark itself"}
TILT_UP, TILT_DOWN = 1.5, 0.5


def _quality(gw, companies, as_of) -> pd.Series:
    f = gw.get_fundamentals(list(companies), as_of)
    out = {}
    for c in companies:
        for ptype in ("annual", "quarter"):
            rev = f[(f["company_id"] == c) & (f["metric"] == "revenue") & (f["period_type"] == ptype)]
            op = f[(f["company_id"] == c) & (f["metric"] == "operating_income") & (f["period_type"] == ptype)]
            if len(rev) and len(op) and rev["period_end"].iloc[0] == op["period_end"].iloc[0] and rev["value"].iloc[0]:
                out[c] = float(op["value"].iloc[0] / rev["value"].iloc[0])
                break
    return pd.Series(out, dtype=float).reindex(list(companies))


def signals_at(tri: pd.DataFrame, day: pd.Timestamp, quality: pd.Series) -> dict[str, pd.Series]:
    """Signals from data up to and including ``day`` (higher = overweight)."""
    h = tri.loc[:day]
    rets = h.pct_change(fill_method=None)
    out = {}
    if len(h) > 252:
        out["momentum_12_1"] = h.iloc[-22] / h.iloc[-253] - 1
    else:
        out["momentum_12_1"] = pd.Series(np.nan, index=tri.columns)
    out["reversal_1m"] = -(h.iloc[-1] / h.iloc[-22] - 1) if len(h) > 21 else pd.Series(np.nan, index=tri.columns)
    out["low_volatility"] = -rets.iloc[-63:].std() if len(h) > 63 else pd.Series(np.nan, index=tri.columns)
    out["quality"] = quality.reindex(tri.columns)
    return out


def tilt(signal: pd.Series, bench: pd.Series) -> pd.Series:
    """Top third x1.5, bottom third x0.5, others (and missing signals) x1; renormalised."""
    s = signal.reindex(bench.index).dropna()
    m = pd.Series(1.0, index=bench.index)
    k = len(s) // 3
    if k >= 1:
        order = s.sort_values(kind="mergesort")                 # stable: ties keep the index order
        m[order.index[-k:]] = TILT_UP
        m[order.index[:k]] = TILT_DOWN
    w = bench * m
    return w / w.sum()


def simulate_pool(gw, companies, as_of, months: int = 12) -> dict:
    """Run the pool over the ``months`` monthly periods ending at ``as_of``.

    Returns {"table": DataFrame (one row per rule), "picks": {rule: (top names, bottom names) now},
             "periods": number of complete monthly periods}."""
    t = cal.require_utc(as_of)
    today = pd.Timestamp(t.tz_convert(cal.ET).date())
    start = (today - pd.DateOffset(months=months)).replace(day=1)
    days = [d for d in cal.rebalance_dates(start, today) if d <= today]
    if not days or days[-1] != today:
        days.append(today)
    companies = list(companies)
    p = gw.get_prices(companies, t, lookback_days=months * 31 + 420)
    r = p.pivot_table(index="date", columns="company_id", values="ret").reindex(columns=companies)
    r.index = pd.DatetimeIndex(r.index)
    tri = (1 + r.fillna(0.0)).cumprod()
    tri = tri.where(r.notna().cummax())                          # NaN before a company's first bar

    benches = {}
    for d in days:                       # months without benchmark weights (before the data starts) are skipped
        try:
            benches[d] = renormalise(gw.get_index_weights(cal.as_of_for(d)).set_index("company_id")["weight"], companies)
        except ValueError:
            continue
    days = [d for d in days if d in benches]
    period_rets = {k: [] for k in POOL}
    with_signal = {k: 0 for k in POOL}
    picks = {}
    for i, d in enumerate(days):
        at = cal.as_of_for(d)
        bench = benches[d]
        sig = signals_at(tri, d, _quality(gw, companies, at))
        if i < len(days) - 1:
            for k in POOL:
                if k == "index_hold" or sig[k].reindex(bench.index).notna().sum() >= 3:
                    with_signal[k] += 1
        weights = {k: tilt(sig[k], bench) for k in POOL if k != "index_hold"}
        weights["index_hold"] = bench
        if i == len(days) - 1:
            for k in POOL:
                if k == "index_hold":
                    continue
                s = sig[k].reindex(bench.index).dropna()
                n = len(s) // 3
                o = s.sort_values(kind="mergesort")
                picks[k] = (list(o.index[-n:][::-1]) if n else [], list(o.index[:n]) if n else [])
            break
        nxt = days[i + 1]
        growth = (tri.loc[:nxt].iloc[-1] / tri.loc[:d].iloc[-1]).reindex(bench.index)
        for k in POOL:
            w = weights[k]
            g = growth.fillna(1.0)                                 # no price = flat (rare; logged in data report)
            period_rets[k].append(float((w * g).sum() - 1))
    n = len(days) - 1
    rows = []
    idx = np.array(period_rets["index_hold"])
    for k in POOL:
        x = np.array(period_rets[k])
        total = float(np.prod(1 + x) - 1) if n else float("nan")
        itot = float(np.prod(1 + idx) - 1) if n else float("nan")
        last3 = float(np.prod(1 + x[-3:]) - np.prod(1 + idx[-3:])) if n >= 3 else float("nan")
        rows.append({"rule": k, "overweights": DESCRIPTION[k], "months_with_signal": with_signal[k],
                     "return": total, "vs_index": total - itot,
                     "months_beating_index": int((x > idx + 1e-12).sum()) if k != "index_hold" else None,
                     "last_3m_vs_index": last3 if k != "index_hold" else 0.0})
    return {"table": pd.DataFrame(rows).set_index("rule"), "picks": picks, "periods": n,
            "from": str(days[0].date()), "to": str(days[-1].date())}


def _p(v) -> str:
    return "n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:+.1%}"


def format_pool(res: dict) -> str:
    n = res["periods"]
    lines = [f"Look-back: {n} monthly periods, {res['from']} to {res['to']} (each rule: top third x1.5, "
             "bottom third x0.5 of benchmark weight; rebalanced monthly; no costs)",
             "rule | overweights | months with a signal | total return | vs index_hold | months beating index_hold | "
             "last 3 months vs index_hold",
             "(without a signal a rule simply holds the benchmark that month)"]
    for k, r in res["table"].iterrows():
        beat = "-" if r["months_beating_index"] is None or (isinstance(r["months_beating_index"], float)
                                                          and math.isnan(r["months_beating_index"])) \
            else f"{int(r['months_beating_index'])} of {n}"
        sig = "-" if k == "index_hold" else f"{int(r['months_with_signal'])} of {n}"
        lines.append(f"{k} | {r['overweights']} | {sig} | {_p(r['return'])} | {_p(r['vs_index'])} | {beat} | "
                     f"{_p(r['last_3m_vs_index'])}")
    lines.append("What each rule would overweight / underweight today:")
    for k, (top, bottom) in res["picks"].items():
        lines.append(f"- {k}: overweight {', '.join(top) or 'none (signal not available)'}; "
                     f"underweight {', '.join(bottom) or 'none'}")
    return "\n".join(lines)
