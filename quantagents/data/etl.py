"""Build the DuckDB data store from the raw downloads (Phase 2).

    python -m quantagents.data.etl --config configs\\base.yaml

Every table carries an ``available_utc`` column: the moment the row became knowable.
The gateway only ever returns rows with ``available_utc <= as_of`` (decision D21 / brief §9).

Availability rules
- price bar ............ that day's actual market close (calendar.close_utc)
- news ................. its publish time (created_at, UTC); a decision at a close sees news up
                         to that close, so after-close news counts from the next trading day
- SEC fact / shares .... the filing's EDGAR acceptance time. EDGAR prints it with a 'Z' but the
                         clock is US Eastern, so we read it as ET (the later, safer reading, D29);
                         if missing: the day after the filing date, 00:00 ET
- index membership ..... the snapshot time it was observed (Wikipedia revision as of that time)
- indicators / weights . the close of the bar they are computed from

Prices: Yahoo's ``close`` is split-adjusted (scaled by later splits) but not dividend-adjusted.
We store it, its total return ``ret`` (close-to-close including dividends: scale-free, no
look-ahead), and ``raw_close`` = close x later split factors (the actual traded price, needed
for market caps).
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from quantagents.config import CONFIG_DIR, REPO_ROOT, load_config
from quantagents.data import calendar as cal
from quantagents.data.download.base import Manifest, read_json_gz, read_jsonl_gz
from quantagents.data.download.factors import FRENCH_FILES, parse_french_csv
from quantagents.data.download.prices import BENCHMARKS, file_name, read_manual_prices, read_splits
from quantagents.paths import Paths, configure_third_party_caches

log = logging.getLogger("quantagents.etl")
REF = REPO_ROOT / "reference"
SCHEMA_VERSION = 1

# metric -> (taxonomy, [concepts in priority order], unit kind)
METRICS: dict[str, list[tuple[str, str]]] = {
    "revenue": [("us-gaap", "Revenues"), ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
                ("us-gaap", "SalesRevenueNet"), ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
                ("us-gaap", "SalesRevenueGoodsNet"), ("ifrs-full", "Revenue")],
    "gross_profit": [("us-gaap", "GrossProfit"), ("ifrs-full", "GrossProfit")],
    "operating_income": [("us-gaap", "OperatingIncomeLoss"), ("ifrs-full", "ProfitLossFromOperatingActivities")],
    "net_income": [("us-gaap", "NetIncomeLoss"), ("us-gaap", "ProfitLoss"),
                   ("ifrs-full", "ProfitLossAttributableToOwnersOfParent"), ("ifrs-full", "ProfitLoss")],
    "eps_diluted": [("us-gaap", "EarningsPerShareDiluted"), ("ifrs-full", "DilutedEarningsLossPerShare")],
    "op_cash_flow": [("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
                     ("us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
                     ("ifrs-full", "CashFlowsFromUsedInOperatingActivities")],
    "capex": [("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
              ("us-gaap", "PaymentsToAcquireProductiveAssets"),
              ("ifrs-full", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities")],
    "total_assets": [("us-gaap", "Assets"), ("ifrs-full", "Assets")],
    "total_liabilities": [("us-gaap", "Liabilities"), ("ifrs-full", "Liabilities")],
    "equity": [("us-gaap", "StockholdersEquity"),
               ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
               ("ifrs-full", "EquityAttributableToOwnersOfParent"), ("ifrs-full", "Equity")],
    "cash": [("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
             ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
             ("ifrs-full", "CashAndCashEquivalents")],
    "long_term_debt": [("us-gaap", "LongTermDebt"), ("us-gaap", "LongTermDebtNoncurrent"),
                       ("ifrs-full", "NoncurrentFinancialLiabilities")],
}
SHARE_COLUMNS = ["company_id", "cik", "period_end", "shares", "accn", "available_utc", "concept"]
US_STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
                "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR".split())


# ----------------------------------------------------------------------------- time helpers
def edgar_acceptance_to_utc(value: str | None) -> pd.Timestamp | None:
    """EDGAR acceptanceDateTime ('2015-01-28T16:31:00.000Z') -> UTC, reading the clock as ET (D29)."""
    if not value:
        return None
    t = pd.Timestamp(str(value).replace("Z", "").split("+")[0])
    if t.tzinfo is not None:
        t = t.tz_localize(None)
    return t.tz_localize(cal.ET).tz_convert("UTC")


def filed_date_fallback_utc(filed: str) -> pd.Timestamp:
    """No acceptance time: available from 00:00 ET on the day after the filing date."""
    return (pd.Timestamp(filed) + pd.Timedelta(days=1)).tz_localize(cal.ET).tz_convert("UTC")


# ----------------------------------------------------------------------------- loaders
def _read_csv_utc(path: Path, cols: tuple[str, ...]) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    for c in cols:
        df[c] = pd.to_datetime(df[c], utc=True)
    return df


def load_reference(name: str) -> pd.DataFrame:
    return pd.read_csv(REF / name, comment="#", dtype=str).fillna("")


def sector_for_sic(sic: str | int | None, table: pd.DataFrame | None = None) -> str:
    table = load_reference("sic_to_sector.csv") if table is None else table
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return "Unknown"
    rows = [(int(r.sic_to) - int(r.sic_from), r.sector) for r in table.itertuples()
            if int(r.sic_from) <= s <= int(r.sic_to)]
    return min(rows)[1] if rows else "Unknown"


def later_split_factor(paths: Paths, manifest: Manifest, ticker: str, last_bar: pd.Timestamp,
                       price_file: Path) -> float:
    """Product of the splits Yahoo applied AFTER our last bar, up to the day the prices were
    downloaded. Yahoo scales every old price by those splits too, but they are not in our price
    window, so without this factor ``raw_close`` would be off by e.g. 10x after a 10-for-1 split."""
    s = read_splits(paths.raw, ticker)
    if s.empty:
        return 1.0
    e = manifest.entry(price_file) if price_file.exists() else None
    downloaded = pd.Timestamp(e.downloaded_utc).tz_convert(None).normalize() if e else pd.Timestamp.today().normalize()
    later = s[(s.index > last_bar) & (s.index <= downloaded)]
    return float(later.prod()) if len(later) else 1.0


def load_prices(paths: Paths, tickers: list[str]) -> pd.DataFrame:
    """One long table of daily bars for every ticker with data (Yahoo first, then manual CSVs)."""
    frames = []
    manifest = Manifest(paths.raw)
    for tk in tickers:
        f = paths.raw / "prices" / "yfinance" / f"{file_name(tk)}.parquet"
        df, source = (pd.read_parquet(f), "yfinance") if f.exists() else (None, None)
        if df is None:
            df = read_manual_prices(paths.manual_prices, tk)
            source = "manual" if df is not None else None
        if df is None or df.empty:
            continue
        df = df.copy()
        df.index = pd.DatetimeIndex(df.index).normalize()
        df = df[~df.index.duplicated(keep="last")].sort_index()
        df = df[df.index.isin(cal.trading_days(df.index.min(), df.index.max()))]
        for c in ("dividends", "splits"):
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        prev = df["close"].shift(1)
        df["ret"] = (df["close"] + df["dividends"]) / prev - 1.0
        ratio = df["splits"].where(df["splits"] > 0, 1.0)
        # product of split ratios strictly AFTER each date
        after = ratio[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
        extra = later_split_factor(paths, manifest, tk, df.index.max(), f) if source == "yfinance" else 1.0
        df["raw_close"] = df["close"] * after * extra
        df["ticker"] = tk
        df["source"] = source
        df["date"] = df.index
        frames.append(df.reset_index(drop=True))
    if not frames:
        return pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "adj_close", "volume",
                                     "dividends", "splits", "ret", "raw_close", "source", "available_utc"])
    out = pd.concat(frames, ignore_index=True)
    out["available_utc"] = cal.bar_available_utc(out["date"]).to_numpy()
    return out[["ticker", "date", "open", "high", "low", "close", "adj_close", "volume", "dividends", "splits",
                "ret", "raw_close", "source", "available_utc"]]


def load_submissions(paths: Paths, cik: str) -> tuple[dict, pd.DataFrame]:
    """(main submissions JSON, table of every filing: accn, form, filed, available_utc)."""
    folder = paths.raw / "edgar" / "submissions"
    main_f = folder / f"CIK{cik}.json.gz"
    if not main_f.exists():
        return {}, pd.DataFrame(columns=["accn", "form", "filed", "available_utc"])
    main = read_json_gz(main_f)
    blocks = [main.get("filings", {}).get("recent", {}) or {}]
    for extra in main.get("filings", {}).get("files", []):
        pf = folder / f"{extra['name'].replace('.json', '')}.json.gz"
        if pf.exists():
            blocks.append(read_json_gz(pf))
    rows = []
    for b in blocks:
        for accn, form, filed, acc in zip(b.get("accessionNumber", []), b.get("form", []),
                                          b.get("filingDate", []),
                                          b.get("acceptanceDateTime") or itertools.repeat("")):
            t = edgar_acceptance_to_utc(acc) or filed_date_fallback_utc(filed)
            rows.append({"accn": accn, "form": form, "filed": filed, "available_utc": t})
    if not rows:
        return main, pd.DataFrame(columns=["accn", "form", "filed", "available_utc"])
    return main, pd.DataFrame(rows).drop_duplicates("accn")


def load_facts(paths: Paths, cik: str, company_id: str, filings: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(fundamentals rows, shares-outstanding rows) for one filer."""
    f = paths.raw / "edgar" / "companyfacts" / f"CIK{cik}.json.gz"
    empty_f = pd.DataFrame(columns=["company_id", "cik", "metric", "concept", "priority", "unit", "value",
                                    "period_start", "period_end", "duration_days", "fy", "fp", "form", "accn",
                                    "filed", "available_utc"])
    empty_s = pd.DataFrame(columns=SHARE_COLUMNS)
    if not f.exists():
        return empty_f, empty_s
    facts = read_json_gz(f).get("facts", {})
    acc = dict(zip(filings["accn"], filings["available_utc"])) if len(filings) else {}

    def avail(accn, filed):
        return acc.get(accn) or filed_date_fallback_utc(filed)

    rows = []
    for metric, concepts in METRICS.items():
        for prio, (tax, concept) in enumerate(concepts):
            units = facts.get(tax, {}).get(concept, {}).get("units", {})
            for unit, items in units.items():
                for it in items:
                    if "val" not in it or "end" not in it:
                        continue
                    start = it.get("start")
                    dur = (pd.Timestamp(it["end"]) - pd.Timestamp(start)).days if start else None
                    rows.append({"company_id": company_id, "cik": cik, "metric": metric, "concept": f"{tax}:{concept}",
                                 "priority": prio, "unit": unit, "value": float(it["val"]),
                                 "period_start": start, "period_end": it["end"], "duration_days": dur,
                                 "fy": it.get("fy"), "fp": it.get("fp"), "form": it.get("form"),
                                 "accn": it.get("accn"), "filed": it.get("filed"),
                                 "available_utc": avail(it.get("accn"), it.get("filed"))})
    srows = []
    for prio, (tax, concept) in enumerate(SHARE_CONCEPTS):
        for it in facts.get(tax, {}).get(concept, {}).get("units", {}).get("shares", []):
            if "val" not in it or "end" not in it or not it.get("accn"):
                continue
            start = it.get("start")
            dur = (pd.Timestamp(it["end"]) - pd.Timestamp(start)).days if start else 0
            if dur > 380:                      # averages over more than a year are too old a picture
                continue
            srows.append({"accn": it["accn"], "period_end": it["end"], "duration": dur, "priority": prio,
                          "concept": concept, "val": float(it["val"]),
                          "available_utc": avail(it.get("accn"), it.get("filed"))})
    shares = empty_s
    if srows:
        shares = pick_share_counts(pd.DataFrame(srows))
        shares.insert(0, "cik", cik)
        shares.insert(0, "company_id", company_id)
    return (pd.DataFrame(rows) if rows else empty_f), shares


