"""Custom cap-weighted benchmark of the run's own companies (D41)."""
import numpy as np
import pandas as pd
import pytest

from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway
from quantagents.eval.benchmarks import benchmark_weights, cap_index_returns, custom_cap_index

COMPANIES = ["AAA", "BBB", "GOOGL"]


@pytest.fixture(scope="module")
def gw(synthetic_db):
    g = Gateway(synthetic_db[1])
    yield g
    g.close()


def test_hand_computed_two_stock_example():
    days = pd.DatetimeIndex(["2021-01-04", "2021-01-05", "2021-01-06"])
    w = pd.DataFrame({"A": [0.6, 0.5, 0.7], "B": [0.4, 0.5, 0.3]}, index=days)
    r = pd.DataFrame({"A": [0.0, 0.10, 0.00], "B": [0.0, -0.05, 0.10]}, index=days)
    out = cap_index_returns(w, r)
    # 5 Jan: 0.6 x 10% + 0.4 x -5% = 4%;  6 Jan: 0.5 x 0% + 0.5 x 10% = 5%
    assert out.tolist() == pytest.approx([0.04, 0.05])
    assert list(out.index) == list(days[1:])


def test_weights_sum_to_one_every_day(gw):
    ci = custom_cap_index(gw, COMPANIES, "2015-01-02", "2015-12-31")
    assert np.allclose(ci.weights.sum(axis=1), 1.0)
    assert ci.missing.empty and len(ci.returns) == len(ci.weights)


def test_matches_the_gateway_by_hand_on_one_day(gw):
    ci = custom_cap_index(gw, ["AAA", "BBB"], "2015-03-02", "2015-03-31")
    d, prev = pd.Timestamp("2015-03-10"), pd.Timestamp("2015-03-09")
    w = gw.get_index_weights(cal.close_utc(prev)).set_index("company_id")["weight"][["AAA", "BBB"]]
    w = w / w.sum()
    p = gw.get_prices(["AAA", "BBB"], cal.close_utc(d), lookback_days=3)
    r = p[p["date"] == d].set_index("company_id")["ret"]
    assert ci.returns.loc[d] == pytest.approx(float((w * r).sum()))


def test_no_weight_uses_data_after_the_previous_close(gw, synthetic_db):
    """The index up to a date is the same when the store is rebuilt as if that date were today."""
    end = "2015-06-30"
    full = custom_cap_index(gw, COMPANIES, "2015-01-02", "2015-12-31")
    cut = Gateway(synthetic_db[2](cal.close_utc(end)))
    try:
        part = custom_cap_index(cut, COMPANIES, "2015-01-02", end)
    finally:
        cut.close()
    pd.testing.assert_series_equal(full.returns.loc[:end], part.returns)
    pd.testing.assert_frame_equal(full.weights.loc[:end], part.weights)


def test_benchmark_weight_vector_sums_to_one(gw):
    w = benchmark_weights(gw, COMPANIES, cal.close_utc("2015-03-02"))
    assert w.sum() == pytest.approx(1.0) and set(w.index) == set(COMPANIES)


def test_company_that_left_drops_out_and_rest_renormalise(gw):
    ci = custom_cap_index(gw, ["AAA", "OLD"], "2015-05-01", "2015-07-31")
    after = ci.weights.loc["2015-06-15"]
    assert after["OLD"] == 0.0 and after["AAA"] == pytest.approx(1.0)
    assert not ci.missing.empty
