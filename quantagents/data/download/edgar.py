"""Fundamentals from SEC EDGAR (XBRL company facts) plus filing metadata (submissions).

- Ticker -> CIK: SEC's current list (company_tickers.json), with
  ``reference/cik_overrides.csv`` for tickers no longer listed (delisted or renamed).
- Per CIK we save:
  * companyfacts:  raw/edgar/companyfacts/CIK##########.json.gz (all XBRL facts; each fact
    has the accession number ``accn`` of the filing it came from)
  * submissions:   raw/edgar/submissions/CIK##########.json.gz (+ any "-submissions-NNN"
    pages). These hold each filing's ``acceptanceDateTime`` (used as the availability time,
    brief section 4), the SIC industry code and the business address (sector and country,
    decision D7).
- SEC requires a User-Agent with a contact email and at most 10 requests/second.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
from tqdm import tqdm

from quantagents.config import REPO_ROOT
from quantagents.data.download.base import (
    FundamentalsSource, HttpClient, Manifest, read_json_gz, write_json_gz,
)
from quantagents.data.download.prices import load_aliases

log = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"


def cik10(cik: int | str) -> str:
    return str(int(cik)).zfill(10)


def load_cik_overrides(path: Path = REPO_ROOT / "reference" / "cik_overrides.csv") -> dict[str, str]:
    if not path.exists():
        return {}
    df = pd.read_csv(path, comment="#", dtype=str).fillna("")
    return {r.ticker.strip().upper(): cik10(r.cik) for r in df.itertuples() if r.cik.strip()}


@dataclass
class SecEdgar(FundamentalsSource):
    raw_dir: Path
    manifest: Manifest
    http: HttpClient
    name: str = "sec_edgar"

    @classmethod
    def create(cls, raw_dir: Path, manifest: Manifest, user_agent: str,
               per_second: float) -> "SecEdgar":
        if "@" not in user_agent:
            raise ValueError("SEC_USER_AGENT in .env must include a contact email "
                             "(e.g. 'QuantAgents research name@example.com')")
        http = HttpClient(per_second, headers={"User-Agent": user_agent,
                                               "Accept-Encoding": "gzip, deflate"})
        return cls(raw_dir, manifest, http)

    @property
    def folder(self) -> Path:
        return self.raw_dir / "edgar"

    def ticker_map(self) -> dict[str, str]:
        path = self.folder / "company_tickers.json.gz"
        if not path.exists():
            data = self.http.get(TICKERS_URL).json()
            write_json_gz(path, data)
            self.manifest.record("edgar", path, len(data))
        data = read_json_gz(path)
        m = {v["ticker"].upper().replace(".", "-"): cik10(v["cik_str"]) for v in data.values()}
        m.update(load_cik_overrides())
        return m

    def _save(self, url: str, path: Path, kind: str, cik: str) -> dict | None:
        if self.manifest.is_complete(path):
            return read_json_gz(path)
        resp = self.http.get(url, allow_404=True)
        if resp is None:
            return None
        data = resp.json()
        write_json_gz(path, data)
        rows = len(data.get("facts", {}).get("us-gaap", {})) if kind == "companyfacts" else \
            len(data.get("filings", {}).get("recent", data).get("accessionNumber", []))
        self.manifest.record("edgar", path, rows, {"cik": cik, "kind": kind})
        return data

    def download(self, tickers: Iterable[str]) -> dict[str, list[Path]]:
        cmap = self.ticker_map()
        out: dict[str, list[Path]] = {}
        missing = []
        aliases = load_aliases()
        tickers = list(tickers)
        for tk in tqdm(tickers, desc="edgar", unit="ticker"):
            cik = cmap.get(tk.upper()) or cmap.get(aliases.get(tk.upper(), "").replace(".", "-"))
            if not cik:
                missing.append({"ticker": tk, "reason": "no CIK (add to reference/cik_overrides.csv)"})
                out[tk] = []
                continue
            files = []
            sub_path = self.folder / "submissions" / f"CIK{cik}.json.gz"
            sub = self._save(SUBMISSIONS_URL.format(name=f"CIK{cik}.json"), sub_path, "submissions", cik)
            if sub is not None:
                files.append(sub_path)
                for extra in sub.get("filings", {}).get("files", []):
                    p = self.folder / "submissions" / f"{extra['name'].replace('.json', '')}.json.gz"
                    if self._save(SUBMISSIONS_URL.format(name=extra["name"]), p, "submissions_page", cik) is not None:
                        files.append(p)
            facts_path = self.folder / "companyfacts" / f"CIK{cik}.json.gz"
            if self._save(FACTS_URL.format(cik=cik), facts_path, "companyfacts", cik) is not None:
                files.append(facts_path)
            else:
                missing.append({"ticker": tk, "reason": f"no XBRL company facts for CIK {cik}"})
            out[tk] = files
        f = self.folder / "missing.csv"
        f.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(missing, columns=["ticker", "reason"]).to_csv(f, index=False)
        return out
