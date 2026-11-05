import pandas as pd
import pytest

from quantagents.data import calendar as cal


def test_rebalance_dates_are_first_trading_days():
    assert [d.strftime("%Y-%m-%d") for d in cal.rebalance_dates("2015-01-01", "2015-06-30")] == [
        "2015-01-02", "2015-02-02", "2015-03-02", "2015-04-01", "2015-05-01", "2015-06-01"]


def test_close_times_follow_daylight_saving_and_early_closes():
    assert cal.close_utc("2015-03-06") == pd.Timestamp("2015-03-06 21:00", tz="UTC")   # EST: 16:00 = 21:00 UTC
    assert cal.close_utc("2015-03-09") == pd.Timestamp("2015-03-09 20:00", tz="UTC")   # EDT: 16:00 = 20:00 UTC
    assert cal.close_utc("2015-11-27") == pd.Timestamp("2015-11-27 18:00", tz="UTC")   # 1 pm early close


def test_holidays_and_next_trading_day():
    assert not cal.is_trading_day("2015-07-03")      # Independence Day observed
    assert cal.next_trading_day("2015-07-02") == pd.Timestamp("2015-07-06")
    assert cal.previous_trading_day("2015-01-02") == pd.Timestamp("2014-12-31")


def test_naive_timestamps_rejected():
    with pytest.raises(ValueError, match="time zone"):
        cal.require_utc(pd.Timestamp("2015-01-02 21:00"))


def test_first_close_at_or_after():
    assert cal.first_close_at_or_after(pd.Timestamp("2015-03-07 16:00", tz="UTC")) == cal.close_utc("2015-03-09")
    assert cal.first_close_at_or_after(cal.close_utc("2015-03-09")) == cal.close_utc("2015-03-09")
