"""Shared pieces for all downloaders.

- Source interfaces, so a data source can be swapped (e.g. a paid membership dataset)
  without touching the rest of the code (brief open decision 1).
- ``HttpClient``: rate-limited, retrying HTTP with an identifying User-Agent.
- ``Manifest``: one JSON line per downloaded file (source, path, rows, sha256, time).
  A file listed in the manifest with a matching checksum is skipped on re-run (resume).
"""
from __future__ import annotations

import abc
import gzip
import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------------- interfaces
class MembershipSource(abc.ABC):
    """Produces index membership snapshots: which tickers were members at which time."""
    name: str

    @abc.abstractmethod
    def download(self, start: date, end: date) -> list[Path]: ...

    @abc.abstractmethod
    def snapshots(self) -> pd.DataFrame:
        """Columns: snapshot_utc (tz-aware), ticker, source_ref. One row per member per snapshot."""


class PriceSource(abc.ABC):
    name: str

    @abc.abstractmethod
    def download(self, tickers: Iterable[str], start: date, end: date) -> dict[str, Path | None]:
        """Returns {ticker: file or None if no data}."""


class NewsSource(abc.ABC):
    name: str

    @abc.abstractmethod
    def download(self, tickers: Iterable[str], start: date, end: date) -> dict[str, list[Path]]: ...


class FundamentalsSource(abc.ABC):
    name: str

    @abc.abstractmethod
    def download(self, tickers: Iterable[str]) -> dict[str, list[Path]]: ...


# ----------------------------------------------------------------------------- HTTP
class RateLimiter:
    def __init__(self, per_second: float):
        self.min_interval = 1.0 / per_second
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._last + self.min_interval - now
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


class HttpError(RuntimeError):
    pass


class HttpClient:
    """GET with rate limiting and retries on 429 / 5xx / connection errors."""

    RETRY_STATUS = {429, 500, 502, 503, 504}

    def __init__(self, per_second: float, headers: dict[str, str] | None = None,
                 max_retries: int = 5, backoff: float = 2.0, timeout: float = 60.0,
                 session: requests.Session | None = None):
        self.limiter = RateLimiter(per_second)
        self.session = session or requests.Session()
        self.session.headers.update(headers or {})
        self.max_retries = max_retries
        self.backoff = backoff
        self.timeout = timeout

    def get(self, url: str, params: dict[str, Any] | None = None,
            allow_404: bool = False) -> requests.Response | None:
        for attempt in range(self.max_retries + 1):
            self.limiter.wait()
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise HttpError(f"GET {url} failed: {type(exc).__name__}") from None
                self._sleep(attempt, None)
                continue
            if resp.status_code == 404 and allow_404:
                return None
            if resp.status_code in self.RETRY_STATUS and attempt < self.max_retries:
                self._sleep(attempt, resp.headers.get("Retry-After"))
                continue
            if resp.status_code >= 400:
                # never include headers (they may carry keys) in the error
                raise HttpError(f"GET {url} returned HTTP {resp.status_code}")
            return resp
        raise HttpError(f"GET {url} failed after retries")  # pragma: no cover

    def _sleep(self, attempt: int, retry_after: str | None) -> None:
        try:
            wait = float(retry_after) if retry_after else self.backoff ** (attempt + 1)
        except ValueError:
            wait = self.backoff ** (attempt + 1)
        log.info("retrying in %.0fs", wait)
        time.sleep(min(wait, 120))


# ----------------------------------------------------------------------------- files
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json_gz(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(obj, fh)
    tmp.replace(path)


def read_json_gz(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def write_jsonl_gz(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    tmp.replace(path)


def read_jsonl_gz(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_text_gz(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        fh.write(text)
    tmp.replace(path)


def read_text_gz(path: Path) -> str:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return fh.read()


@dataclass
class ManifestEntry:
    source: str
    path: str          # relative to the raw folder, forward slashes
    rows: int
    sha256: str
    downloaded_utc: str
    params: dict


class Manifest:
    """Append-only JSON-lines manifest at <raw>/manifest.jsonl. The last entry per path wins."""

    def __init__(self, raw_dir: Path):
        self.raw_dir = raw_dir
        self.file = raw_dir / "manifest.jsonl"
        self._lock = threading.Lock()
        self._entries: dict[str, ManifestEntry] = {}
        if self.file.exists():
            with open(self.file, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        e = ManifestEntry(**json.loads(line))
                        self._entries[e.path] = e

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.raw_dir.resolve()).as_posix()

    def record(self, source: str, path: Path, rows: int, params: dict | None = None) -> ManifestEntry:
        e = ManifestEntry(source=source, path=self.rel(path), rows=int(rows),
                          sha256=sha256_file(path),
                          downloaded_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          params=params or {})
        with self._lock:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            with open(self.file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(e.__dict__, default=str) + "\n")
            self._entries[e.path] = e
        return e

    def is_complete(self, path: Path) -> bool:
        """True if ``path`` exists and matches its manifest checksum (so it can be skipped)."""
        if not path.exists():
            return False
        e = self._entries.get(self.rel(path))
        return e is not None and e.sha256 == sha256_file(path)

    def entry(self, path: Path) -> ManifestEntry | None:
        return self._entries.get(self.rel(path))

    def entries(self, source: str | None = None) -> list[ManifestEntry]:
        return [e for e in self._entries.values() if source is None or e.source == source]

    def summary(self) -> pd.DataFrame:
        rows = [{"source": e.source, "files": 1, "rows": e.rows} for e in self._entries.values()]
        if not rows:
            return pd.DataFrame(columns=["source", "files", "rows"])
        return pd.DataFrame(rows).groupby("source", as_index=False).sum()
