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
import re
from dataclasses import dataclass
from datetime import date
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
# Every name ever used by every EDGAR filer ("NAME:CIK:" per line) - includes delisted companies
CIK_LOOKUP_URL = "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt"
PERIODIC_FORMS = {"10-K", "10-Q", "20-F", "40-F", "10-K405", "10-KT"}
_SUFFIXES = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC",
             "LLC", "LP", "NV", "SA", "AG", "SE", "HOLDINGS", "HOLDING", "GROUP", "THE", "DE", "NEW",
             "CLASS", "A", "B", "COM"}
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"


def cik10(cik: int | str) -> str:
    return str(int(cik)).zfill(10)


def load_cik_overrides(path: Path = REPO_ROOT / "reference" / "cik_overrides.csv") -> dict[str, str]:
    if not path.exists():
        return {}
    df = pd.read_csv(path, comment="#", dtype=str).fillna("")
    return {r.ticker.strip().upper(): (r.cik.strip().upper() if r.cik.strip().startswith("=") else cik10(r.cik))
            for r in df.itertuples() if r.cik.strip()}


_ONES = ["", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN", "ELEVEN",
         "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN"]
_TENS = ["", "", "TWENTY", "THIRTY", "FORTY", "FIFTY", "SIXTY", "SEVENTY", "EIGHTY", "NINETY"]
_ORD = {"ONE": "FIRST", "TWO": "SECOND", "THREE": "THIRD", "FIVE": "FIFTH", "EIGHT": "EIGHTH",
        "NINE": "NINTH", "TWELVE": "TWELFTH"}


