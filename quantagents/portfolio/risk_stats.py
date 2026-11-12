"""Risk numbers for Dave, the risk control analyst (D33). All computed here, never by an LLM.

Per stock (1 year of daily total returns known at ``as_of``):
- returns over 1, 3 and 12 months, annualised volatility, beta against the benchmark;
- daily turnover ratio = average dollar volume over 20 days / market value (how easily it trades).

Per portfolio (weights ``w`` against benchmark weights ``b``):
- beta = sum of w x stock beta; volatility = sqrt(w' S w x 252) with the sample covariance S;
- liquidity ratio LR = (sum of w x turnover ratio) / (sum of b x turnover ratio): 1 = as liquid as the benchmark;
- max active sector exposure = largest |portfolio sector weight - benchmark sector weight|;
- the paper's risk score R = w1 x beta + w2 x (1 / LR) + w3 x (max active sector / band) + w4 x (vol / benchmark vol),
  weights in config (default 0.25 each). Every term is scaled so the benchmark itself scores
  1, 1, 0 and 1: the benchmark's R is 0.75. Informational only: there is no risk veto (D33).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def returns_panel(gw, companies, as_of, lookback_days: int = 400) -> pd.DataFrame:
    """Daily total returns (rows: trading days, columns: companies), bars known at ``as_of``."""
    p = gw.get_prices(list(companies), as_of, lookback_days=lookback_days)
    if p.empty:
        return pd.DataFrame(columns=list(companies), dtype=float)
    r = p.pivot_table(index="date", columns="company_id", values="ret")
    r.index = pd.DatetimeIndex(r.index)
    return r.reindex(columns=list(companies))


def _total(r: pd.Series, n: int) -> float:
    r = r.dropna()
    return float((1 + r.iloc[-n:]).prod() - 1) if len(r) >= n else float("nan")


def stock_table(gw, companies, as_of, bench: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(per-stock table, last year of daily returns). ``bench`` = benchmark weights at ``as_of``."""
    companies = list(companies)
    p = gw.get_prices(companies, as_of, lookback_days=400)
    r = p.pivot_table(index="date", columns="company_id", values="ret").reindex(columns=companies)
    r.index = pd.DatetimeIndex(r.index)
    year = r.iloc[-TRADING_DAYS:]
    rb = year.fillna(0.0) @ bench.reindex(companies).fillna(0.0)
    w = gw.get_index_weights(as_of).set_index("company_id")["mcap"]
    rows = []
    for c in companies:
        s = year[c]
        ok = s.notna() & rb.notna()
        beta = float(np.cov(s[ok], rb[ok])[0, 1] / np.var(rb[ok], ddof=1)) if ok.sum() > 20 else float("nan")
        px = p[p["company_id"] == c].tail(20)
        dollar = float((px["close"] * px["volume"]).mean()) if len(px) else float("nan")
        mcap = float(w.get(c, float("nan")))
        rows.append({"company_id": c, "ret_1m": _total(r[c], 21), "ret_3m": _total(r[c], 63),
                     "ret_12m": _total(r[c], TRADING_DAYS),
                     "vol_1y": float(s.std() * math.sqrt(TRADING_DAYS)) if s.notna().sum() > 20 else float("nan"),
                     "beta_1y": beta,
                     "turnover_ratio": dollar / mcap if mcap and not math.isnan(mcap) else float("nan")})
    return pd.DataFrame(rows).set_index("company_id"), year


def portfolio_stats(w: pd.Series, bench: pd.Series, sectors: pd.Series, table: pd.DataFrame,
                    year: pd.DataFrame, band_pp: float, weights) -> dict:
    """Risk numbers for weights ``w`` (any subset of companies; normalised to sum 1 here)."""
    cols = list(bench.index)
    w = w.reindex(cols).fillna(0.0)
    if w.sum() <= 0:
        return {}
    w = w / w.sum()
    b = bench.reindex(cols).fillna(0.0)
    cov = year.reindex(columns=cols).fillna(0.0).cov().to_numpy() * TRADING_DAYS
    vol = lambda x: float(math.sqrt(max(x @ cov @ x, 0.0)))  # noqa: E731
    beta_s = table["beta_1y"].reindex(cols).fillna(1.0).to_numpy()
    tr = table["turnover_ratio"].reindex(cols)
    tr = tr.fillna(tr.median()).fillna(0.0).to_numpy()
    sec = pd.DataFrame({"w": w, "b": b, "s": sectors.reindex(cols).fillna("Unknown")}).groupby("s")[["w", "b"]].sum()
    active = (sec["w"] - sec["b"])
    top = active.abs().idxmax()
    lr = float((w.to_numpy() @ tr) / (b.to_numpy() @ tr)) if b.to_numpy() @ tr > 0 else 1.0
    out = {"beta": float(w.to_numpy() @ beta_s), "volatility": vol(w.to_numpy()), "benchmark_volatility": vol(b.to_numpy()),
           "liquidity_ratio": lr, "max_active_sector": float(abs(active[top])), "max_active_sector_name": str(top),
           "max_active_sector_signed": float(active[top])}
    band = band_pp / 100.0
    out["risk_score"] = float(weights.beta * out["beta"] + weights.illiquidity * (1.0 / lr if lr > 0 else 10.0)
                              + weights.sector * out["max_active_sector"] / band
                              + weights.volatility * (out["volatility"] / out["benchmark_volatility"]
                                                      if out["benchmark_volatility"] > 0 else 1.0))
    return out


def _f(v, fmt: str) -> str:
    return "n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else fmt.format(v)


def format_stock_table(table: pd.DataFrame, bench: pd.Series, names: dict[str, str] | None = None) -> str:
    lines = ["company | benchmark weight | return 1m | 3m | 12m | volatility (1y) | beta (1y) | daily turnover ratio"]
    for c, r in table.iterrows():
        lines.append(f"{c} | {_f(float(bench.get(c, float('nan'))), '{:.2%}')} | {_f(r.ret_1m, '{:+.1%}')} | "
                     f"{_f(r.ret_3m, '{:+.1%}')} | {_f(r.ret_12m, '{:+.1%}')} | {_f(r.vol_1y, '{:.1%}')} | "
                     f"{_f(r.beta_1y, '{:.2f}')} | {_f(r.turnover_ratio, '{:.3%}')}")
    return "\n".join(lines)


def format_portfolio_stats(label: str, s: dict) -> str:
    if not s:
        return f"{label}: no stock holdings (all cash)."
    return (f"{label}: beta {s['beta']:.2f}; volatility {s['volatility']:.1%} a year (benchmark "
            f"{s['benchmark_volatility']:.1%}); liquidity ratio {s['liquidity_ratio']:.2f} (1 = benchmark); "
            f"largest active sector position {s['max_active_sector_signed']:+.2%} in {s['max_active_sector_name']}; "
            f"risk score R = {s['risk_score']:.3f} (higher = riskier)")
