"""Historical news from the Alpaca news API (free account).

Endpoint: GET https://data.alpaca.markets/v1beta1/news
Auth headers: APCA-API-KEY-ID / APCA-API-SECRET-KEY. Paginated with ``next_page_token``
(up to 50 articles per page). We keep headline, summary, symbols, source, url and the UTC
``created_at`` / ``updated_at`` timestamps; full article bodies are not downloaded.

Files: raw/news/alpaca/<TICKER>/<YEAR>.jsonl.gz (one per ticker-year, so a stopped download
resumes where it left off). The after-4pm-ET rule is applied later, in the gateway.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

from tqdm import tqdm

from quantagents.data.download.base import HttpClient, Manifest, NewsSource, write_jsonl_gz
from quantagents.data.download.prices import file_name, load_aliases

log = logging.getLogger(__name__)

NEWS_URL = "https://data.alpaca.markets/v1beta1/news"
KEEP = ("id", "headline", "summary", "author", "created_at", "updated_at", "url", "symbols", "source")


@dataclass
class AlpacaNews(NewsSource):
    raw_dir: Path
    manifest: Manifest
    http: HttpClient
    aliases: dict[str, str] = field(default_factory=load_aliases)
    name: str = "alpaca"

    @classmethod
    def create(cls, raw_dir: Path, manifest: Manifest, key_id: str, secret: str,
               per_minute: float) -> "AlpacaNews":
        http = HttpClient(per_minute / 60.0, headers={
            "APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret,
            "User-Agent": "QuantAgents-research/0.1"})
        return cls(raw_dir, manifest, http)

    @property
    def folder(self) -> Path:
        return self.raw_dir / "news" / "alpaca"

    def symbols_for(self, ticker: str) -> str:
        """Old and current symbol for renamed companies (e.g. 'FB,META')."""
        alias = self.aliases.get(ticker)
        return ticker if not alias or alias == ticker else f"{ticker},{alias}"

    def _fetch_range(self, ticker: str, start: str, end: str) -> list[dict]:
        rows: list[dict] = []
        token = None
        while True:
            params = {"symbols": self.symbols_for(ticker), "start": start, "end": end, "limit": 50,
                      "sort": "asc", "include_content": "false"}
            if token:
                params["page_token"] = token
            data = self.http.get(NEWS_URL, params=params).json()
            for item in data.get("news", []):
                rows.append({k: item.get(k) for k in KEEP})
            token = data.get("next_page_token")
            if not token:
                return rows

    def download(self, tickers: Iterable[str], start: date, end: date) -> dict[str, list[Path]]:
        out: dict[str, list[Path]] = {}
        tickers = list(tickers)
        for tk in tqdm(tickers, desc="news", unit="ticker"):
            out[tk] = []
            for year in range(start.year, end.year + 1):
                path = self.folder / file_name(tk) / f"{year}.jsonl.gz"
                if self.manifest.is_complete(path):
                    out[tk].append(path)
                    continue
                y0 = max(start, date(year, 1, 1)).isoformat() + "T00:00:00Z"
                y1 = min(end, date(year, 12, 31)).isoformat() + "T23:59:59Z"
                rows = self._fetch_range(tk, y0, y1)
                write_jsonl_gz(path, rows)
                self.manifest.record("news", path, len(rows), {"ticker": tk, "year": year})
                out[tk].append(path)
        return out
