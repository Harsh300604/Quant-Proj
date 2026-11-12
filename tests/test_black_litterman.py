"""Black-Litterman: no views = benchmark exactly; views move weights the right way, more with more
confidence; Idzorek limits; a hand-worked 3-asset example; constraints always hold."""
import numpy as np
import pandas as pd
import pytest

from quantagents.portfolio.black_litterman import (bl_weights, idzorek_omega, implied_returns, ledoit_wolf,
                                                   optimise, posterior)
from quantagents.portfolio.constraints import ConstraintSet

TABLE = {"strong_sell": -0.06, "sell": -0.03, "hold": 0.0, "buy": 0.03, "strong_buy": 0.06}


def setup(seed=0, n=8):
    rng = np.random.default_rng(seed)
    ids = [f"C{i}" for i in range(n)]
    b = pd.Series(rng.lognormal(0, 0.6, n), index=ids)
    b /= b.sum()
    sec = pd.Series(["IT", "IT", "IT", "HC", "HC", "CS", "CS", "CD"][:n], index=ids)
    f = rng.normal(0, 0.01, (300, 1))
    r = 0.8 * f + rng.normal(0, 0.012, (300, n))
    sigma, _ = ledoit_wolf(r)
    return ConstraintSet.build(b, sec, 0.0, 2.0, 2.0), sigma * 21


def test_no_views_gives_the_benchmark_exactly():
    cs, sigma = setup()
    w, d = bl_weights(cs, sigma, {}, TABLE, 2.5, 0.05)
    assert np.abs(w.to_numpy() - cs.bench).max() < 1e-12 and d["views_used"] == 0
    w2, _ = bl_weights(cs, sigma, {"C0": ("buy", 0.0)}, TABLE, 2.5, 0.05)     # zero confidence = no view
    assert np.abs(w2.to_numpy() - cs.bench).max() < 1e-12


def test_buy_raises_sell_lowers_and_confidence_scales():
    cs, sigma = setup()
    base = pd.Series(cs.bench, index=list(cs.companies))
    lo, _ = bl_weights(cs, sigma, {"C5": ("buy", 0.2)}, TABLE, 2.5, 0.05)
    hi, _ = bl_weights(cs, sigma, {"C5": ("buy", 0.8)}, TABLE, 2.5, 0.05)
    assert base["C5"] < lo["C5"] < hi["C5"]
    s, _ = bl_weights(cs, sigma, {"C5": ("sell", 0.5)}, TABLE, 2.5, 0.05)
    assert s["C5"] < base["C5"]
    for w in (lo, hi, s):
        assert cs.violations(w.to_numpy()) == []


def test_idzorek_limits():
    sigma = np.array([[0.004, 0.001], [0.001, 0.003]])
    P = np.array([[1.0, 0.0]])
    assert idzorek_omega(P, sigma, 0.05, np.array([1.0]))[0, 0] == pytest.approx(0.0, abs=1e-15)
    assert idzorek_omega(P, sigma, 0.05, np.array([0.5]))[0, 0] == pytest.approx(0.05 * 0.004)
    pi = implied_returns(sigma, np.array([0.6, 0.4]), 2.5)
    certain = posterior(pi, sigma, P, np.array([0.02]), idzorek_omega(P, sigma, 0.05, np.array([1.0])), 0.05)
    assert certain[0] == pytest.approx(0.02, abs=1e-12)           # confidence 1: the view holds exactly


def test_hand_worked_three_asset_example():
    """sigma diagonal, one view at 50% confidence: posterior moves exactly half way for that asset."""
    sigma = np.diag([0.004, 0.009, 0.0016])
    w = np.array([0.5, 0.3, 0.2])
    pi = implied_returns(sigma, w, 2.5)
    assert pi == pytest.approx([2.5 * 0.002, 2.5 * 0.0027, 2.5 * 0.00032])
    P = np.array([[0.0, 1.0, 0.0]])
    Q = np.array([pi[1] + 0.01])
    mu = posterior(pi, sigma, P, Q, idzorek_omega(P, sigma, 0.05, np.array([0.5])), 0.05)
    assert mu[1] == pytest.approx(pi[1] + 0.005) and mu[0] == pytest.approx(pi[0]) and mu[2] == pytest.approx(pi[2])


def test_optimiser_matches_the_unconstrained_solution_when_nothing_binds():
    sigma = np.diag([0.004, 0.009, 0.0016]) * 1.0
    b = pd.Series([0.4, 0.35, 0.25], index=list("ABC"))
    cs = ConstraintSet.build(b, pd.Series(["X", "X", "X"], index=list("ABC")), 0.0, 2.0, 50.0)
    mu = implied_returns(sigma, b.to_numpy(), 2.5) + np.array([0.0005, -0.0005, 0.0])
    w = optimise(cs, mu, sigma, 2.5)
    # with only the budget constraint binding: w = (delta S)^-1 (mu - lambda 1), sum 1
    inv = np.linalg.inv(2.5 * sigma)
    lam = (inv @ mu).sum() - 1
    lam /= inv.sum()
    assert w == pytest.approx(inv @ (mu - lam), abs=1e-9)


def test_ledoit_wolf_is_a_valid_covariance():
    rng = np.random.default_rng(3)
    cov, s = ledoit_wolf(rng.normal(0, 0.01, (60, 20)))
    assert 0 <= s <= 1 and np.linalg.eigvalsh(cov).min() > 0
    f = rng.normal(0, 0.02, (20000, 1))
    data = np.hstack([f, 0.5 * f + rng.normal(0, 0.005, (20000, 1)), rng.normal(0, 0.03, (20000, 1))])
    _, s2 = ledoit_wolf(data)
    assert s2 < 0.05                         # lots of data, far from an identity matrix: little shrinkage
    _, s3 = ledoit_wolf(rng.normal(0, 0.01, (40, 3)))
    assert s3 > s2                           # truth IS a scaled identity and data are few: shrink more