# Shares outstanding, best source first. The SEC company-facts file leaves out figures reported per
# share class, so companies with several classes (Alphabet, Meta, Comcast, Zoom, ...) and many
# foreign filers have no cover-page count; the balance-sheet count or the latest period's average
# share count is then the best figure known at that filing.
SHARE_CONCEPTS = [("dei", "EntityCommonStockSharesOutstanding"),
                  ("us-gaap", "CommonStockSharesOutstanding"),
                  ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),
                  ("ifrs-full", "WeightedAverageShares")]
MIN_PLAUSIBLE_SHARES = 100_000     # e.g. Fox's cover page once reported "1"


def pick_share_counts(sd: pd.DataFrame) -> pd.DataFrame:
    """One share count per filing: the best source, its latest period, its shortest period
    (latest quarter rather than year-to-date). Cover-page rows of one filing and period are summed
    (one row per share class). Then a filing that reports an OLDER period than one already known
    (an amendment, or a comparative figure) is dropped. Uses only each filing and earlier ones, so
    it is point-in-time."""
    cover = sd[sd["priority"] == 0]
    cover = (cover.groupby(["accn", "period_end", "duration", "priority", "concept"], as_index=False)
                  .agg(val=("val", "sum"), available_utc=("available_utc", "min")))
    sd = pd.concat([cover, sd[sd["priority"] > 0]], ignore_index=True)
    sd = sd[sd["val"] >= MIN_PLAUSIBLE_SHARES].copy()
    if sd.empty:
        return pd.DataFrame(columns=["period_end", "shares", "accn", "available_utc", "concept"])
    sd["period_end"] = pd.to_datetime(sd["period_end"])
    sd["available_utc"] = pd.to_datetime(sd["available_utc"], utc=True)
    sd = sd.sort_values(["accn", "priority", "period_end", "duration"], ascending=[True, True, False, True])
    best = sd.drop_duplicates("accn", keep="first").sort_values(["available_utc", "period_end"])
    best = best[best["period_end"] >= best["period_end"].cummax()]
    best = best.rename(columns={"val": "shares"})
    best["period_end"] = best["period_end"].dt.strftime("%Y-%m-%d")
    return best[["period_end", "shares", "accn", "available_utc", "concept"]].reset_index(drop=True)


