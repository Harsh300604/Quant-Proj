"""Bob's simulated trading pool (D32): deterministic, point-in-time, correct tilt maths."""
import pandas as pd
import pytest

from quantagents.agents.sim_trading import POOL, simulate_pool, tilt
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway

AS_OF = cal.as_of_for(pd.Timestamp("2015-06-01"))
IDS = ["AAA", "BBB", "GOOGL", "OLD"]


def test_tilt_top_third_up_bottom_third_down():
    bench = pd.Series([0.4, 0.3, 0.2, 0.1, 0.0, 0.0], index=list("ABCDEF")) + 0.0
    bench = (bench + 0.05) / (bench + 0.05).sum()
    w = tilt(pd.Series([6, 5, 4, 3, 2, 1], index=list("ABCDEF"), dtype=float), bench)
    m = (w / bench) / (w / bench)["C"]                            # relative to an untilted name
    assert m["A"] == pytest.approx(1.5) and m["B"] == pytest.approx(1.5)
    assert m["E"] == pytest.approx(0.5) and m["F"] == pytest.approx(0.5) and w.sum() == pytest.approx(1)
    nan = tilt(pd.Series(float("nan"), index=bench.index), bench)
    assert nan.equals(bench / bench.sum())                       # no signal -> benchmark


def run_pool(db):
    gw = Gateway(db, freeze_at=AS_OF)
    try:
        return simulate_pool(gw, IDS, AS_OF, months=4)
    finally:
        gw.close()


def test_look_back_before_the_first_price_is_skipped(synthetic_db):
    """Found in the paid pilot: the 2 Jan 2015 decision looks back to before the first stored bar."""
    t = cal.as_of_for(pd.Timestamp("2015-01-02"))
    gw = Gateway(synthetic_db[1], freeze_at=t)
    try:
        res = simulate_pool(gw, IDS, t, months=14)           # look-back starts Nov 2013; prices start Jan 2014
    finally:
        gw.close()
    assert res["periods"] <= 12 and pd.Timestamp(res["from"]) >= pd.Timestamp("2014-01-02")
    assert res["to"] == "2015-01-02" and len(res["table"]) == 5


def test_pool_is_point_in_time_and_deterministic(synthetic_db):
    full, cut = run_pool(synthetic_db[1]), run_pool(synthetic_db[2](AS_OF))
    pd.testing.assert_frame_equal(full["table"], cut["table"])
    assert full["picks"] == cut["picks"] and full["periods"] == 4
    again = run_pool(synthetic_db[1])
    pd.testing.assert_frame_equal(full["table"], again["table"])
    assert list(full["table"].index) == list(POOL)
    assert full["table"].loc["index_hold", "vs_index"] == 0.0
