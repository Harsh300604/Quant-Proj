import numpy as np
import pandas as pd
import pytest

from quantagents.data import calendar as cal
from quantagents.data.etl import compute_indicators
from quantagents.data.gateway import Gateway


def test_indicator_on_t_identical_with_data_up_to_t_or_full_history(synthetic_db):
    g = Gateway(synthetic_db[1])
    try:
        bars = g.get_prices(["BBB"], cal.close_utc("2015-12-30"), lookback_days=10_000)
    finally:
        g.close()
    full = compute_indicators(bars).set_index("date")
    for cut in ("2014-11-03", "2015-04-15", "2015-09-01"):
        part = compute_indicators(bars[bars["date"] <= cut]).set_index("date")
        a, b = full.loc[pd.Timestamp(cut)].drop("available_utc"), part.loc[pd.Timestamp(cut)].drop("available_utc")
        cols = [c for c in a.index if c != "company_id"]
        np.testing.assert_allclose(a[cols].astype(float), b[cols].astype(float), rtol=1e-9, equal_nan=True)


def test_indicators_are_scale_free():
    """Multiplying all prices by 10 (like a different split adjustment) changes nothing."""
    rng = np.random.default_rng(1)
    n = 300
    c = pd.Series(50 * np.exp(np.cumsum(rng.normal(0, 0.01, n))))
    days = cal.trading_days("2014-01-02", "2016-01-01")[:n]
    bars = pd.DataFrame({"company_id": "X", "date": days, "available_utc": cal.bar_available_utc(days).to_numpy(),
                         "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "ret": c.pct_change()})
    big = bars.assign(open=c * 10, high=c * 10.1, low=c * 9.9, close=c * 10)
    a, b = compute_indicators(bars), compute_indicators(big)
    cols = [x for x in a.columns if x not in ("company_id", "date", "available_utc")]
    np.testing.assert_allclose(a[cols].astype(float), b[cols].astype(float), rtol=1e-6, equal_nan=True)


def test_short_history_gives_blank_indicators_not_a_crash():
    days = cal.trading_days("2015-01-02", "2015-02-27")[:15]
    c = pd.Series(np.linspace(10, 12, len(days)))
    bars = pd.DataFrame({"company_id": "NEWCO", "date": days, "available_utc": cal.bar_available_utc(days).to_numpy(),
                         "open": c, "high": c, "low": c, "close": c, "ret": c.pct_change()})
    out = compute_indicators(bars)
    assert len(out) == 15 and out["close_ema200"].isna().all() and out["close_sma200"].isna().all()


def test_no_warm_up_values_before_the_full_window():
    days = cal.trading_days("2014-01-02", "2015-12-31")
    rng = np.random.default_rng(3)
    c = pd.Series(50 * np.exp(np.cumsum(rng.normal(0, 0.01, len(days)))))
    bars = pd.DataFrame({"company_id": "X", "date": days, "available_utc": cal.bar_available_utc(days).to_numpy(),
                         "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "ret": c.pct_change()})
    out = compute_indicators(bars)
    assert out["rsi14"].iloc[:14].isna().all() and out["rsi14"].iloc[14:].notna().all()
    assert out["macd_hist_pct"].iloc[:34].isna().all() and out["close_ema200"].iloc[:199].isna().all()