def load_news(paths: Paths, ticker: str, company_id: str) -> pd.DataFrame:
    folder = paths.raw / "news" / "alpaca" / file_name(ticker)
    rows = []
    for f in sorted(folder.glob("*.jsonl.gz")) if folder.exists() else []:
        rows.extend(read_jsonl_gz(f))
    if not rows:
        return pd.DataFrame(columns=["company_id", "ticker", "id", "created_utc", "headline", "summary",
                                     "symbols", "source", "url", "available_utc"])
    df = pd.DataFrame(rows)
    df["created_utc"] = pd.to_datetime(df["created_at"], utc=True)
    df["company_id"] = company_id
    df["ticker"] = ticker
    df["symbols"] = df["symbols"].map(lambda v: ",".join(v) if isinstance(v, list) else str(v or ""))
    df["available_utc"] = df["created_utc"]
    return df[["company_id", "ticker", "id", "created_utc", "headline", "summary", "symbols", "source", "url",
               "available_utc"]]


def load_factors(paths: Paths) -> tuple[pd.DataFrame, pd.DataFrame]:
    folder = paths.raw / "factors" / "french"
    out = {}
    for freq in ("daily", "monthly"):
        ff = folder / FRENCH_FILES[f"ff3_{freq}"]
        mom = folder / FRENCH_FILES[f"mom_{freq}"]
        if not (ff.exists() and mom.exists()):
            out[freq] = pd.DataFrame(columns=["date", "mkt_rf", "smb", "hml", "rf", "mom"])
            continue
        a = parse_french_csv(ff.read_bytes())
        b = parse_french_csv(mom.read_bytes())
        df = a.join(b, how="inner") / 100.0          # percent -> decimal
        df.columns = [c.strip().lower().replace("-", "_") for c in df.columns]
        if "mom" not in df.columns:            # momentum file's column is 'Mom' (sometimes padded)
            df = df.rename(columns={df.columns[-1]: "mom"})
        out[freq] = df.reset_index().rename(columns={"index": "date"})
    return out["daily"], out["monthly"]


