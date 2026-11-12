"""Carhart 4-factor regression with Newey-West standard errors (brief section 11). numpy only.

Daily excess return (portfolio - T-bill) = alpha + b1 (market - T-bill) + b2 SMB + b3 HML + b4 MOM + error,
with the Kenneth French daily factors. Alpha is reported per year (daily alpha x 252) with its
t-statistic using Newey-West (HAC) standard errors, lag L = floor(4 (T / 100)^(2/9)).
The same regression on the ACTIVE return (portfolio - benchmark, no T-bill) shows whether any
difference from the benchmark is explained by size, value or momentum tilts.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

FACTORS = ["mkt_rf", "smb", "hml", "mom"]


def load_factors(con, start, end) -> pd.DataFrame:
    """Daily factors from the store (``con``: a DuckDB connection; read-only use)."""
    f = con.execute("SELECT date, mkt_rf, smb, hml, mom, rf FROM factors_daily WHERE date BETWEEN ? AND ? ORDER BY date",
                    [pd.Timestamp(start), pd.Timestamp(end)]).df()
    return f.set_index(pd.DatetimeIndex(f.pop("date")))


def newey_west_lag(t: int) -> int:
    return int(math.floor(4 * (t / 100) ** (2 / 9)))


def ols_newey_west(y: np.ndarray, x: np.ndarray, lag: int | None = None) -> tuple[np.ndarray, np.ndarray, float]:
    """(coefficients, HAC standard errors, R^2). ``x`` without the constant (added here, first)."""
    t = len(y)
    X = np.column_stack([np.ones(t), x])
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    e = y - X @ beta
    lag = newey_west_lag(t) if lag is None else lag
    xe = X * e[:, None]
    s = xe.T @ xe
    for k in range(1, lag + 1):
        w = 1 - k / (lag + 1)
        g = xe[k:].T @ xe[:-k]
        s += w * (g + g.T)
    cov = xtx_inv @ s @ xtx_inv
    r2 = 1 - (e @ e) / (((y - y.mean()) ** 2).sum()) if t > 1 else float("nan")
    return beta, np.sqrt(np.diag(cov)), float(r2)


def carhart(returns: pd.Series, factors: pd.DataFrame, active: bool = False) -> dict:
    """``returns``: daily returns. ``active=True``: ``returns`` is already portfolio - benchmark."""
    d = pd.concat([returns.rename("r"), factors], axis=1, join="inner").dropna()
    if len(d) < 60:
        return {"n_days": len(d)}
    y = (d["r"] if active else d["r"] - d["rf"]).to_numpy()
    x = d[FACTORS].to_numpy()
    if np.linalg.matrix_rank(np.column_stack([np.ones(len(x)), x])) < len(FACTORS) + 1:
        return {"n_days": len(d), "note": "factor data do not vary enough for a regression"}
    beta, se, r2 = ols_newey_west(y, x)
    out = {"n_days": len(d), "alpha_annual": float(beta[0] * 252), "alpha_t": float(beta[0] / se[0]), "r2": r2}
    for i, f in enumerate(FACTORS, start=1):
        out[f"beta_{f}"] = float(beta[i])
        out[f"t_{f}"] = float(beta[i] / se[i])
    return out
