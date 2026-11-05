"""News timing (brief §4): an article published after the close counts from the next trading day."""
import pandas as pd
import pytest

from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway


@pytest.fixture(scope="module")
def gw(synthetic_db):
    g = Gateway(synthetic_db[1])
    yield g
    g.close()


def ids(gw, day):
    return set(gw.get_news(["AAA"], cal.close_utc(day), window_days=5)["id"])


def test_before_and_after_the_close(gw):
    assert 1 in ids(gw, "2015-03-02")          # 15:59 ET
    assert 2 not in ids(gw, "2015-03-02")      # 16:01 ET -> after the close
    assert 2 in ids(gw, "2015-03-03")          # ... usable the next trading day


def test_daylight_saving_switch_day(gw):
    # 9 Mar 2015 is the first trading day on summer time: close = 20:00 UTC, news at 15:30 ET = 19:30 UTC
    assert 3 in ids(gw, "2015-03-09")


def test_utc_after_midnight_is_still_previous_day_in_new_york(gw):
    # 19:30 ET Friday 6 Mar = 00:30 UTC Saturday: after Friday's close, before Monday's
    assert 4 not in ids(gw, "2015-03-06") and 4 in ids(gw, "2015-03-09")


def test_weekend_news_counts_from_monday(gw):
    assert 5 in ids(gw, "2015-03-09") and 5 not in ids(gw, "2015-03-06")


def test_early_close_day(gw):
    # Black Friday 27 Nov 2015 closes at 1 pm ET: 12:30 counts that day, 13:30 only on Monday
    assert 7 in ids(gw, "2015-11-27") and 6 not in ids(gw, "2015-11-27")
    assert 6 in ids(gw, "2015-11-30")