def load_riskfree(paths: Paths) -> pd.DataFrame:
    f = paths.raw / "riskfree" / "DTB3.csv"
    if not f.exists():
        return pd.DataFrame(columns=["date", "dtb3_annual", "rf_daily", "available_utc"])
    df = pd.read_csv(f)
    df.columns = ["date", "dtb3"]
    df["date"] = pd.to_datetime(df["date"])
    df["dtb3_annual"] = pd.to_numeric(df["dtb3"], errors="coerce") / 100.0
    df = df.dropna(subset=["dtb3_annual"])
    df["rf_daily"] = (1 + df["dtb3_annual"]) ** (1 / 252) - 1
    # FRED publishes a day's rate after that day; available from the next close (conservative)
    df["available_utc"] = [cal.close_utc(cal.next_trading_day(d)) for d in df["date"]]
    return df[["date", "dtb3_annual", "rf_daily", "available_utc"]]


# ----------------------------------------------------------------------------- derived tables
def compute_indicators(bars: pd.DataFrame) -> pd.DataFrame:
    """Scale-free indicators per company from its daily bars (sorted by date).

    Only ratios are stored (RSI, close/SMA, ATR %, Bollinger width/position, momentum from total
    returns), so the split-adjustment scale of Yahoo prices cannot leak future information.
    """
    import pandas_ta as ta
    b = bars.sort_values("date").reset_index(drop=True)
    c, h, low = b["close"].astype(float), b["high"].astype(float), b["low"].astype(float)
    out = pd.DataFrame({"company_id": b["company_id"], "date": b["date"], "available_utc": b["available_utc"]})
    nan = pd.Series(np.nan, index=b.index)

    def safe(x):  # pandas-ta returns None when the history is shorter than the window
        return nan if x is None else x

    out["rsi14"] = safe(ta.rsi(c, length=14))
    macd = ta.macd(c)
    out["macd_hist_pct"] = (macd.iloc[:, 1] / c) if macd is not None else nan
    for n in (20, 50, 200):
        out[f"close_sma{n}"] = c / c.rolling(n).mean() - 1
        out[f"close_ema{n}"] = c / safe(ta.ema(c, length=n)) - 1
    out["atr14_pct"] = safe(ta.atr(h, low, c, length=14)) / c
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std(ddof=0)
    out["bb_width"] = (4 * sd) / mid
    out["bb_pos"] = (c - (mid - 2 * sd)) / (4 * sd)
    tr = (1 + b["ret"].fillna(0.0)).cumprod()
    out["mom_1m"] = tr / tr.shift(21) - 1
    out["mom_3m"] = tr / tr.shift(63) - 1
    out["mom_6m"] = tr / tr.shift(126) - 1
    out["mom_12_1"] = tr.shift(21) / tr.shift(252) - 1
    # Blank every value until its full window of history exists. pandas-ta otherwise emits
    # "warm-up" values computed from too few bars for long series (but nothing for short ones),
    # which would make a value depend on how much data FOLLOWS it.
    bars_so_far = np.arange(1, len(b) + 1)
    need = {"rsi14": 15, "macd_hist_pct": 35, "atr14_pct": 15, "bb_width": 20, "bb_pos": 20}
    for n in (20, 50, 200):
        need[f"close_sma{n}"] = n
        need[f"close_ema{n}"] = n
    for col, n in need.items():
        out.loc[bars_so_far < n, col] = np.nan
    return out


