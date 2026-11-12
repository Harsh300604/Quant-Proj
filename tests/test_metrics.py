"""Metrics against hand calculations; factor regression recovers known numbers; bootstrap is sane."""
import math

import numpy as np
import pandas as pd
import pytest

from quantagents.eval.factors import carhart, newey_west_lag, ols_newey_west
from quantagents.eval.metrics import (block_bootstrap, calendar_returns, cagr, confidence_intervals, enb, entropy,
                                      max_drawdown, performance, sharpe)


def test_simple_numbers_by_hand():
    idx = pd.to_datetime(["2021-12-30", "2021-12-31", "2022-01-03", "2022-01-04"])
    nav = pd.Series([1.0, 1.1, 0.99, 1.089], index=idx)
    assert max_drawdown(nav) == pytest.approx(0.99 / 1.1 - 1)
    assert calendar_returns(nav) == {2021: pytest.approx(0.1), 2022: pytest.approx(1.089 / 1.1 - 1)}
    days = pd.bdate_range("2020-01-01", periods=253)
    up = pd.Series(1.0005 ** np.arange(253), index=days)
    assert cagr(up) == pytest.approx(up.iloc[-1] ** (365.25 / (days[-1] - days[0]).days) - 1)
    r = pd.Series([0.01, -0.02, 0.03, 0.0])
    assert sharpe(r) == pytest.approx(r.mean() / r.std() * math.sqrt(252))


def test_active_metrics_and_rf():
    days = pd.bdate_range("2021-01-01", periods=300)
    rng = np.random.default_rng(0)
    b = pd.Series((1 + rng.normal(0.0004, 0.01, 300)).cumprod(), index=days)
    p = b * 1.0                                                     # identical portfolio
    m = performance(p, None, b)
    assert m["tracking_error"] == pytest.approx(0, abs=1e-12) and m["active_return"] == pytest.approx(0, abs=1e-12)
    rf = pd.Series(0.0001, index=days)
    assert performance(p, rf)["sharpe"] < performance(p)["sharpe"]


def test_entropy_and_enb():
    assert entropy(np.ones(4) / 4) == pytest.approx(math.log(4))
    assert enb(np.ones(3) / 3, np.eye(3)) == pytest.approx(3.0)          # 3 independent equal bets
    one_factor = np.full((3, 3), 1.0) + 1e-9 * np.eye(3)
    assert enb(np.ones(3) / 3, one_factor) == pytest.approx(1.0, abs=1e-6)  # all the same bet


def test_carhart_recovers_alpha_and_betas():
    rng = np.random.default_rng(1)
    days = pd.bdate_range("2019-01-01", periods=1500)
    f = pd.DataFrame(rng.normal(0, 0.01, (1500, 4)), index=days, columns=["mkt_rf", "smb", "hml", "mom"])
    f["rf"] = 0.0001
    r = f["rf"] + 0.0002 + 1.2 * f["mkt_rf"] - 0.3 * f["smb"] + 0.1 * f["hml"] + 0.05 * f["mom"] \
        + rng.normal(0, 0.002, 1500)
    out = carhart(r, f)
    assert out["alpha_annual"] == pytest.approx(0.0002 * 252, abs=0.01)
    assert out["beta_mkt_rf"] == pytest.approx(1.2, abs=0.01) and out["beta_smb"] == pytest.approx(-0.3, abs=0.01)
    assert out["alpha_t"] > 2


def test_newey_west_equals_white_at_lag_zero_and_lag_rule():
    rng = np.random.default_rng(2)
    x = rng.normal(size=(200, 1))
    y = 1 + 2 * x[:, 0] + rng.normal(size=200)
    b, se, _ = ols_newey_west(y, x, lag=0)
    X = np.column_stack([np.ones(200), x])
    e = y - X @ b
    inv = np.linalg.inv(X.T @ X)
    white = np.sqrt(np.diag(inv @ (X.T * e ** 2) @ X @ inv))
    assert se == pytest.approx(white)
    assert newey_west_lag(756) == 6


def test_bootstrap_interval_contains_the_estimate_and_is_deterministic():
    days = pd.bdate_range("2021-01-01", periods=500)
    rng = np.random.default_rng(3)
    b = pd.Series((1 + rng.normal(0.0004, 0.01, 500)).cumprod(), index=days)
    p = pd.Series((1 + b.pct_change().fillna(0) + rng.normal(0.0001, 0.002, 500)).cumprod(), index=days)
    a = confidence_intervals(p, b)
    c = confidence_intervals(p, b)
    assert a == c
    lo, hi = a["sharpe_ci"]
    assert lo < sharpe(p.pct_change().dropna()) < hi
    assert math.isnan(block_bootstrap([pd.Series([0.1, 0.2])], sharpe)[0])
