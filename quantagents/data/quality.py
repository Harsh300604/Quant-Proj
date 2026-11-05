"""Data-quality checks on the built DuckDB store (Phase 2; reused by the red-flag checks).

All checks read the store directly (offline, no LLM). They answer:
- coverage: on each rebalance date, how many index members have prices / a market cap / fundamentals
- ticker reuse: does each company's price series cover the period it was in the index?
  (a reused ticker that now belongs to another company shows up as a series starting too late)
- foreign filers: 20-F/40-F companies whose depositary-share ratio is still missing
- derived index vs QQQ: yearly return and tracking error of our cap-weighted index
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quantagents.data import calendar as cal

MISSING_RED_FLAG = 0.02   # brief §9 / D3: more than 2% of members without prices is a red flag


def coverage_by_month(con, start="2015-01-01", end="2023-12-31") -> pd.DataFrame:
    rows = []
    priced = set(con.execute("SELECT company_id FROM company_price_ticker").df()["company_id"])
    for d in cal.rebalance_dates(start, end):
        t = cal.as_of_for(d)
        mem = con.execute("""SELECT ticker AS company_id FROM membership_company
                             WHERE start_utc <= ? AND (end_utc IS NULL OR end_utc > ?)""", [t, t]).df()["company_id"]
        mem = set(mem)
        with_bar = set(con.execute("""SELECT DISTINCT p.company_id FROM prices p
            JOIN company_price_ticker r ON r.company_id = p.company_id AND r.ticker = p.ticker
            WHERE p.available_utc <= ? AND p.available_utc > ? - INTERVAL 10 DAY""", [t, t]).df()["company_id"])
        w = con.execute("""SELECT company_id FROM index_weights WHERE available_utc =
                           (SELECT max(available_utc) FROM index_weights WHERE available_utc <= ?)""", [t]).df()
        fund = set(con.execute("""SELECT DISTINCT company_id FROM fundamentals
                                  WHERE metric = 'revenue' AND available_utc <= ? AND available_utc > ? - INTERVAL 400 DAY""",
                               [t, t]).df()["company_id"])
        no_price = sorted(mem - (with_bar & priced))
        rows.append({"rebalance": d.date(), "members": len(mem), "with_prices": len(mem) - len(no_price),
                     "with_mcap": len(mem & set(w["company_id"])), "with_fundamentals": len(mem & fund),
                     "pct_missing_prices": round(100 * len(no_price) / max(len(mem), 1), 1),
                     "missing_prices": ", ".join(no_price),
                     "missing_mcap": ", ".join(sorted((mem - set(no_price)) - set(w["company_id"]))),
                     "missing_fundamentals": ", ".join(sorted(mem - fund))})
    return pd.DataFrame(rows)


def ticker_reuse(con, tolerance_days: int = 10) -> pd.DataFrame:
    """Companies whose price series starts after they joined, or ends before they left."""
    spans = con.execute("""
        SELECT r.company_id, r.ticker, min(p.date) AS first_bar, max(p.date) AS last_bar
        FROM company_price_ticker r JOIN prices p ON p.company_id = r.company_id AND p.ticker = r.ticker
        GROUP BY 1, 2""").df()
    spells = con.execute("""SELECT ticker AS company_id, min(start_utc) AS joined, max(coalesce(end_utc,
                            TIMESTAMPTZ '2099-01-01 00:00:00+00')) AS left_ FROM membership_company GROUP BY 1""").df()
    m = spans.merge(spells, on="company_id")
    data_start = pd.Timestamp("2014-01-15")
    out = []
    for r in m.itertuples():
        joined = pd.Timestamp(r.joined).tz_convert(None).normalize()
        left = pd.Timestamp(r.left_).tz_convert(None).normalize()
        late = pd.Timestamp(r.first_bar) > max(joined, data_start) + pd.Timedelta(days=tolerance_days)
        early = left < pd.Timestamp("2098-01-01") and pd.Timestamp(r.last_bar) < left - pd.Timedelta(days=tolerance_days)
        if late or early:
            out.append({"company_id": r.company_id, "ticker": r.ticker, "joined": joined.date(),
                        "left": None if left.year > 2090 else left.date(), "first_bar": pd.Timestamp(r.first_bar).date(),
                        "last_bar": pd.Timestamp(r.last_bar).date(),
                        "problem": "prices start after joining" if late else "prices end before leaving"})
    return pd.DataFrame(out, columns=["company_id", "ticker", "joined", "left", "first_bar", "last_bar", "problem"])


def foreign_filers(con) -> pd.DataFrame:
    return con.execute("""SELECT company_id, name, annual_form, state_or_country, ordinary_per_ads FROM companies
                          WHERE annual_form IN ('20-F', '40-F') ORDER BY company_id""").df()


def index_vs_benchmark(con, benchmark: str = "QQQ") -> pd.DataFrame:
    """Yearly return of our derived cap-weighted index vs the benchmark, and tracking error.

    Index return on day t = sum of weights at the close of t-1 x each company's total return on t."""
    w = con.execute("SELECT date, company_id, weight FROM index_weights").df()
    r = con.execute("""SELECT p.date, p.company_id, p.ret FROM prices p
                       JOIN company_price_ticker c ON c.company_id = p.company_id AND c.ticker = p.ticker""").df()
    b = con.execute("SELECT date, ret FROM benchmarks WHERE ticker = ? ORDER BY date", [benchmark]).df()
    if w.empty or b.empty:
        return pd.DataFrame(columns=["year", "index_return", "benchmark_return", "difference", "tracking_error"])
    w = w.sort_values("date")
    days = sorted(w["date"].unique())
    nxt = dict(zip(days[:-1], days[1:]))
    w["apply_date"] = w["date"].map(nxt)
    m = w.dropna(subset=["apply_date"]).merge(r.rename(columns={"date": "apply_date"}), on=["apply_date", "company_id"])
    m["contrib"] = m["weight"] * m["ret"].fillna(0.0)
    idx = m.groupby("apply_date")["contrib"].sum().rename("index_ret")
    j = pd.concat([idx, b.set_index("date")["ret"].rename("bench_ret")], axis=1, join="inner").dropna()
    j["year"] = pd.DatetimeIndex(j.index).year
    out = []
    for y, g in j.groupby("year"):
        out.append({"year": y, "index_return": (1 + g["index_ret"]).prod() - 1,
                    "benchmark_return": (1 + g["bench_ret"]).prod() - 1,
                    "difference": (1 + g["index_ret"]).prod() - (1 + g["bench_ret"]).prod(),
                    "tracking_error": float((g["index_ret"] - g["bench_ret"]).std() * np.sqrt(252))})
    return pd.DataFrame(out)
