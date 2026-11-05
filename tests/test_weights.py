import numpy as np
import pandas as pd
import pytest

from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway


@pytest.fixture(scope="module")
def gw(synthetic_db):
    g = Gateway(synthetic_db[1])
    yield g
    g.close()


@pytest.mark.parametrize("day", ["2014-06-02", "2015-01-02", "2015-06-01", "2015-12-01"])
def test_weights_sum_to_one_and_only_members(gw, day):
    w = gw.get_index_weights(cal.close_utc(day))
    assert w["weight"].sum() == pytest.approx(1.0)
    assert set(w["company_id"]) <= set(gw.get_universe(cal.close_utc(day))["company_id"])


def test_no_weight_before_first_shares_filing(gw):
    # first filings are accepted ~32 days after the first quarter end (29 Mar 2014)
    assert gw.get_index_weights(cal.close_utc("2014-03-03")).empty
    assert not gw.get_index_weights(cal.close_utc("2014-05-02")).empty


def test_market_cap_uses_actual_traded_price_across_a_split(gw):
    """AAA splits 2-for-1 on 1 June 2015. Yahoo's close is pre-scaled, raw_close is the actual price;
    market cap (actual price x shares) must not halve or double at the split."""
    before = gw.get_index_weights(cal.close_utc("2015-05-29")).set_index("company_id").loc["AAA", "mcap"]
    after = gw.get_index_weights(cal.close_utc("2015-06-01")).set_index("company_id").loc["AAA", "mcap"]
    assert 0.8 < after / before < 1.2
    p = gw.get_prices(["AAA"], cal.close_utc("2015-06-02"), lookback_days=10).set_index("date")
    assert p.loc[pd.Timestamp("2015-05-29"), "raw_close"] == pytest.approx(2 * p.loc[pd.Timestamp("2015-05-29"), "close"])


def test_two_share_classes_summed(gw):
    w = gw.get_index_weights(cal.close_utc("2015-03-02")).set_index("company_id")
    p = gw.get_prices(["GOOGL"], cal.close_utc("2015-03-02"), lookback_days=3).iloc[-1]
    assert w.loc["GOOGL", "mcap"] == pytest.approx(p["raw_close"] * 500.0)      # 400 + 100 shares


def test_total_return_includes_dividends(gw):
    p = gw.get_prices(["BBB"], cal.close_utc("2014-12-31"), lookback_days=400)
    d = p[p["dividends"] > 0].iloc[1]
    prev = p[p["date"] < d["date"]].iloc[-1]
    assert d["ret"] == pytest.approx((d["close"] + d["dividends"]) / prev["close"] - 1)
