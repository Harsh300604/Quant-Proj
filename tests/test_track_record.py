"""Track record (D34): only fully known 3-month outcomes; correct maths; point-in-time."""
import pandas as pd
import pytest

from quantagents.agents.track_record import format_track_record, outcome_end, outcomes
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway

HISTORY = [{"rebalance": d, "views": {"AAA": 1.5, "BBB": 0.5, "GOOGL": 1.0}, "bench": {"AAA": 0.3, "BBB": 0.5, "GOOGL": 0.2}}
           for d in ("2015-01-02", "2015-02-02", "2015-03-02", "2015-04-01")]


def test_outcome_end_is_the_first_trading_day_three_months_later():
    assert outcome_end("2015-01-02", 3) == pd.Timestamp("2015-04-01")
    assert outcome_end("2021-01-04", 3) == pd.Timestamp("2021-04-01")


def frame(db, day):
    t = cal.as_of_for(pd.Timestamp(day))
    gw = Gateway(db, freeze_at=t)
    try:
        return outcomes(gw, HISTORY, t, 3), gw
    finally:
        gw.close()


def test_only_outcomes_known_at_t(synthetic_db):
    df, _ = frame(synthetic_db[1], "2015-05-01")
    assert set(df["made"]) == {"2015-01-02", "2015-02-02"}           # March and April views end later
    assert (pd.to_datetime(df["ends"]) <= pd.Timestamp("2015-05-01")).all()
    assert "GOOGL" not in set(df["company_id"])                       # x1.0 = no view, not scored
    early, _ = frame(synthetic_db[1], "2015-03-02")
    assert early.empty


def test_excess_return_maths(synthetic_db):
    df, _ = frame(synthetic_db[1], "2015-04-01")
    gw = Gateway(synthetic_db[1])
    try:
        p = gw.get_prices(["AAA", "BBB", "GOOGL"], cal.as_of_for(pd.Timestamp("2015-04-01")), lookback_days=120)
    finally:
        gw.close()
    r = p.pivot_table(index="date", columns="company_id", values="ret")
    r.index = pd.DatetimeIndex(r.index)
    g = (1 + r.loc["2015-01-05":"2015-04-01"].fillna(0)).prod() - 1   # from the 2 Jan close to the 1 Apr close
    bench = 0.3 * g["AAA"] + 0.5 * g["BBB"] + 0.2 * g["GOOGL"]
    row = df[df["company_id"] == "AAA"].iloc[0]
    assert row["excess"] == pytest.approx(g["AAA"] - bench, abs=1e-12)
    assert row["right"] == (row["excess"] > 0)


def test_point_in_time_and_text(synthetic_db):
    t = cal.as_of_for(pd.Timestamp("2015-05-01"))
    a, _ = frame(synthetic_db[1], "2015-05-01")
    b, _ = frame(synthetic_db[2](t), "2015-05-01")
    pd.testing.assert_frame_equal(a, b)
    txt = format_track_record(a, t, 3, 3)
    assert "right" in txt and "Views made 2015-02-02" in txt
    empty = format_track_record(a.iloc[0:0], t, 3, 3, first_rebalance="2021-01-04")
    assert "No track record yet" in empty and "2021-04-01" in empty