def _ordinal_words(n: int) -> str:
    """21 -> 'TWENTY FIRST' (1-99)."""
    words = [_ONES[n]] if n < 20 else [_TENS[n // 10]] + ([_ONES[n % 10]] if n % 10 else [])
    last = words[-1]
    words[-1] = _ORD.get(last, last[:-1] + "IETH" if last.endswith("Y") else last + "TH")
    return " ".join(words)


def normalize_company(name: str) -> str:
    """'Activision Blizzard, Inc.' / 'ACTIVISION BLIZZARD INC' -> 'ACTIVISION BLIZZARD';
    '21st Century Fox' and 'Twenty-First Century Fox' -> 'TWENTY FIRST CENTURY FOX'."""
    n = re.sub(r"\(.*?\)", " ", str(name)).upper().replace("&", " AND ")
    n = re.sub(r"\b([1-9][0-9]?)(ST|ND|RD|TH)\b", lambda m: " " + _ordinal_words(int(m.group(1))) + " ", n)
    n = re.sub(r"/[A-Z]{2}/", " ", n)                  # state tags like /DE/
    n = re.sub(r"[^A-Z0-9 ]+", " ", n)
    words = [w for w in n.split() if w]
    while words and words[-1] in _SUFFIXES:
        words.pop()
    if words and words[0] == "THE":
        words = words[1:]
    return " ".join(words)


def parse_cik_lookup(text: str) -> dict[str, set[str]]:
    """{normalized name: {cik10, ...}} from cik-lookup-data.txt."""
    out: dict[str, set[str]] = {}
    for line in text.splitlines():
        m = re.match(r"^(.*):(\d{10}):\s*$", line)
        if m:
            key = normalize_company(m.group(1))
            if key:
                out.setdefault(key, set()).add(m.group(2))
    return out


def name_used_during(submissions: dict, names: list[str], start: date, end: date) -> bool:
    """Did the filer carry one of ``names`` at some point in [start, end]?

    Uses the current name and SEC's dated ``formerNames``. Needed because a name can move
    between filers: 'VIACOM INC' was today's Paramount (CBS) until 2005 and the separate new
    Viacom from 2006.
    """
    wanted = {normalize_company(n) for n in names}
    former = submissions.get("formerNames") or []
    s0, e0 = start.isoformat(), end.isoformat()
    for f in former:
        if normalize_company(f.get("name", "")) in wanted:
            f_from, f_to = (f.get("from") or "0000")[:10], (f.get("to") or "9999")[:10]
            if f_from <= e0 and f_to >= s0:
                return True
    if normalize_company(submissions.get("name", "")) in wanted:
        current_from = max(((f.get("to") or "0000")[:10] for f in former), default="0000")
        return current_from <= e0
    return False


def periodic_filings_between(submissions: dict, start: date, end: date) -> int:
    """Number of 10-K/10-Q/20-F/40-F filings dated within [start, end]."""
    recent = submissions.get("filings", {}).get("recent", submissions)
    n = 0
    for form, d in zip(recent.get("form", []), recent.get("filingDate", [])):
        if form in PERIODIC_FORMS and start.isoformat() <= d <= end.isoformat():
            n += 1
    return n


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
        return m

    def name_index(self) -> dict[str, set[str]]:
        path = self.folder / "cik-lookup-data.txt.gz"
        if not self.manifest.is_complete(path):
            from quantagents.data.download.base import write_text_gz
            text = self.http.get(CIK_LOOKUP_URL).content.decode("latin-1")
            write_text_gz(path, text)
            self.manifest.record("edgar", path, text.count("\n"), {"kind": "cik-lookup"})
        from quantagents.data.download.base import read_text_gz
        return parse_cik_lookup(read_text_gz(path))

    def resolve_by_name(self, ticker: str, names: list[str], period: tuple[date, date],
                        index: dict[str, set[str]], taken: set[str]) -> dict:
        """Find the CIK of a company no longer in SEC's current ticker list.

        Candidates: EDGAR filers whose (normalized) name equals one of the company's
        Wikipedia names. Kept: candidates that carried that name during the membership period
        (``name_used_during``). Chosen: the one with the most 10-K/10-Q/20-F filings while the
        company was in the index. CIKs already used by *other companies* are skipped.
        """
        cands = sorted({c for n in names for c in index.get(normalize_company(n), set())} - taken)
        start, end = period
        scored = []
        for c in cands[:12]:
            sub = self._save(SUBMISSIONS_URL.format(name=f"CIK{c}.json"),
                             self.folder / "submissions" / f"CIK{c}.json.gz", "submissions", c)
            window = (date(start.year - 1, 1, 1), end)
            score = periodic_filings_between(sub, *window) if sub and name_used_during(sub, names, *window) else 0
            scored.append((score, c, (sub or {}).get("name", "")))
        scored.sort(key=lambda x: (-x[0], x[1]))
        good = [x for x in scored if x[0] > 0]
        if not good:
            return {"ticker": ticker, "names": " | ".join(names), "cik": "", "edgar_name": "",
                    "candidates": len(cands), "filings_in_period": 0,
                    "confidence": "none - add to reference/cik_overrides.csv"}
        best = good[0]
        confident = len(good) == 1 or good[0][0] >= 2 * good[1][0]
        return {"ticker": ticker, "names": " | ".join(names), "cik": best[1], "edgar_name": best[2],
                "candidates": len(cands), "filings_in_period": best[0],
                "confidence": "high" if confident else "check"}

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

    def download(self, tickers: Iterable[str], names: dict[str, list[str]] | None = None,
                 periods: dict[str, tuple[date, date]] | None = None,
                 company_of: dict[str, str] | None = None) -> dict[str, list[Path]]:
        """``names``/``periods`` (company names and index-membership period per ticker) let
        companies that are no longer listed be found by name (``resolve_by_name``).
        ``company_of`` (ticker -> company id, D27): tickers of one company share one CIK
        (share classes, renames such as Liberty Interactive -> Qurate Retail)."""
        cmap = self.ticker_map()
        out: dict[str, list[Path]] = {}
        missing = []
        aliases = load_aliases()
        overrides = load_cik_overrides()
        tickers = list(tickers)
        company_of = company_of or {}
        comp = lambda t: company_of.get(t, t)  # noqa: E731
        ciks: dict[str, str] = {}
        for tk in tickers:
            o = overrides.get(tk.upper(), "")
            c = (o if o and not o.startswith("=") else "") or cmap.get(tk.upper()) or \
                cmap.get(aliases.get(tk.upper(), "").replace(".", "-"))
            if c:
                ciks[tk] = c

        def share_within_companies():
            by_company: dict[str, str] = {}
            for t, c in ciks.items():
                by_company.setdefault(comp(t), c)
            for t in tickers:
                if t not in ciks and comp(t) in by_company:
                    ciks[t] = by_company[comp(t)]

        share_within_companies()
        groups: dict[str, list[str]] = {}
        for t in tickers:
            if t not in ciks:
                groups.setdefault(comp(t), []).append(t)
        if groups and names:
            index = self.name_index()
            matches = []
            for cid, members in tqdm(sorted(groups.items()), desc="edgar name lookup", unit="company"):
                gnames = list(dict.fromkeys(n for t in members for n in (names.get(t) or [])))
                label = "+".join(members)
                if not gnames:
                    matches.append({"ticker": label, "names": "", "cik": "", "edgar_name": "", "candidates": 0,
                                    "filings_in_period": 0, "confidence": "none - no company name known"})
                    continue
                ps = [(periods or {}).get(t, (date(2014, 1, 1), date(2023, 12, 31))) for t in members]
                period = (min(p[0] for p in ps), max(p[1] for p in ps))
                taken = {c for t, c in ciks.items() if comp(t) != cid}
                m = self.resolve_by_name(label, gnames, period, index, taken)
                matches.append(m)
                if m["cik"]:
                    for t in members:
                        ciks[t] = m["cik"]
            mf = self.folder / "cik_matches.csv"
            mf.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(matches).to_csv(mf, index=False)
        for t, o in overrides.items():          # "=WBD" means: same CIK as ticker WBD
            if o.startswith("=") and t in tickers and o[1:] in ciks:
                ciks[t] = ciks[o[1:]]
        share_within_companies()
        # one table for Phase 2: which CIK each ticker uses, and how it was found
        source = {}
        for t in tickers:
            if t not in ciks:
                source[t] = "missing"
            elif t in overrides:
                source[t] = "override"
            elif cmap.get(t.upper()) == ciks[t]:
                source[t] = "sec_current_list"
            else:
                source[t] = "name_lookup_or_company"
        tf = self.folder / "ticker_ciks.csv"
        tf.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{"ticker": t, "cik": ciks.get(t, ""), "company_id": comp(t), "source": source[t]}
                      for t in tickers]).to_csv(tf, index=False)
        for tk in tqdm(tickers, desc="edgar", unit="ticker"):
            cik = ciks.get(tk)
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
