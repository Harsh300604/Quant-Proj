"""Point-in-time gateway: the ONLY way the pipeline reads data (brief §9).

Every function takes ``as_of`` (a tz-aware UTC timestamp, normally the close of a rebalance
day) and only returns rows whose ``available_utc <= as_of``. The universe is at company level
(D27). Every call is recorded in ``Gateway.calls`` so the red-flag checks can prove no call
looked past the rebalance date, and ``Gateway(freeze_at=...)`` makes any later ``as_of`` an error.

    python -m quantagents.data.gateway --as-of 2016-03-01 --show universe
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from quantagents.data import calendar as cal

# Which fundamentals count as "quarterly" (about 3 months) and "annual" (about a year)
QUARTER_DAYS = (80, 100)
ANNUAL_DAYS = (350, 380)


class LookAheadError(RuntimeError):
    pass


@dataclass
class Gateway:
    db_path: Path
    freeze_at: pd.Timestamp | None = None
    calls: list[tuple[str, pd.Timestamp]] = field(default_factory=list)

    def __post_init__(self):
        import duckdb
        self.con = duckdb.connect(str(self.db_path), read_only=True)
        if self.freeze_at is not None:
            self.freeze_at = cal.require_utc(self.freeze_at)

    def close(self) -> None:
        self.con.close()

    # ------------------------------------------------------------------ guard
    def _check(self, fn: str, as_of) -> pd.Timestamp:
        t = cal.require_utc(as_of)
        self.calls.append((fn, t))
        if self.freeze_at is not None and t > self.freeze_at:
            raise LookAheadError(f"{fn}(as_of={t}) is after the allowed time {self.freeze_at}")
        return t

    @property
    def max_as_of(self) -> pd.Timestamp | None:
        return max((t for _, t in self.calls), default=None)

    def _q(self, sql: str, params: list) -> pd.DataFrame:
        return self.con.execute(sql, params).df()

    @staticmethod
    def _companies(companies) -> list[str]:
        return [companies] if isinstance(companies, str) else list(companies)

    # ------------------------------------------------------------------ API
    def get_universe(self, as_of) -> pd.DataFrame:
        """Index members (companies) at ``as_of``, with name, sector, country and whether prices exist."""
        t = self._check("get_universe", as_of)
        return self._q("""
            SELECT m.ticker AS company_id, c.name, c.tickers, c.sector, c.state_or_country, c.is_us,
                   p.ticker IS NOT NULL AS has_prices
            FROM membership_company m
            LEFT JOIN companies c ON c.company_id = m.ticker
            LEFT JOIN company_price_ticker p ON p.company_id = m.ticker
            WHERE m.start_utc <= ? AND (m.end_utc IS NULL OR m.end_utc > ?)
            ORDER BY company_id""", [t, t])

    def get_index_weights(self, as_of) -> pd.DataFrame:
        """Company weights from the latest close at or before ``as_of`` (members with a market cap)."""
        t = self._check("get_index_weights", as_of)
        return self._q("""
            WITH last AS (SELECT max(available_utc) AS a FROM index_weights WHERE available_utc <= ?)
            SELECT w.company_id, w.weight, w.mcap, w.date, c.sector, c.is_us
            FROM index_weights w JOIN last ON w.available_utc = last.a
            LEFT JOIN companies c ON c.company_id = w.company_id
            ORDER BY w.weight DESC""", [t])

    def get_prices(self, companies, as_of, lookback_days: int = 400) -> pd.DataFrame:
        """Daily bars (company-level price series) with close at or before ``as_of``."""
        t = self._check("get_prices", as_of)
        start = (t - pd.Timedelta(days=lookback_days)).tz_convert(None).normalize()
        return self._q("""
            SELECT p.company_id, p.ticker, p.date, p.open, p.high, p.low, p.close, p.volume, p.dividends,
                   p.splits, p.ret, p.raw_close, p.available_utc
            FROM prices p JOIN company_price_ticker r ON r.company_id = p.company_id AND r.ticker = p.ticker
            WHERE p.company_id IN (SELECT unnest(?)) AND p.available_utc <= ? AND p.date >= ?
            ORDER BY p.company_id, p.date""", [self._companies(companies), t, start])

    def get_indicators(self, companies, as_of) -> pd.DataFrame:
        """Latest indicator row per company at or before ``as_of``."""
        t = self._check("get_indicators", as_of)
        return self._q("""
            SELECT * EXCLUDE (rn) FROM (
              SELECT i.*, row_number() OVER (PARTITION BY company_id ORDER BY available_utc DESC) AS rn
              FROM indicators i WHERE company_id IN (SELECT unnest(?)) AND available_utc <= ?)
            WHERE rn = 1 ORDER BY company_id""", [self._companies(companies), t])

    def get_fundamentals(self, companies, as_of) -> pd.DataFrame:
        """Per company and metric: the latest quarterly and annual values known at ``as_of``.

        Restatement-safe: for each period, the value comes from the latest filing accepted at or
        before ``as_of`` (a later restatement is invisible until it was filed). Balance-sheet items
        (no duration) are returned as 'instant'.
        """
        t = self._check("get_fundamentals", as_of)
        return self._q(f"""
            WITH known AS (
              SELECT *, CASE
                  WHEN duration_days IS NULL THEN 'instant'
                  WHEN duration_days BETWEEN {QUARTER_DAYS[0]} AND {QUARTER_DAYS[1]} THEN 'quarter'
                  WHEN duration_days BETWEEN {ANNUAL_DAYS[0]} AND {ANNUAL_DAYS[1]} THEN 'annual'
                  ELSE 'other' END AS period_type
              FROM fundamentals WHERE company_id IN (SELECT unnest(?)) AND available_utc <= ?),
            per_period AS (   -- latest filing (then best concept) for each period
              SELECT * EXCLUDE (rn) FROM (
                SELECT *, row_number() OVER (PARTITION BY company_id, metric, period_type, period_end
                                             ORDER BY available_utc DESC, priority ASC) AS rn
                FROM known WHERE period_type <> 'other') WHERE rn = 1),
            latest AS (       -- most recent period per metric and period type
              SELECT * EXCLUDE (rn) FROM (
                SELECT *, row_number() OVER (PARTITION BY company_id, metric, period_type
                                             ORDER BY period_end DESC) AS rn FROM per_period) WHERE rn = 1)
            SELECT company_id, metric, period_type, value, unit, period_start, period_end, form, accn,
                   available_utc, concept
            FROM latest ORDER BY company_id, metric, period_type""", [self._companies(companies), t])

    def get_news(self, companies, as_of, window_days: int = 31) -> pd.DataFrame:
        """News published in the ``window_days`` before ``as_of`` (up to and including ``as_of``).

        Because ``as_of`` is a market close, an article published after the close only appears
        from the next trading day's decision (brief §4)."""
        t = self._check("get_news", as_of)
        start = t - pd.Timedelta(days=window_days)
        return self._q("""
            SELECT company_id, ticker, id, created_utc, headline, summary, symbols, source, url, available_utc
            FROM news WHERE company_id IN (SELECT unnest(?)) AND available_utc <= ? AND available_utc > ?
            ORDER BY company_id, created_utc""", [self._companies(companies), t, start])

    def get_benchmark(self, ticker: str, as_of, lookback_days: int = 400) -> pd.DataFrame:
        """Daily bars of a benchmark ('QQQ' or '^NDX') with close at or before ``as_of``."""
        t = self._check("get_benchmark", as_of)
        start = (t - pd.Timedelta(days=lookback_days)).tz_convert(None).normalize()
        return self._q("""SELECT * FROM benchmarks WHERE ticker = ? AND available_utc <= ? AND date >= ?
                          ORDER BY date""", [ticker, t, start])

    def get_riskfree(self, as_of) -> pd.DataFrame:
        t = self._check("get_riskfree", as_of)
        return self._q("SELECT * FROM riskfree WHERE available_utc <= ? ORDER BY date", [t])


