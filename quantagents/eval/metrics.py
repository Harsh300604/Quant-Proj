"""Performance metrics (brief section 11, main plan Phase 6). Python only, no LLM calls.

From a daily NAV series (and optionally a benchmark NAV and the daily T-bill rate):
- total return, CAGR, calendar-year returns, annualised volatility;
- Sharpe and Sortino ratios on returns above the T-bill rate; maximum drawdown; Calmar (CAGR / |max drawdown|);
- against the benchmark: active return (CAGR difference), tracking error, information ratio;
- from the run's weights: average monthly turnover and total trading cost;
- diversification as in the QuantAgents paper (D36):
  ENT = entropy of the portfolio weights, -sum w ln w (higher = spread over more companies);
  ENB = effective number of bets (Meucci 2009): exp(entropy of the risk shares of the
  uncorrelated principal portfolios), from one year of daily returns before each rebalance;
- moving-block bootstrap confidence intervals (block 21 days, 2,000 resamples, fixed seed) for the
  Sharpe ratio, the information ratio and the annualised active return.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

DAYS = 252
BLOCK = 21
RESAMPLES = 2000
SEED = 20261113


def _rf(r: pd.Series, rf: pd.Series | None) -> pd.Series:
    if rf is None or not len(rf):
        return pd.Series(0.0, index=r.index)
    return rf.reindex(r.index).ffill().fillna(0.0)


def sharpe(ex: pd.Series) -> float:
    return float(ex.mean() / ex.std() * math.sqrt(DAYS)) if ex.std() > 0 else float("nan")


def sortino(ex: pd.Series) -> float:
    down = np.sqrt((np.minimum(ex, 0) ** 2).mean())
    return float(ex.mean() / down * math.sqrt(DAYS)) if down > 0 else float("nan")


def max_drawdown(nav: pd.Series) -> float:
    return float((nav / nav.cummax() - 1).min())


def cagr(nav: pd.Series) -> float:
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    return float((nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1) if years > 0 else float("nan")


def calendar_returns(nav: pd.Series) -> dict[int, float]:
    ends = nav.groupby(nav.index.year).last()
    prev = ends.shift(1, fill_value=float(nav.iloc[0]))
    return {int(y): float(v) for y, v in (ends / prev - 1).items()}


def performance(nav: pd.Series, rf: pd.Series | None = None, bench: pd.Series | None = None) -> dict:
    nav = nav.dropna()
    r = nav.pct_change().dropna()
    ex = r - _rf(r, rf)
    mdd = max_drawdown(nav)
    out = {"total_return": float(nav.iloc[-1] / nav.iloc[0] - 1), "cagr": cagr(nav),
           "volatility": float(r.std() * math.sqrt(DAYS)), "sharpe": sharpe(ex), "sortino": sortino(ex),
           "max_drawdown": mdd, "calmar": cagr(nav) / abs(mdd) if mdd < 0 else float("nan")}
    for y, v in calendar_returns(nav).items():
        out[f"return_{y}"] = v
    if bench is not None:
        b = bench.reindex(nav.index).ffill()
        a = (r - b.pct_change().reindex(r.index)).dropna()
        out["active_return"] = out["cagr"] - cagr(b.dropna())
        out["tracking_error"] = float(a.std() * math.sqrt(DAYS))
        out["information_ratio"] = float(a.mean() / a.std() * math.sqrt(DAYS)) if a.std() > 0 else float("nan")
    return out


def entropy(w: np.ndarray) -> float:
    w = np.asarray(w, dtype=float)
    w = w[w > 0] / w[w > 0].sum()
    return float(-(w * np.log(w)).sum())


def enb(w: np.ndarray, cov: np.ndarray) -> float:
    """Meucci's effective number of bets with principal-component (uncorrelated) bets."""
    vals, vecs = np.linalg.eigh(cov)
    vals = np.clip(vals, 0, None)
    exposure = vecs.T @ np.asarray(w, dtype=float)
    contrib = exposure ** 2 * vals
    if contrib.sum() <= 0:
        return float("nan")
    p = contrib / contrib.sum()
    p = p[p > 0]
    return float(np.exp(-(p * np.log(p)).sum()))


def diversification(weights: pd.DataFrame, returns: pd.DataFrame) -> dict:
    """Average ENT and ENB over the rebalances. ``weights``: rebalance, company_id, weight[, benchmark].
    ``returns``: daily returns (dates x companies) covering a year before the first rebalance."""
    ents, enbs, b_ents, b_enbs = [], [], [], []
    for reb, g in weights.groupby("rebalance"):
        g = g[g["weight"] > 0] if "benchmark" not in g else g
        ids = list(g["company_id"])
        hist = returns.reindex(columns=ids).loc[:pd.Timestamp(reb)].iloc[-DAYS:].fillna(0.0)
        cov = hist.cov().to_numpy() if len(hist) > 20 else None
        ents.append(entropy(g["weight"].to_numpy()))
        if cov is not None:
            enbs.append(enb(g["weight"].to_numpy(), cov))
        if "benchmark" in g:
            b_ents.append(entropy(g["benchmark"].to_numpy()))
            if cov is not None:
                b_enbs.append(enb(g["benchmark"].to_numpy(), cov))
    mean = lambda x: float(np.mean(x)) if x else float("nan")  # noqa: E731
    return {"ent": mean(ents), "enb": mean(enbs), "benchmark_ent": mean(b_ents), "benchmark_enb": mean(b_enbs)}


def block_bootstrap(series: list[pd.Series], stat, n: int = RESAMPLES, block: int = BLOCK, seed: int = SEED,
                    level: float = 0.90) -> tuple[float, float]:
    """Moving-block bootstrap of aligned daily series; ``stat(*resampled)`` -> number. Returns the CI."""
    data = pd.concat(series, axis=1).dropna().to_numpy()
    t = len(data)
    if t < 2 * block:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    k = int(math.ceil(t / block))
    vals = []
    for _ in range(n):
        starts = rng.integers(0, t - block + 1, k)
        idx = (starts[:, None] + np.arange(block)).ravel()[:t]
        sample = data[idx]
        vals.append(stat(*[pd.Series(sample[:, j]) for j in range(sample.shape[1])]))
    lo, hi = np.nanpercentile(vals, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(lo), float(hi)


def confidence_intervals(nav: pd.Series, bench: pd.Series, rf: pd.Series | None = None) -> dict:
    r = nav.pct_change().dropna()
    rb = bench.reindex(nav.index).ffill().pct_change().reindex(r.index)
    ex = r - _rf(r, rf)
    act = r - rb
    return {"sharpe_ci": block_bootstrap([ex], sharpe),
            "information_ratio_ci": block_bootstrap([act], lambda a: float(a.mean() / a.std() * math.sqrt(DAYS))
                                                    if a.std() > 0 else float("nan")),
            "active_return_ci": block_bootstrap([act], lambda a: float(a.mean() * DAYS))}