def company_price_tickers(company_map: pd.DataFrame, prices: pd.DataFrame) -> dict[str, str]:
    """Which ticker's prices represent each company: the company id itself if it has data,
    otherwise the member ticker with the most bars."""
    counts = prices.groupby("ticker").size().to_dict() if len(prices) else {}
    out = {}
    for cid, g in company_map.groupby("company_id"):
        tks = [cid] + [t for t in g["ticker"] if t != cid]
        with_data = [t for t in tks if counts.get(t, 0) > 0]
        if with_data:
            out[cid] = cid if cid in with_data else max(with_data, key=lambda t: counts[t])
    return out


def adr_table(ref: pd.DataFrame) -> pd.DataFrame:
    """reference/adr_ratios.csv -> company_id, ordinary_per_ads, valid_from (a ratio applies to
    prices from its valid_from date until the next row; a blank valid_from means 'always')."""
    cols = ["company_id", "ordinary_per_ads", "valid_from"]
    if ref.empty:
        return pd.DataFrame({"company_id": pd.Series(dtype=str), "ordinary_per_ads": pd.Series(dtype=float),
                             "valid_from": pd.Series(dtype="datetime64[ns]")})
    t = ref[ref["ordinary_per_ads"].astype(str).str.strip() != ""][cols].copy()
    t["ordinary_per_ads"] = t["ordinary_per_ads"].astype(float)
    t["valid_from"] = pd.to_datetime(t["valid_from"].replace("", "1900-01-01"))
    return t.reset_index(drop=True)


