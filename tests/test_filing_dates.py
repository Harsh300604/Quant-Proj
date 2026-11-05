"""Fundamentals count from the SEC acceptance time (never the period end), restatements included."""
import pandas as pd
import pytest

from quantagents.data import calendar as cal
from quantagents.data.etl import edgar_acceptance_to_utc
from quantagents.data.gateway import Gateway


@pytest.fixture(scope="module")
def gw(synthetic_db):
    g = Gateway(synthetic_db[1])
    yield g
    g.close()


def rev(gw, as_of, period_end):
    f = gw.get_fundamentals(["AAA"], as_of)
    q = f[(f["metric"] == "revenue") & (f["period_type"] == "quarter")]
    return q[q["period_end"] == period_end]


def test_acceptance_clock_is_read_as_eastern_time():
    # '16:31 Z' as printed by EDGAR is 16:31 New York time = 21:31 UTC in winter (D29, conservative)
    assert edgar_acceptance_to_utc("2015-01-28T16:31:00.000Z") == pd.Timestamp("2015-01-28 21:31", tz="UTC")


def test_filing_accepted_after_close_is_invisible_that_day(gw):
    # quarter ended 27 Dec 2014; 10-Q accepted 28 Jan 2015 16:31 ET (after the 16:00 close)
    assert rev(gw, cal.close_utc("2015-01-28"), "2014-12-27").empty
    assert not rev(gw, cal.close_utc("2015-01-29"), "2014-12-27").empty


def test_not_visible_at_period_end(gw):
    f = gw.get_fundamentals(["AAA"], cal.close_utc("2014-12-31"))
    q = f[(f["metric"] == "revenue") & (f["period_type"] == "quarter")]
    assert str(q["period_end"].iloc[0]) < "2014-12-27"       # latest known quarter is an older one


def test_restatement_invisible_until_filed(gw):
    # Q3-2014 revenue: 1020 in the 10-Q; restated to 9999 in the 10-K accepted 20 Feb 2015
    def q3(as_of):
        f = gw.con.execute("""SELECT value FROM fundamentals WHERE company_id='AAA' AND metric='revenue'
                              AND period_end='2014-09-27' AND available_utc <= ? ORDER BY available_utc DESC LIMIT 1""",
                           [as_of]).fetchone()
        return f[0] if f else None
    assert q3(cal.close_utc("2015-02-19")) == 1020.0
    assert q3(cal.close_utc("2015-02-20")) == 9999.0
