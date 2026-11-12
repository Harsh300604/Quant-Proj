"""Black-Litterman for the enhanced variant (brief section 7, main plan Phase 7). numpy only.

Units are MONTHLY (the rebalance frequency):
- covariance: Ledoit-Wolf shrinkage of the last 252 daily total returns, x 21 to a month;
- prior (market-implied) returns: pi = delta x Sigma x w_bench, with the benchmark weights on date t
  (delta = 2.5, configurable);
- views are absolute, one per rated company: P = that company's row of the identity matrix and
  Q = pi_i + (3-month expected excess return from the rating table) / 3. So a "hold" view says
  "the market-implied return is right", and "buy" says "3% more than that over 3 months";
- Omega by Idzorek's method from the committee's confidence c in [0, 1]:
  omega_k = tau x (1 - c) / c x P_k Sigma P_k' (c = 1: the view is taken as certain; c = 0: ignored);
- posterior mean mu = pi + tau Sigma P' (P tau Sigma P' + Omega)^-1 (Q - P pi).

Weights: the mean-variance portfolio  max mu'w - delta/2 w' Sigma w  under the SAME constraint set as
the baseline (0x-2x of benchmark weight, sector bands, sum 1, long-only), solved exactly by
projected gradient steps with the baseline optimizer's projection. Because pi is defined from the
benchmark, no views give mu = pi and the optimum is exactly the benchmark ("no view = market
weight"). The prior covariance is used in the optimizer so that property holds exactly.
LLMs never touch any of this: they give a rating and a confidence; Python does the rest.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quantagents.portfolio.baseline_opt import project
from quantagents.portfolio.constraints import ConstraintSet

DAYS_PER_MONTH = 21
MAX_ITER = 20000
TOL = 1e-13


def ledoit_wolf(returns: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit & Wolf (2004) shrinkage towards a scaled identity. ``returns``: days x assets.
    Returns (covariance, shrinkage intensity in [0, 1])."""
    x = np.asarray(returns, dtype=float)
    n, p = x.shape
    x = x - x.mean(axis=0)
    s = x.T @ x / n
    mu = np.trace(s) / p
    x2 = x ** 2
    beta_ = float(np.sum(x2.T @ x2))
    delta_ = float(np.sum(s ** 2))
    beta = (beta_ / n - delta_) / (p * n)
    delta = (delta_ - 2.0 * mu * np.trace(s) + p * mu ** 2) / p
    beta = min(beta, delta)
    shrink = 0.0 if beta <= 0 or delta <= 0 else beta / delta
    return (1.0 - shrink) * s + shrink * mu * np.eye(p), float(shrink)


def monthly_covariance(daily: pd.DataFrame, companies: list[str]) -> np.ndarray:
    r = daily.reindex(columns=companies).iloc[-252:].fillna(0.0).to_numpy()
    cov, _ = ledoit_wolf(r)
    return cov * DAYS_PER_MONTH


def implied_returns(sigma: np.ndarray, w_bench: np.ndarray, delta: float) -> np.ndarray:
    return delta * sigma @ w_bench


def idzorek_omega(P: np.ndarray, sigma: np.ndarray, tau: float, confidence: np.ndarray) -> np.ndarray:
    c = np.clip(np.asarray(confidence, dtype=float), 1e-9, 1.0)
    var = np.einsum("ij,jk,ik->i", P, sigma, P)
    return np.diag(tau * (1.0 - c) / c * var)


def posterior(pi: np.ndarray, sigma: np.ndarray, P: np.ndarray, Q: np.ndarray, omega: np.ndarray,
              tau: float) -> np.ndarray:
    if len(Q) == 0:
        return pi.copy()
    ts = tau * sigma
    m = P @ ts @ P.T + omega
    return pi + ts @ P.T @ np.linalg.solve(m, Q - P @ pi)


def optimise(cs: ConstraintSet, mu: np.ndarray, sigma: np.ndarray, delta: float) -> np.ndarray:
    """max mu'w - delta/2 w'Sigma w over the constraint set (exact projected gradient, FISTA)."""
    lip = delta * float(np.linalg.eigvalsh(sigma).max())
    step = 1.0 / lip if lip > 0 else 1.0
    w = y = cs.bench.copy()
    t = 1.0
    for _ in range(MAX_ITER):
        w_new = project(cs, y + step * (mu - delta * sigma @ y), "absolute")
        t_new = 0.5 * (1 + np.sqrt(1 + 4 * t * t))
        y = w_new + (t - 1) / t_new * (w_new - w)
        if np.abs(w_new - w).max() < TOL:
            w = w_new
            break
        w, t = w_new, t_new
    return w


def bl_weights(cs: ConstraintSet, sigma: np.ndarray, views: dict[str, tuple[str, float]], rating_table: dict,
               delta: float, tau: float) -> tuple[pd.Series, dict]:
    """``views``: {company: (rating, confidence)}. Returns (weights, details for the transcript)."""
    ids = list(cs.companies)
    pi = implied_returns(sigma, cs.bench, delta)
    rated = [(c, r, float(conf)) for c, (r, conf) in views.items() if c in ids and float(conf) > 0]
    P = np.zeros((len(rated), len(ids)))
    Q = np.zeros(len(rated))
    for k, (c, r, _) in enumerate(rated):
        i = ids.index(c)
        P[k, i] = 1.0
        Q[k] = pi[i] + rating_table[r] / 3.0
    omega = idzorek_omega(P, sigma, tau, np.array([c for _, _, c in rated])) if rated else np.zeros((0, 0))
    mu = posterior(pi, sigma, P, Q, omega, tau)
    w = optimise(cs, mu, sigma, delta)
    details = {"prior_monthly": dict(zip(ids, pi)), "posterior_monthly": dict(zip(ids, mu)), "views_used": len(rated)}
    return pd.Series(w, index=ids), details