def ads_ratio_on(dates_and_ids: pd.DataFrame, adr: pd.DataFrame) -> pd.Series:
    """Ordinary shares per depositary share for each (company_id, date) row; 1.0 where none applies."""
    if adr is None or len(adr) == 0:
        return pd.Series(1.0, index=dates_and_ids.index)
    left = dates_and_ids[["company_id", "date"]].copy()
    left["date"] = pd.to_datetime(left["date"]).astype("datetime64[ns]")
    left["_row"] = np.arange(len(left))
    right = adr.rename(columns={"valid_from": "date"}).copy()
    right["date"] = right["date"].astype("datetime64[ns]")
    m = pd.merge_asof(left.sort_values("date"), right.sort_values("date"), on="date", by="company_id",
                      direction="backward").sort_values("_row")
    return pd.Series(m["ordinary_per_ads"].fillna(1.0).to_numpy(), index=dates_and_ids.index)


def compute_weights(bars: pd.DataFrame, shares: pd.DataFrame, spells: pd.DataFrame,
                    adr: pd.DataFrame | None = None) -> pd.DataFrame:
    """Daily company-level index weights: market cap = actual price x latest shares known by that
    close (sum of share classes, D27) / ordinary shares per ADS on that date, over the companies
    that are members at that close."""
    if bars.empty:
        return pd.DataFrame(columns=["date", "company_id", "mcap", "weight", "available_utc"])
    b = bars[["company_id", "date", "raw_close", "available_utc"]].sort_values("available_utc")
    s = shares.dropna(subset=["shares"]).sort_values("available_utc")[["company_id", "shares", "available_utc"]]
    s = s.rename(columns={"available_utc": "shares_known_utc"})
    s["shares"] = s["shares"].astype(float)
    s["shares_known_utc"] = pd.to_datetime(s["shares_known_utc"], utc=True)
    m = pd.merge_asof(b, s.sort_values("shares_known_utc"), left_on="available_utc",
                      right_on="shares_known_utc", by="company_id", direction="backward")
    m["ordinary_per_ads"] = ads_ratio_on(m, adr)
    m["mcap"] = m["raw_close"] * m["shares"] / m["ordinary_per_ads"]
    sp = spells
    member = np.zeros(len(m), dtype=bool)
    for cid, g in sp.groupby("ticker"):
        idx = m.index[m["company_id"] == cid]
        if len(idx) == 0:
            continue
        t = m.loc[idx, "available_utc"]
        ok = np.zeros(len(idx), dtype=bool)
        for r in g.itertuples():
            ok |= ((t >= r.start_utc) & (pd.isna(r.end_utc) | (t < r.end_utc))).to_numpy()
        member[np.asarray(idx)] = ok
    m = m[member & m["mcap"].notna() & (m["mcap"] > 0)].copy()
    m["weight"] = m["mcap"] / m.groupby("date")["mcap"].transform("sum")
    return m[["date", "company_id", "mcap", "weight", "available_utc"]].reset_index(drop=True)


