import pytest

from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway


@pytest.fixture(scope="module")
def gw(synthetic_db):
    g = Gateway(synthetic_db[1])
    yield g
    g.close()


def test_removed_company_present_before_and_absent_after(gw):
    assert "OLD" in set(gw.get_universe(cal.close_utc("2015-05-29"))["company_id"])
    assert "OLD" not in set(gw.get_universe(cal.close_utc("2015-06-01"))["company_id"])


def test_added_company_absent_before_even_though_prices_exist(gw):
    # NEW has prices from March 2015 but only joins on 1 June 2015
    assert "NEW" not in set(gw.get_universe(cal.close_utc("2015-04-01"))["company_id"])
    assert "NEW" in set(gw.get_universe(cal.close_utc("2015-06-02"))["company_id"])


def test_share_classes_are_one_company(gw):
    u = gw.get_universe(cal.close_utc("2015-03-02")).set_index("company_id")
    assert "GOOG" not in u.index and u.loc["GOOGL", "tickers"] == "GOOG,GOOGL"
