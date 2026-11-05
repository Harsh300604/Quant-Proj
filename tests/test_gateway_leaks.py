"""LEAK TESTS (mandatory before any backtest): no gateway function may return data that was
not available at ``as_of``, and nothing after ``as_of`` may influence what it returns."""
import numpy as np
import pandas as pd
import pytest

from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway, LookAheadError

COMPANIES = ["AAA", "BBB", "GOOGL", "OLD", "NEW"]


def random_as_ofs(n=40, seed=7):
    rng = np.random.default_rng(seed)
    days = cal.trading_days("2014-02-01", "2015-12-30")
    out = [cal.close_utc(d) for d in rng.choice(days, n // 2)]
    out += [pd.Timestamp("2014-02-01", tz="UTC") + pd.Timedelta(minutes=int(m))
            for m in rng.integers(0, 60 * 24 * 690, n // 2)]          # arbitrary times, incl. weekends
    return out


@pytest.fixture(scope="module")
def gw(synthetic_db):
    _, db, _ = synthetic_db
    g = Gateway(db)
    yield g
    g.close()


@pytest.mark.parametrize("as_of", random_as_ofs())
def test_no_row_after_as_of(gw, as_of):
    for name, df in {
        "prices": gw.get_prices(COMPANIES, as_of, lookback_days=10_000),
        "indicators": gw.get_indicators(COMPANIES, as_of),
        "fundamentals": gw.get_fundamentals(COMPANIES, as_of),
        "news": gw.get_news(COMPANIES, as_of, window_days=10_000),
        "weights": gw.get_index_weights(as_of).assign(available_utc=lambda d: cal.bar_available_utc(d["date"]).to_numpy()),
        "riskfree": gw.get_riskfree(as_of),
    }.items():
        if len(df):
            assert (pd.to_datetime(df["available_utc"], utc=True) <= as_of).all(), f"{name} leaked at {as_of}"


@pytest.mark.parametrize("as_of", random_as_ofs())
def test_universe_only_members_at_as_of(gw, as_of):
    u = set(gw.get_universe(as_of)["company_id"])
    removal = pd.Timestamp("2015-06-01", tz="UTC")
    assert ("OLD" in u) == (as_of < removal) and ("NEW" in u) == (as_of >= removal)
    assert "GOOG" not in u and "GOOGL" in u            # company level (D27)


CUTOFFS = [cal.close_utc("2014-12-31"), cal.close_utc("2015-01-28"), pd.Timestamp("2015-03-07 12:00", tz="UTC"),
           cal.close_utc("2015-06-01"), cal.close_utc("2015-11-27")]


@pytest.mark.parametrize("cutoff", CUTOFFS)
def test_nothing_after_as_of_influences_results(synthetic_db, cutoff):
    """Build the store as if today were ``cutoff`` (all later data deleted) and check every
    gateway function returns exactly the same at ``as_of = cutoff`` as with the full store.
    This catches indicators, weights or fundamentals that peek at later rows."""
    _, full_db, build_at = synthetic_db
    full, cut = Gateway(full_db), Gateway(build_at(cutoff))
    try:
        def norm(df):
            df = df.copy()
            for c in df.columns:
                if df[c].dtype == object:
                    df[c] = df[c].astype(str)
            return df.sort_values(list(df.columns)).reset_index(drop=True)
        for fn in ("get_universe", "get_index_weights"):
            pd.testing.assert_frame_equal(norm(getattr(full, fn)(cutoff)), norm(getattr(cut, fn)(cutoff)),
                                          check_dtype=False, obj=fn)
        for fn, kw in (("get_prices", {"lookback_days": 10_000}), ("get_indicators", {}),
                       ("get_fundamentals", {}), ("get_news", {"window_days": 10_000})):
            a, b = getattr(full, fn)(COMPANIES, cutoff, **kw), getattr(cut, fn)(COMPANIES, cutoff, **kw)
            pd.testing.assert_frame_equal(norm(a), norm(b), check_dtype=False, obj=fn)
    finally:
        full.close()
        cut.close()


def test_freeze_at_blocks_later_calls(synthetic_db):
    _, db, _ = synthetic_db
    g = Gateway(db, freeze_at=cal.close_utc("2015-03-02"))
    g.get_universe(cal.close_utc("2015-03-02"))
    with pytest.raises(LookAheadError):
        g.get_news(["AAA"], cal.close_utc("2015-03-03"))
    assert g.max_as_of == cal.close_utc("2015-03-03")    # the attempt is still recorded for red flags
    g.close()


def test_naive_as_of_rejected(gw):
    with pytest.raises(ValueError, match="time zone"):
        gw.get_universe(pd.Timestamp("2015-03-02 21:00"))
