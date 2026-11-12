"""Baseline optimizer: proposed multipliers -> the nearest weights that satisfy every constraint
(brief section 7: "projects these onto the constraints, minimizing distance to the proposed weights").

Problem (a quadratic programme):  minimise sum_i (w_i - t_i)^2  where t_i = multiplier_i x b_i,
subject to  lower_i <= w_i <= upper_i,  sector totals within their band,  sum_i w_i = 1.

Because every company is in exactly one sector, the exact solution has a simple form (from the
optimality conditions): w_i = clip(t_i + mu_s, lower_i, upper_i), one shift mu_s per sector; all
sectors whose band is not binding share the same shift nu. Both shifts are found by bisection on
monotone functions, so the result is exact to machine precision, deterministic, and needs only
numpy. No LLM is involved: Python does all the maths.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quantagents.portfolio.constraints import ConstraintSet

ITER = 200


def _shift_to_sum(t: np.ndarray, lo: np.ndarray, hi: np.ndarray, total: float) -> np.ndarray:
    """w = clip(t + mu, lo, hi) with sum(w) = total (total within [sum lo, sum hi])."""
    if total <= lo.sum():
        return lo.copy()
    if total >= hi.sum():
        return hi.copy()
    a, b = float((lo - t).min()) - 1.0, float((hi - t).max()) + 1.0
    for _ in range(ITER):
        mid = 0.5 * (a + b)
        if np.clip(t + mid, lo, hi).sum() < total:
            a = mid
        else:
            b = mid
    return np.clip(t + 0.5 * (a + b), lo, hi)


def project(cs: ConstraintSet, target: np.ndarray) -> np.ndarray:
    """The feasible weights nearest to ``target`` (Euclidean distance)."""
    t = np.asarray(target, dtype=float)
    groups = list(cs.sector_index().values())
    s_lo = [max(cs.sector_lower[k], cs.lower[g].sum()) for k, g in enumerate(groups)]
    s_hi = [min(cs.sector_upper[k], cs.upper[g].sum()) for k, g in enumerate(groups)]

    def totals(nu: float) -> list[float]:
        return [min(max(np.clip(t[g] + nu, cs.lower[g], cs.upper[g]).sum(), s_lo[k]), s_hi[k])
                for k, g in enumerate(groups)]

    a, b = float((cs.lower - t).min()) - 1.0, float((cs.upper - t).max()) + 1.0
    for _ in range(ITER):
        mid = 0.5 * (a + b)
        if sum(totals(mid)) < 1.0:
            a = mid
        else:
            b = mid
    w = np.zeros_like(t)
    for k, g in enumerate(groups):
        tot = totals(0.5 * (a + b))[k]
        w[g] = _shift_to_sum(t[g], cs.lower[g], cs.upper[g], tot)
    # bisection leaves ~1e-16 of slack; put it on the company with the most room (stays within bounds)
    gap = 1.0 - w.sum()
    if abs(gap) > 0:
        room = (cs.upper - w) if gap > 0 else (w - cs.lower)
        i = int(np.argmax(room))
        w[i] += gap
    return w


def weights_from_multipliers(cs: ConstraintSet, multipliers: pd.Series | dict | None = None) -> pd.Series:
    """Multipliers of benchmark weight per company (missing = 1.0, i.e. no view) -> constrained weights."""
    m = pd.Series(1.0, index=list(cs.companies))
    if multipliers is not None:
        given = pd.Series(multipliers, dtype=float)
        m.update(given[given.index.isin(m.index)])
    w = project(cs, m.to_numpy() * cs.bench)
    return pd.Series(w, index=list(cs.companies))
