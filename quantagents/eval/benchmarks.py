"""Custom cap-weighted benchmark: the run's own companies at market weight (D41).

For proto20 this is "the same 20 companies, held at their market-cap weights". Weights come from
the derived index weights (``index_weights``), renormalised to the chosen companies. Timing is the
same as ``quality.index_vs_benchmark``: the weights at the close of day t-1 apply to the total
returns on day t, so no weight ever uses data after t-1.

    benchmark_weights(gateway, companies, as_of)   weight vector at one decision time (constraints)
    custom_cap_index(gateway, companies, start, end) daily weights and daily total return
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway


def renormalise(weights: pd.Series, companies) -> pd.Series:
    """Index weights restricted to ``companies`` and scaled to sum to 1 (companies without a
    weight that day are left out)."""
    w = weights.reindex(list(companies)).dropna()
    total = w.sum()
    if total <= 0:
        raise ValueError("none of the chosen companies has an index weight")
    return w / total


def benchmark_weights(gateway: Gateway, companies, as_of) -> pd.Series:
    """Benchmark weight per company at ``as_of`` (the latest close at or before it)."""
    w = gateway.get_index_weights(as_of).set_index("company_id")["weight"]
    return renormalise(w, companies)


def cap_index_returns(weights: pd.DataFrame, returns: pd.DataFrame) -> pd.Series:
    """Daily index return from wide tables (index = trading dates, columns = companies).

    ``weights`` row t = weights at the close of t; ``returns`` row t = total return on t.
    Return on t = sum over companies of weight(t-1) x return(t). A missing return counts as 0."""
    days = returns.index.intersection(weights.index).sort_values()
    w = weights.reindex(days).shift(1)
    r = returns.reindex(days).reindex(columns=w.columns).fillna(0.0)
    out = (w * r).sum(axis=1, min_count=1)
    return out.iloc[1:].rename("ret")


@dataclass
class CustomIndex:
    weights: pd.DataFrame      # close of each trading day x company, rows sum to 1
    returns: pd.Series         # daily total return (weights of the previous close)
    missing: pd.DataFrame      # (date, company_id) with no weight that day

    @property
    def nav(self) -> pd.Series:
        return (1 + self.returns).cumprod().rename("nav")


def custom_cap_index(gateway: Gateway, companies, start, end) -> CustomIndex:
    """Daily weights and total return of the cap-weighted index of ``companies`` from ``start``
    to ``end`` (dates). Every row is read through the gateway at that day's close."""
    companies = list(companies)
    days = cal.trading_days(pd.Timestamp(start), pd.Timestamp(end))
    if len(days) == 0:
        raise ValueError("no trading days between start and end")
    prev = cal.previous_trading_day(days[0])
    all_days = [prev] + list(days)
    rows, missing = [], []
    for d in all_days:
        w = gateway.get_index_weights(cal.close_utc(d))
        if len(w) and pd.Timestamp(w["date"].iloc[0]).normalize() != pd.Timestamp(d).normalize():
            w = w.iloc[0:0]          # the store has no weights for this exact day (data gap)
        s = renormalise(w.set_index("company_id")["weight"], companies) if len(w) else pd.Series(dtype=float)
        missing += [{"date": d, "company_id": c} for c in companies if c not in s.index]
        rows.append(s.rename(d))
    weights = pd.DataFrame(rows).reindex(columns=companies).fillna(0.0)
    weights.index = pd.DatetimeIndex(all_days)
    px = gateway.get_prices(companies, cal.close_utc(days[-1]),
                            lookback_days=(pd.Timestamp(days[-1]) - pd.Timestamp(prev)).days + 5)
    rets = px.pivot_table(index="date", columns="company_id", values="ret")
    rets.index = pd.DatetimeIndex(rets.index)
    ret = cap_index_returns(weights, rets.reindex(pd.DatetimeIndex(all_days)))
    return CustomIndex(weights.iloc[1:], ret, pd.DataFrame(missing, columns=["date", "company_id"]))
