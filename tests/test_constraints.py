"""Constraints and the baseline projection optimizer."""
import numpy as np
import pandas as pd
import pytest

from quantagents.portfolio.baseline_opt import project, weights_from_multipliers
from quantagents.portfolio.constraints import ConstraintSet, InfeasibleError


def random_set(seed, n=20, n_sectors=5, band=2.0):
    rng = np.random.default_rng(seed)
    b = pd.Series(rng.lognormal(0, 1, n), index=[f"C{i:02d}" for i in range(n)])
    b /= b.sum()
    sec = pd.Series([f"S{i % n_sectors}" for i in range(n)], index=b.index)
    return ConstraintSet.build(b, sec, 0.0, 2.0, band)


def objective(w, t):
    return float(((w - t) ** 2).sum())


@pytest.mark.parametrize("seed", range(30))
def test_output_always_satisfies_every_constraint(seed):
    cs = random_set(seed)
    rng = np.random.default_rng(1000 + seed)
    m = pd.Series(rng.uniform(0, 3, len(cs.companies)), index=list(cs.companies))     # even > 2x proposed
    w = weights_from_multipliers(cs, m)
    assert cs.violations(w.to_numpy()) == []


@pytest.mark.parametrize("seed", range(15))
def test_projection_is_the_nearest_feasible_point(seed):
    """Optimality check: no feasible point on the way to the benchmark, or to another feasible
    portfolio, is closer to the target (the feasible set is convex)."""
    cs = random_set(seed)
    rng = np.random.default_rng(seed)
    t = rng.uniform(0, 2.5, len(cs.companies)) * cs.bench
    w = project(cs, t)
    others = [cs.bench] + [project(cs, rng.uniform(0, 2, len(cs.companies)) * cs.bench) for _ in range(5)]
    for o in others:
        for lam in (0.01, 0.1, 0.5, 0.9):
            assert objective(w, t) <= objective((1 - lam) * w + lam * o, t) + 1e-12


def test_all_multipliers_one_gives_the_benchmark():
    cs = random_set(3)
    w = weights_from_multipliers(cs)
    np.testing.assert_allclose(w.to_numpy(), cs.bench, atol=1e-12)


def test_missing_multiplier_means_no_view():
    cs = random_set(4)
    c0 = cs.companies[0]
    w = weights_from_multipliers(cs, {c0: 1.0})
    np.testing.assert_allclose(w.to_numpy(), cs.bench, atol=1e-12)


def test_unconstrained_case_is_a_uniform_shift():
    b = pd.Series([0.25, 0.25, 0.25, 0.25], index=list("ABCD"))
    cs = ConstraintSet.build(b, pd.Series("S", index=b.index), 0.0, 2.0, 100.0)
    w = project(cs, np.array([0.30, 0.30, 0.20, 0.20]))      # sums to 1 already, inside the box
    np.testing.assert_allclose(w, [0.30, 0.30, 0.20, 0.20], atol=1e-12)
    w = project(cs, np.array([0.30, 0.30, 0.30, 0.30]))      # sums to 1.2: shift each by -0.05
    np.testing.assert_allclose(w, [0.25, 0.25, 0.25, 0.25], atol=1e-12)


def test_sector_band_binds():
    b = pd.Series([0.25, 0.25, 0.25, 0.25], index=list("ABCD"))
    sec = pd.Series(["X", "X", "Y", "Y"], index=b.index)
    cs = ConstraintSet.build(b, sec, 0.0, 2.0, 2.0)
    w = weights_from_multipliers(cs, {"A": 2.0, "B": 2.0, "C": 0.0, "D": 0.0})
    assert w[["A", "B"]].sum() == pytest.approx(0.52) and w[["C", "D"]].sum() == pytest.approx(0.48)


def test_infeasible_settings_give_a_clear_error_and_are_not_loosened():
    b = pd.Series([0.5, 0.5], index=["A", "B"])
    sec = pd.Series(["X", "Y"], index=b.index)
    cs = ConstraintSet.build(b, sec, 0.0, 2.0, 2.0)
    bad = ConstraintSet(cs.companies, cs.bench, cs.sectors, cs.lower, cs.upper * 0.2, cs.sector_names,
                        cs.sector_bench, cs.sector_lower, cs.sector_upper)
    with pytest.raises(InfeasibleError, match="NOT loosened"):
        bad.assert_feasible()


def test_twenty_stock_benchmark_with_two_point_bands_is_feasible(synthetic_db):
    """D41: the same-N benchmark with +-2 pp bands is always feasible (it satisfies them itself)."""
    from quantagents.data import calendar as cal
    from quantagents.data.gateway import Gateway
    g = Gateway(synthetic_db[1])
    try:
        for day in ("2015-01-02", "2015-06-01", "2015-12-01"):
            w = g.get_index_weights(cal.close_utc(day)).set_index("company_id")
            cs = ConstraintSet.build(w["weight"], w["sector"], 0.0, 2.0, 2.0)
            assert cs.violations(cs.bench) == []
    finally:
        g.close()


# ---- relative distance (multiplier units), the option found necessary in the P4 pilot
@pytest.mark.parametrize("seed", range(15))
def test_relative_projection_is_feasible_and_nearest_in_multiplier_units(seed):
    cs = random_set(seed)
    rng = np.random.default_rng(seed)
    t = rng.uniform(0, 2.5, len(cs.companies)) * cs.bench
    w = project(cs, t, "relative")
    assert cs.violations(w) == []
    rel = lambda x: float((((x - t) ** 2) / cs.bench).sum())  # noqa: E731
    others = [cs.bench] + [project(cs, rng.uniform(0, 2, len(cs.companies)) * cs.bench, "relative") for _ in range(5)]
    for o in others:
        for lam in (0.01, 0.1, 0.5, 0.9):
            assert rel(w) <= rel((1 - lam) * w + lam * o) + 1e-12


def test_relative_projection_moves_every_multiplier_by_the_same_amount():
    """Pilot case (2 Mar 2015): a small company must not be pushed to 2x by a correction made for big ones."""
    b = pd.Series({"AAPL": 0.5624, "MSFT": 0.2693, "NVDA": 0.0092, "AMZN": 0.1340, "AAL": 0.0251})
    b /= b.sum()
    sec = pd.Series({"AAPL": "IT", "MSFT": "IT", "NVDA": "IT", "AMZN": "CD", "AAL": "IND"})
    m = {"AAPL": 1.0, "MSFT": 0.75, "NVDA": 1.0, "AMZN": 0.75, "AAL": 0.0}
    cs = ConstraintSet.build(b, sec, 0.0, 2.0, 2.0)
    absolute = weights_from_multipliers(cs, m, "absolute") / b
    relative = weights_from_multipliers(cs, m, "relative") / b
    assert absolute["NVDA"] > 1.9                                  # the P3 behaviour
    assert relative["NVDA"] < 1.3 and relative["AAL"] < absolute["AAL"]
    it = relative[["AAPL", "MSFT", "NVDA"]] - pd.Series({"AAPL": 1.0, "MSFT": 0.75, "NVDA": 1.0})
    assert it.max() - it.min() < 1e-9                              # same multiplier shift inside the sector
    assert cs.violations((relative * b).to_numpy()) == []
