"""Market-cap inputs found wrong on the real store (12 Nov 2026, proto20 P0):
- splits Yahoo applied after our price window were missing from raw_close;
- share counts missing for companies without a cover-page count (several share classes, foreign filers);
- ADR ratios could not change over time.
"""
import pandas as pd
import pytest

from quantagents.data import calendar as cal
from quantagents.data.etl import MIN_PLAUSIBLE_SHARES, adr_table, ads_ratio_on, pick_share_counts
from quantagents.data.gateway import Gateway


@pytest.fixture(scope="module")
def gw(synthetic_db):
    g = Gateway(synthetic_db[1])
    yield g
    g.close()


# ------------------------------------------------------------------ splits after the price window
def test_split_after_price_window_restores_traded_price(gw):
    p = gw.get_prices(["BBB"], cal.close_utc("2015-03-02"), lookback_days=5).iloc[-1]
    assert p["raw_close"] == pytest.approx(10 * p["close"])


def test_split_after_window_does_not_change_returns(gw):
    p = gw.get_prices(["BBB"], cal.close_utc("2015-03-02"), lookback_days=10)
    r = p["close"].iloc[-1] / p["close"].iloc[-2] - 1          # no dividend on these days
    if p["dividends"].iloc[-1] == 0:
        assert p["ret"].iloc[-1] == pytest.approx(r)


# ------------------------------------------------------------------ share counts
def _row(accn, end, val, prio, avail, dur=0, concept="c"):
    return {"accn": accn, "period_end": end, "duration": dur, "priority": prio, "concept": concept,
            "val": val, "available_utc": pd.Timestamp(avail, tz="UTC")}


def test_company_without_cover_page_count_still_has_a_weight(gw):
    w = gw.get_index_weights(cal.close_utc("2015-09-01")).set_index("company_id")
    assert "NEW" in w.index and w.loc["NEW", "mcap"] > 0


def test_cover_page_classes_summed_and_preferred():
    sd = pd.DataFrame([_row("a1", "2020-10-20", 400.0e6, 0, "2020-10-30"),
                       _row("a1", "2020-10-20", 100.0e6, 0, "2020-10-30"),
                       _row("a1", "2020-09-30", 480.0e6, 1, "2020-10-30")])
    out = pick_share_counts(sd)
    assert len(out) == 1 and out["shares"].iloc[0] == 500.0e6


def test_latest_quarter_preferred_over_year_to_date():
    sd = pd.DataFrame([_row("a1", "2020-09-30", 4.70e9, 2, "2020-11-16", dur=273),
                       _row("a1", "2020-09-30", 4.75e9, 2, "2020-11-16", dur=91),
                       _row("a1", "2019-09-30", 4.60e9, 2, "2020-11-16", dur=91)])
    assert pick_share_counts(sd)["shares"].iloc[0] == 4.75e9


def test_implausible_count_dropped():
    sd = pd.DataFrame([_row("a1", "2019-03-18", 1.0, 0, "2019-03-19"),
                       _row("a1", "2019-03-31", 6.0e8, 2, "2019-03-19", dur=90)])
    out = pick_share_counts(sd)
    assert out["shares"].tolist() == [6.0e8] and MIN_PLAUSIBLE_SHARES > 1


def test_older_period_filed_later_is_ignored():
    sd = pd.DataFrame([_row("q3", "2020-09-30", 5.0e8, 2, "2020-10-30", dur=91),
                       _row("ka", "2019-12-31", 9.9e8, 2, "2020-11-15", dur=91)])     # late amendment
    assert pick_share_counts(sd)["accn"].tolist() == ["q3"]


def test_share_choice_is_point_in_time():
    """The count chosen for each filing depends only on that filing and earlier ones."""
    rows = [_row(f"f{i}", f"2020-{m:02d}-28", 1e8 + i * 1e6, i % 3, f"2020-{m:02d}-28")
            for i, m in enumerate(range(1, 13))]
    full = pick_share_counts(pd.DataFrame(rows))
    for k in range(1, len(rows)):
        part = pick_share_counts(pd.DataFrame(rows[:k]))
        assert part.equals(full[full["available_utc"] <= rows[k - 1]["available_utc"]].reset_index(drop=True))


# ------------------------------------------------------------------ ADR ratios with dates
def test_adr_ratio_changes_on_its_date():
    ref = pd.DataFrame({"company_id": ["NTES", "NTES", "JD"], "ordinary_per_ads": ["25", "5", "2"],
                        "valid_from": ["", "2020-10-02", ""], "note": ["", "", ""]})
    rows = pd.DataFrame({"company_id": ["NTES", "NTES", "JD", "AAPL"],
                         "date": pd.to_datetime(["2020-10-01", "2020-10-02", "2021-01-04", "2021-01-04"])})
    assert ads_ratio_on(rows, adr_table(ref)).tolist() == [25.0, 5.0, 2.0, 1.0]


def test_empty_adr_file_means_ratio_one():
    rows = pd.DataFrame({"company_id": ["X"], "date": pd.to_datetime(["2021-01-04"])})
    empty = pd.DataFrame(columns=["company_id", "ordinary_per_ads", "valid_from", "note"])
    assert ads_ratio_on(rows, adr_table(empty)).tolist() == [1.0]
