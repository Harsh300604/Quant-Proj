"""NYSE trading calendar and the project's time rules (all timestamps in UTC).

- A daily price bar becomes available at that day's actual close (4 pm ET, or 1 pm ET on
  early-close days such as the day after Thanksgiving), converted to UTC with daylight saving.
- A decision is made "as of" the close of the first trading day of the month (decision D9).
- Trades execute at the next trading day's open.

Everything that compares times uses tz-aware UTC timestamps; naive timestamps are rejected so a
time-zone mistake cannot silently leak data.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache

import pandas as pd

ET = "America/New_York"
_CAL_START, _CAL_END = "2010-01-01", "2026-12-31"


@lru_cache(maxsize=1)
def _schedule() -> pd.DataFrame:
    import pandas_market_calendars as mcal
    s = mcal.get_calendar("XNYS").schedule(start_date=_CAL_START, end_date=_CAL_END)
    s.index = pd.DatetimeIndex(s.index).normalize()
    return s[["market_open", "market_close"]]


def require_utc(ts) -> pd.Timestamp:
    """Return ``ts`` as a UTC Timestamp; raise if it has no time zone."""
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        raise ValueError(f"timestamp {ts!r} has no time zone; use UTC (e.g. pd.Timestamp(..., tz='UTC'))")
    return t.tz_convert("UTC")


def trading_days(start, end) -> pd.DatetimeIndex:
    s = _schedule()
    return s.loc[pd.Timestamp(start):pd.Timestamp(end)].index


def is_trading_day(d) -> bool:
    return pd.Timestamp(d).normalize() in _schedule().index


def close_utc(d) -> pd.Timestamp:
    """Actual market close of trading day ``d`` (UTC)."""
    return _schedule().loc[pd.Timestamp(d).normalize(), "market_close"]


def open_utc(d) -> pd.Timestamp:
    return _schedule().loc[pd.Timestamp(d).normalize(), "market_open"]


def next_trading_day(d) -> pd.Timestamp:
    idx = _schedule().index
    pos = idx.searchsorted(pd.Timestamp(d).normalize(), side="right")
    return idx[pos]


def previous_trading_day(d) -> pd.Timestamp:
    idx = _schedule().index
    pos = idx.searchsorted(pd.Timestamp(d).normalize(), side="left")
    return idx[pos - 1]


def first_trading_day_of_month(year: int, month: int) -> pd.Timestamp:
    days = trading_days(date(year, month, 1), (pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd(0)).date())
    return days[0]


def rebalance_dates(start, end) -> list[pd.Timestamp]:
    """First trading day of every month between ``start`` and ``end`` (inclusive)."""
    out = []
    for m in pd.period_range(pd.Timestamp(start), pd.Timestamp(end), freq="M"):
        d = first_trading_day_of_month(m.year, m.month)
        if pd.Timestamp(start) <= d <= pd.Timestamp(end):
            out.append(d)
    return out


def as_of_for(rebalance_day) -> pd.Timestamp:
    """The decision time for a rebalance day: its close, in UTC (D9)."""
    return close_utc(rebalance_day)


def bar_available_utc(days) -> pd.Series:
    """Availability time (close, UTC) for each trading day in ``days``."""
    s = _schedule()["market_close"]
    idx = pd.DatetimeIndex(days).normalize()
    return pd.Series(s.reindex(idx).to_numpy(), index=idx)


def first_close_at_or_after(ts) -> pd.Timestamp:
    """The first market close at or after ``ts`` (when a news item or filing becomes usable
    in a daily decision)."""
    t = require_utc(ts)
    closes = _schedule()["market_close"]
    pos = closes.searchsorted(t, side="left")
    return closes.iloc[pos]