def main(argv: list[str] | None = None) -> int:
    from quantagents.config import CONFIG_DIR, load_config
    from quantagents.paths import Paths
    ap = argparse.ArgumentParser(description="Look at the data as it was known on a date")
    ap.add_argument("--as-of", required=True, help="date (YYYY-MM-DD); uses that trading day's close")
    ap.add_argument("--show", choices=["universe", "weights", "sectors", "fundamentals", "news", "indicators"],
                    default="universe")
    ap.add_argument("--company", help="company id for fundamentals/news/indicators (e.g. AAPL)")
    ap.add_argument("--config", default=str(CONFIG_DIR / "base.yaml"))
    args = ap.parse_args(argv)
    d = pd.Timestamp(args.as_of)
    day = d if cal.is_trading_day(d) else cal.next_trading_day(d)
    as_of = cal.as_of_for(day)
    gw = Gateway(Paths.from_config(load_config(args.config)).duckdb_file)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 200)
    print(f"As of {as_of} (close of {day.date()})")
    if args.show == "universe":
        u = gw.get_universe(as_of)
        w = gw.get_index_weights(as_of)
        u = u.merge(w[["company_id", "weight"]], on="company_id", how="left").sort_values("weight", ascending=False)
        print(u[["company_id", "name", "sector", "is_us", "has_prices", "weight"]].to_string(index=False))
        print(f"\n{len(u)} companies; {int(u['has_prices'].sum())} with prices; "
              f"weights sum to {w['weight'].sum():.3f}")
    elif args.show in ("weights", "sectors"):
        w = gw.get_index_weights(as_of)
        if args.show == "weights":
            print(w.head(30).to_string(index=False))
        else:
            print(w.groupby("sector")["weight"].sum().sort_values(ascending=False).round(4).to_string())
            print(f"\nUS share of weight: {w.loc[w['is_us'] == True, 'weight'].sum():.3f}")  # noqa: E712
    else:
        if not args.company:
            print("--company is required for this view")
            return 2
        fn = {"fundamentals": gw.get_fundamentals, "news": gw.get_news, "indicators": gw.get_indicators}[args.show]
        print(fn([args.company.upper()], as_of).to_string(index=False))
    gw.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
