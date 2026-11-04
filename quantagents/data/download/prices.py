"""Daily prices: yfinance first, then user-supplied CSVs for gaps (decision D3).

For each ticker we store the raw (unadjusted) OHLCV plus ``Adj Close``, dividends and splits,
one Parquet file per ticker: raw/prices/yfinance/<TICKER>.parquet.

Tickers that changed symbol (e.g. FB -> META) are looked up under their current Yahoo
symbol via ``reference/ticker_aliases.csv``. Tickers with no data are listed in
raw/prices/missing.csv so you can supply files in D:\\...\\qa_store\\manual_prices\\
(<TICKER>.csv with columns date,open,high,low,close,adj_close,volume[,dividends,splits]).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
from tqdm import tqdm

from quantagents.config import REPO_ROOT
from quantagents.data.download.base import Manifest, PriceSource

log = logging.getLogger(__name__)

PRICE_COLUMNS = ["open", "high", "low", "close", "adj_close", "volume", "dividends", "splits"]
_YF_RENAME = {"Open": "open", "High": "high", "Low": "low", "Close": "close",
              "Adj Close": "adj_close", "Volume": "volume", "Dividends": "dividends",
              "Stock Splits": "splits"}
BENCHMARKS = ["QQQ", "^NDX"]


def load_aliases(path: Path = REPO_ROOT / "reference" / "ticker_aliases.csv") -> dict[str, str]:
    """{index ticker: Yahoo symbol} for tickers whose Yahoo symbol differs."""
    if not path.exists():
        return {}
    df = pd.read_csv(path, comment="#", dtype=str).fillna("")
    return {r.ticker.strip().upper(): r.yahoo_symbol.strip() for r in df.itertuples()
            if r.yahoo_symbol.strip()}


def file_name(ticker: str) -> str:
    """Windows-safe file name for a ticker ('^NDX' -> '_NDX')."""
    return ticker.replace("^", "_").replace("/", "-")


def _yf_fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
    import yfinance as yf
    return yf.Ticker(symbol).history(start=start.isoformat(),
                                     end=(end + timedelta(days=1)).isoformat(),
                                     auto_adjust=False, actions=True, repair=False)


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=_YF_RENAME)
    for c in PRICE_COLUMNS:
        if c not in df.columns:
            df[c] = 0.0 if c in ("dividends", "splits") else pd.NA
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    df.index.name = "date"
    return df[PRICE_COLUMNS].sort_index()


@dataclass
class YFinancePrices(PriceSource):
    raw_dir: Path
    manifest: Manifest
    fetch: Callable[[str, date, date], pd.DataFrame] | None = None  # None = yfinance
    aliases: dict[str, str] = field(default_factory=load_aliases)
    name: str = "yfinance"

    @property
    def folder(self) -> Path:
        return self.raw_dir / "prices" / "yfinance"

    def download(self, tickers: Iterable[str], start: date, end: date) -> dict[str, Path | None]:
        out: dict[str, Path | None] = {}
        missing = []
        tickers = list(tickers)
        for tk in tqdm(tickers, desc="prices", unit="ticker", disable=len(tickers) < 3):
            path = self.folder / f"{file_name(tk)}.parquet"
            if self.manifest.is_complete(path):
                out[tk] = path
                continue
            symbol = self.aliases.get(tk, tk)
            try:
                df = (self.fetch or _yf_fetch)(symbol, start, end)
            except Exception as exc:  # yfinance raises many kinds of errors for dead tickers
                log.warning("%s (%s): yfinance error %s", tk, symbol, type(exc).__name__)
                df = pd.DataFrame()
            if df is None or df.empty:
                out[tk] = None
                missing.append({"ticker": tk, "yahoo_symbol": symbol, "reason": "no data from yfinance"})
                continue
            df = normalise(df)
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path)
            self.manifest.record("prices", path, len(df), {"symbol": symbol, "start": str(start), "end": str(end)})
            out[tk] = path
        self._write_missing(missing)
        return out

    def _write_missing(self, missing: list[dict]) -> None:
        f = self.raw_dir / "prices" / "missing.csv"
        f.parent.mkdir(parents=True, exist_ok=True)
        old = pd.read_csv(f, dtype=str) if f.exists() else pd.DataFrame(columns=["ticker", "yahoo_symbol", "reason"])
        new = pd.concat([old, pd.DataFrame(missing, columns=["ticker", "yahoo_symbol", "reason"])])
        new = new.drop_duplicates("ticker", keep="last")
        have = {p.stem for p in self.folder.glob("*.parquet")} if self.folder.exists() else set()
        new = new[~new["ticker"].map(file_name).isin(have)]
        new.to_csv(f, index=False)


def read_manual_prices(manual_dir: Path, ticker: str) -> pd.DataFrame | None:
    """User-supplied CSV for a ticker, normalised to PRICE_COLUMNS, or None."""
    f = manual_dir / f"{file_name(ticker)}.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    need = {"date", "open", "high", "low", "close", "adj_close", "volume"}
    if not need <= set(df.columns):
        raise ValueError(f"{f}: needs columns {sorted(need)}")
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df.set_index("date")
    for c in ("dividends", "splits"):
        if c not in df.columns:
            df[c] = 0.0
    return df[PRICE_COLUMNS].sort_index()
