"""A small synthetic raw data store with every point-in-time edge case, for Phase 2 tests.

World (2014-01-02 .. 2015-12-31):
- companies AAA, BBB, GOOGL (= share classes GOOG + GOOGL), OLD (leaves 2015-06-01), NEW (joins 2015-06-01)
- AAA: 2-for-1 split on 2015-06-01, quarterly dividends
- SEC: quarterly revenue for every company; AAA's Q3-2014 revenue is RESTATED in the 10-K
  accepted 2015-02-20; AAA's 10-Q for the quarter ending 2014-12-27 is accepted 2015-01-28
  16:31 (ET clock) - i.e. AFTER that day's close
- shares outstanding from each filing; GOOGL files two classes in one filing; NEW has no
  cover-page count (balance-sheet count only); BBB has a split after the price window
- news for AAA at 15:59 / 16:01 ET, on a DST-switch day, at 00:30 UTC (still the previous day
  in New York), on a weekend, and on the 1 pm early-close day after Thanksgiving
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from quantagents.data.download.base import write_json_gz, write_jsonl_gz

DAYS = pd.bdate_range("2014-01-02", "2015-12-31")
CIK = {"AAA": "0000000001", "BBB": "0000000002", "GOOGL": "0000000003", "OLD": "0000000004", "NEW": "0000000005"}
NEWS_TIMES_ET = {          # id -> local New York time
    1: "2015-03-02 15:59", 2: "2015-03-02 16:01",          # either side of the close
    3: "2015-03-09 15:30",                                 # first trading day after DST starts (close = 20:00 UTC)
    4: "2015-03-06 19:30",                                 # 00:30 UTC on 7 Mar, still Friday evening in NY
    5: "2015-03-07 11:00",                                 # Saturday
    6: "2015-11-27 13:30",                                 # after the 1 pm early close (Black Friday)
    7: "2015-11-27 12:30",                                 # before the early close
}


def _prices(seed: int, split_on: str | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, len(DAYS))))
    df = pd.DataFrame({"open": close * 0.998, "high": close * 1.01, "low": close * 0.99, "close": close,
                       "adj_close": close, "volume": 1e6, "dividends": 0.0, "splits": 0.0}, index=DAYS)
    df.loc[df.index[::63], "dividends"] = 0.5
    if split_on:
        # Yahoo style: the series is already split-adjusted (continuous); the actual traded price
        # before the split was 2x the stored close; dividends are adjusted the same way
        before = df.index < pd.Timestamp(split_on)
        df.loc[before, "dividends"] = df.loc[before, "dividends"] / 2
        df.loc[pd.Timestamp(split_on), "splits"] = 2.0
    df.index.name = "date"
    return df


def _french(daily: bool) -> bytes:
    if daily:
        rows = "".join(f"{d:%Y%m%d},0.05,0.01,-0.01,0.00\n" for d in DAYS)
        body = f"Created\n\n,Mkt-RF,SMB,HML,RF\n{rows}\n Copyright\n"
        mom = f"Created\n\n,Mom   \n" + "".join(f"{d:%Y%m%d},0.02\n" for d in DAYS) + "\n"
    else:
        ms = pd.period_range("2014-01", "2015-12", freq="M")
        body = "Created\n\n,Mkt-RF,SMB,HML,RF\n" + "".join(f"{m.strftime('%Y%m')},1.0,0.2,-0.1,0.01\n" for m in ms) + "\n"
        mom = "Created\n\n,Mom   \n" + "".join(f"{m.strftime('%Y%m')},0.5\n" for m in ms) + "\n"
    out = []
    for text in (body, mom):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("x.CSV", text)
        out.append(buf.getvalue())
    return out


def _facts(cik: str, quarters: list[tuple[str, str, float, str]], shares: list[tuple[str, list[float], str]],
           cover_page: bool = True) -> dict:
    """quarters: (start, end, value, accn); shares: (end, [values per class], accn).
    cover_page=False: no cover-page share count (as for multi-class companies in the SEC facts
    file); the count is reported only as balance-sheet CommonStockSharesOutstanding."""
    rev = [{"start": s, "end": e, "val": v, "accn": a, "fy": 2015, "fp": "Q", "form": "10-Q",
            "filed": "2099-01-01"} for s, e, v, a in quarters]
    sh = [{"end": e, "val": v, "accn": a, "form": "10-Q", "filed": "2099-01-01"} for e, vals, a in shares for v in vals]
    us_gaap = {"Revenues": {"units": {"USD": rev}}}
    dei = {}
    if cover_page:
        dei["EntityCommonStockSharesOutstanding"] = {"units": {"shares": sh}}
    else:
        us_gaap["CommonStockSharesOutstanding"] = {"units": {"shares": sh}}
    return {"cik": int(cik), "facts": {"us-gaap": us_gaap, "dei": dei}}


def build_raw_store(root: Path) -> Path:
    raw, derived = root / "raw", root / "derived"
    # --- membership (company level and ticker level) and company map
    derived.mkdir(parents=True, exist_ok=True)
    start = "2014-01-01T00:00:00Z"
    pd.DataFrame([
        {"ticker": "AAA", "start_utc": start, "end_utc": "", "source": "t"},
        {"ticker": "BBB", "start_utc": start, "end_utc": "", "source": "t"},
        {"ticker": "GOOG", "start_utc": start, "end_utc": "", "source": "t"},
        {"ticker": "GOOGL", "start_utc": start, "end_utc": "", "source": "t"},
        {"ticker": "OLD", "start_utc": start, "end_utc": "2015-06-01T00:00:00Z", "source": "t"},
        {"ticker": "NEW", "start_utc": "2015-06-01T00:00:00Z", "end_utc": "", "source": "t"},
    ]).to_csv(derived / "ndx_membership.csv", index=False)
    pd.DataFrame([
        {"ticker": "AAA", "start_utc": start, "end_utc": "", "source": "t"},
        {"ticker": "BBB", "start_utc": start, "end_utc": "", "source": "t"},
        {"ticker": "GOOGL", "start_utc": start, "end_utc": "", "source": "t"},
        {"ticker": "OLD", "start_utc": start, "end_utc": "2015-06-01T00:00:00Z", "source": "t"},
        {"ticker": "NEW", "start_utc": "2015-06-01T00:00:00Z", "end_utc": "", "source": "t"},
    ]).to_csv(derived / "ndx_membership_companies.csv", index=False)
    pd.DataFrame([{"ticker": t, "company_id": "GOOGL" if t == "GOOG" else t, "reason": ""}
                  for t in ["AAA", "BBB", "GOOG", "GOOGL", "OLD", "NEW"]]).to_csv(derived / "company_map.csv", index=False)
    pd.DataFrame([{"ticker": t, "name": f"{t} Inc.", "all_names": f"{t} Inc."} for t in CIK]).to_csv(
        derived / "ticker_names.csv", index=False)
    (raw / "edgar").mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"ticker": t, "cik": CIK["GOOGL" if t == "GOOG" else t],
                   "company_id": "GOOGL" if t == "GOOG" else t, "source": "x"}
                  for t in ["AAA", "BBB", "GOOG", "GOOGL", "OLD", "NEW"]]).to_csv(raw / "edgar" / "ticker_ciks.csv", index=False)

    # --- prices
    pf = raw / "prices" / "yfinance"
    pf.mkdir(parents=True, exist_ok=True)
    _prices(1, split_on="2015-06-01").to_parquet(pf / "AAA.parquet")
    _prices(2).to_parquet(pf / "BBB.parquet")
    _prices(3).to_parquet(pf / "GOOGL.parquet")
    _prices(3).to_parquet(pf / "GOOG.parquet")
    p_old = _prices(4)
    p_old[p_old.index < "2015-07-01"].to_parquet(pf / "OLD.parquet")
    _prices(9).to_parquet(pf / "QQQ.parquet")
    _prices(9).to_parquet(pf / "_NDX.parquet")
    p_new = _prices(5)
    p_new[p_new.index >= "2015-03-01"].to_parquet(pf / "NEW.parquet")
    # BBB splits 10-for-1 on 2016-06-01, AFTER our price window ends: Yahoo's old prices are
    # already divided by 10, but the split only shows in the separate split history
    sf = raw / "prices" / "splits"
    sf.mkdir(parents=True, exist_ok=True)
    (sf / "BBB.csv").write_text("date,ratio\n2016-06-01,10.0\n", encoding="utf-8")

    # --- SEC submissions (acceptance times; ET clock printed with 'Z') and company facts
    subs = raw / "edgar" / "submissions"
    facts = raw / "edgar" / "companyfacts"
    q_ends = [("2014-01-01", "2014-03-29"), ("2014-03-30", "2014-06-28"), ("2014-06-29", "2014-09-27"),
              ("2014-09-28", "2014-12-27"), ("2014-12-28", "2015-03-28"), ("2015-03-29", "2015-06-27"),
              ("2015-06-28", "2015-09-26")]
    for t, cik in CIK.items():
        accns, forms, dates, accepted, quarters, shares = [], [], [], [], [], []
        for i, (qs, qe) in enumerate(q_ends):
            accn = f"{cik}-q{i}"
            acc = pd.Timestamp(qe) + pd.Timedelta(days=32)
            acc_str = f"{acc:%Y-%m-%d}T16:31:00.000Z" if (t == "AAA" and qe == "2014-12-27") else f"{acc:%Y-%m-%d}T10:00:00.000Z"
            if t == "AAA" and qe == "2014-12-27":
                acc_str = "2015-01-28T16:31:00.000Z"
            accns.append(accn); forms.append("10-Q"); dates.append(f"{acc:%Y-%m-%d}"); accepted.append(acc_str)
            quarters.append((qs, qe, 1000.0 + 10 * i, accn))
            # AAA splits 2-for-1 on 2015-06-01: filings accepted after it report the doubled count
            n = 1000.0e6 if (t == "AAA" and acc >= pd.Timestamp("2015-06-01")) else 500.0e6
            shares.append((qe, [400.0e6, 100.0e6] if t == "GOOGL" else [n], accn))
        if t == "AAA":  # restatement of Q3-2014 in a 10-K accepted 2015-02-20
            accns.append(f"{cik}-k2014"); forms.append("10-K"); dates.append("2015-02-20")
            accepted.append("2015-02-20T09:00:00.000Z")
            quarters.append(("2014-06-29", "2014-09-27", 9999.0, f"{cik}-k2014"))
        write_json_gz(subs / f"CIK{cik}.json.gz", {
            "cik": cik, "name": f"{t} INC", "sic": "3674" if t != "BBB" else "2834",
            "addresses": {"business": {"stateOrCountry": "CA" if t != "BBB" else "X0"}},
            "filings": {"recent": {"accessionNumber": accns, "form": forms, "filingDate": dates,
                                   "acceptanceDateTime": accepted}, "files": []}})
        write_json_gz(facts / f"CIK{cik}.json.gz", _facts(cik, quarters, shares, cover_page=(t != "NEW")))

    # --- news for AAA
    rows = []
    for i, local in NEWS_TIMES_ET.items():
        utc = pd.Timestamp(local).tz_localize("America/New_York").tz_convert("UTC")
        rows.append({"id": i, "headline": f"AAA news {i}", "summary": "s", "author": "a",
                     "created_at": utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "updated_at": "", "url": "",
                     "symbols": ["AAA"], "source": "test"})
    write_jsonl_gz(raw / "news" / "alpaca" / "AAA" / "2015.jsonl.gz", rows)

    # --- factors and risk-free
    ff = raw / "factors" / "french"
    ff.mkdir(parents=True, exist_ok=True)
    from quantagents.data.download.factors import FRENCH_FILES
    d_ff, d_mom = _french(True)
    m_ff, m_mom = _french(False)
    (ff / FRENCH_FILES["ff3_daily"]).write_bytes(d_ff)
    (ff / FRENCH_FILES["mom_daily"]).write_bytes(d_mom)
    (ff / FRENCH_FILES["ff3_monthly"]).write_bytes(m_ff)
    (ff / FRENCH_FILES["mom_monthly"]).write_bytes(m_mom)
    (raw / "riskfree").mkdir(parents=True, exist_ok=True)
    (raw / "riskfree" / "DTB3.csv").write_text(
        "observation_date,DTB3\n" + "".join(f"{d:%Y-%m-%d},0.05\n" for d in DAYS), encoding="utf-8")
    (raw / "manifest.jsonl").write_text("", encoding="utf-8")
    return root