def truncate(df: pd.DataFrame, cutoff: pd.Timestamp, col: str = "available_utc") -> pd.DataFrame:
    return df[df[col] <= cutoff].reset_index(drop=True) if len(df) else df


def truncate_spells(spells: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    s = spells[spells["start_utc"] <= cutoff].copy()
    s.loc[s["end_utc"] > cutoff, "end_utc"] = pd.NaT
    return s.reset_index(drop=True)


# ----------------------------------------------------------------------------- build
def build(cfg_path: str | Path = CONFIG_DIR / "base.yaml", out: Path | None = None,
          cutoff_utc: pd.Timestamp | None = None) -> Path:
    """Build the DuckDB store. ``cutoff_utc`` (tests): build as if today were that time."""
    import duckdb
    cfg = load_config(cfg_path)
    paths = Paths.from_config(cfg).ensure()
    configure_third_party_caches(paths)
    out = Path(out) if out else paths.duckdb_file

    company_map = pd.read_csv(paths.derived / "company_map.csv", dtype=str)
    spells_t = _read_csv_utc(paths.derived / "ndx_membership.csv", ("start_utc", "end_utc"))
    spells_c = _read_csv_utc(paths.derived / "ndx_membership_companies.csv", ("start_utc", "end_utc"))
    ticker_ciks = pd.read_csv(paths.raw / "edgar" / "ticker_ciks.csv", dtype=str).fillna("")
    tickers = sorted(company_map["ticker"])
    cid_of = dict(zip(company_map["ticker"], company_map["company_id"]))

    log.info("prices")
    prices = load_prices(paths, tickers)
    prices["company_id"] = prices["ticker"].map(cid_of)

    benchmarks = load_prices(paths, BENCHMARKS)

    log.info("companies, SEC facts and shares")
    sic_table = load_reference("sic_to_sector.csv")
    so = load_reference("sector_overrides.csv")
    sector_over = dict(zip(so["company_id"], so["sector"]))
    adr = adr_table(load_reference("adr_ratios.csv"))
    latest_adr = adr.sort_values("valid_from").groupby("company_id")["ordinary_per_ads"].last().to_dict()
    names = {}
    tn = paths.derived / "ticker_names.csv"
    if tn.exists():
        names = dict(pd.read_csv(tn, dtype=str).fillna("")[["ticker", "name"]].values)
    comp_rows, fund_frames, share_frames, filing_frames = [], [], [], []
    for cid, g in company_map.groupby("company_id"):
        ciks = sorted({c for c in ticker_ciks[ticker_ciks["ticker"].isin(g["ticker"])]["cik"] if c})
        main, sic, state, forms, fname = {}, "", "", [], ""
        for cik in ciks:
            m, filings = load_submissions(paths, cik)
            if m and not main:
                main = m
            filings["cik"] = cik
            filing_frames.append(filings)
            f, s = load_facts(paths, cik, cid, filings)
            fund_frames.append(f)
            share_frames.append(s)
            forms += list(filings["form"])
        if main:
            sic = str(main.get("sic", "") or "")
            state = (main.get("addresses", {}).get("business", {}) or {}).get("stateOrCountry", "") or ""
            fname = main.get("name", "")
        periodic = [f for f in forms if f in ("10-K", "20-F", "40-F")]
        filer = max(set(periodic), key=periodic.count) if periodic else ""
        comp_rows.append({"company_id": cid, "tickers": ",".join(sorted(g["ticker"])),
                          "name": names.get(cid) or fname, "edgar_name": fname, "cik": ",".join(ciks),
                          "sic": sic, "sector": sector_over.get(cid) or sector_for_sic(sic, sic_table),
                          "state_or_country": state, "is_us": state in US_STATES if state else None,
                          "annual_form": filer, "ordinary_per_ads": latest_adr.get(cid)})
    companies = pd.DataFrame(comp_rows)
    fundamentals = pd.concat([f for f in fund_frames if len(f)], ignore_index=True) if any(len(f) for f in fund_frames) \
        else fund_frames[0] if fund_frames else pd.DataFrame()
    shares = pd.concat([s for s in share_frames if len(s)], ignore_index=True) if any(len(s) for s in share_frames) \
        else pd.DataFrame(columns=SHARE_COLUMNS)
    filings_all = pd.concat(filing_frames, ignore_index=True) if filing_frames else pd.DataFrame()

    log.info("news")
    nf = [load_news(paths, t, cid_of[t]) for t in tickers]
    nf = [f for f in nf if len(f)] or [load_news(paths, "__none__", "")]
    news = pd.concat(nf, ignore_index=True).drop_duplicates(subset=["company_id", "id"]).reset_index(drop=True)

    ff_daily, ff_monthly = load_factors(paths)
    riskfree = load_riskfree(paths)

    if cutoff_utc is not None:
        cutoff_utc = cal.require_utc(cutoff_utc)
        prices, news, riskfree = truncate(prices, cutoff_utc), truncate(news, cutoff_utc), truncate(riskfree, cutoff_utc)
        benchmarks = truncate(benchmarks, cutoff_utc)
        fundamentals, shares = truncate(fundamentals, cutoff_utc), truncate(shares, cutoff_utc)
        if len(filings_all):
            filings_all = truncate(filings_all, cutoff_utc)
        spells_t, spells_c = truncate_spells(spells_t, cutoff_utc), truncate_spells(spells_c, cutoff_utc)

    log.info("indicators and index weights")
    rep = company_price_tickers(company_map, prices)
    rep_df = pd.DataFrame(list(rep.items()), columns=["company_id", "ticker"])
    cbars = prices.merge(rep_df, on=["company_id", "ticker"], how="inner") if len(prices) else prices
    indicators = pd.concat([compute_indicators(g) for _, g in cbars.groupby("company_id")], ignore_index=True) \
        if len(cbars) else pd.DataFrame()
    weights = compute_weights(cbars, shares, spells_c, adr)

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".building.duckdb")
    if tmp.exists():
        tmp.unlink()
    con = duckdb.connect(str(tmp))
    tables = {"company_map": company_map, "companies": companies, "membership_ticker": spells_t,
              "membership_company": spells_c, "ticker_cik": ticker_ciks, "prices": prices,
              "company_price_ticker": rep_df,
              "fundamentals": fundamentals, "shares": shares, "filings": filings_all, "news": news,
              "indicators": indicators, "index_weights": weights, "benchmarks": benchmarks, "factors_daily": ff_daily,
              "factors_monthly": ff_monthly, "riskfree": riskfree}
    for name, df in tables.items():
        con.register("_df", df)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM _df")
        con.unregister("_df")
    manifest_f = paths.raw / "manifest.jsonl"
    raw_digest = hashlib.sha256(manifest_f.read_bytes()).hexdigest() if manifest_f.exists() else ""
    info = pd.DataFrame([{"table_name": n, "rows": len(df)} for n, df in tables.items()])
    info["built_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    info["schema_version"] = SCHEMA_VERSION
    info["raw_manifest_sha256"] = raw_digest
    info["cutoff_utc"] = str(cutoff_utc) if cutoff_utc is not None else ""
    con.register("_df", info)
    con.execute("CREATE TABLE build_manifest AS SELECT * FROM _df")
    con.close()
    if out.exists():
        out.unlink()
    tmp.replace(out)
    return out


def main(argv: list[str] | None = None) -> int:
    from quantagents.logs import setup_logging
    ap = argparse.ArgumentParser(description="Build the QuantAgents DuckDB data store from raw downloads")
    ap.add_argument("--config", default=str(CONFIG_DIR / "base.yaml"))
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    setup_logging(Paths.from_config(cfg).logs, "etl")
    out = build(args.config)
    import duckdb
    con = duckdb.connect(str(out), read_only=True)
    print(f"DuckDB written: {out}")
    print(con.execute("SELECT table_name, rows FROM build_manifest ORDER BY table_name").df().to_string(index=False))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
