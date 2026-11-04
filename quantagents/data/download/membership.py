"""NASDAQ-100 membership by date, reconstructed for free from Wikipedia's page history.

Method (decision D2):
1. For every snapshot time (by default the 1st and 15th of each month, 00:00 UTC) ask the
   MediaWiki API which revision of the "Nasdaq-100" article was current at that moment.
2. Download that revision's HTML once per revision (gzipped) and parse the member tickers
   from the components table (fallback: "Company (TICKER)" list items).
3. Snapshots whose member count is implausible are flagged ``needs_review``.
4. ``build_spells`` turns snapshots into membership spells (ticker, start, end) and applies
   hand corrections from ``reference/ndx_changes_manual.csv`` (exact effective dates from
   Nasdaq announcements) and ``reference/membership_bad_revisions.csv`` (vandalised revisions).

A snapshot taken at time T only uses a revision saved before T, so it is point-in-time
with respect to Wikipedia (edits can lag real changes by days; hand corrections fix the
important ones).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from quantagents.config import REPO_ROOT
from quantagents.data.download.base import (
    HttpClient, Manifest, MembershipSource, read_json_gz, read_text_gz, write_json_gz,
    write_text_gz,
)

log = logging.getLogger(__name__)

API_URL = "https://en.wikipedia.org/w/api.php"
ARTICLE = "Nasdaq-100"
USER_AGENT = "QuantAgents-research/0.1 (academic backtest; python-requests)"
MIN_MEMBERS, MAX_MEMBERS = 95, 110
REFERENCE = REPO_ROOT / "reference"

_TICKER_COL = re.compile(r"ticker|symbol", re.I)
_TICKER_OK = re.compile(r"^[A-Z]{1,5}(-[A-Z])?$")
_PAREN_TICKER = re.compile(r"\(\s*(?:NASDAQ\s*:\s*)?([A-Z]{1,5}(?:\.[A-Z])?)\s*\)")


def snapshot_times(start: date, end: date, days: list[int]) -> list[datetime]:
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        for d in days:
            t = datetime(y, m, d, tzinfo=timezone.utc)
            if start <= t.date() <= end:
                out.append(t)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def clean_ticker(raw: str) -> str | None:
    t = re.sub(r"\[.*?\]", "", str(raw)).strip().upper()
    t = t.replace("NASDAQ:", "").strip().replace(".", "-")
    return t if t and _TICKER_OK.match(t) else None


def parse_members(html: str) -> tuple[list[str], str]:
    """Return (sorted tickers, method). Method is 'table', 'list' or 'failed'."""
    best: list[str] = []
    try:
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except (ValueError, ImportError):  # no <table> in this revision
        tables = []
    for tbl in tables:
        cols = [c for c in tbl.columns if _TICKER_COL.search(" ".join(map(str, c))
                                                            if isinstance(c, tuple) else str(c))]
        if not cols:
            continue
        tickers = sorted({t for t in (clean_ticker(v) for v in tbl[cols[0]].dropna()) if t})
        if MIN_MEMBERS <= len(tickers) <= MAX_MEMBERS and \
                abs(len(tickers) - 100) < abs(len(best) - 100 if best else 999):
            best = tickers
    if best:
        return best, "table"
    items = re.findall(r"<li[^>]*>(.*?)</li>", html, flags=re.S | re.I)
    found = set()
    for it in items:
        text = re.sub(r"<[^>]+>", "", it)
        for m in _PAREN_TICKER.findall(text):
            t = clean_ticker(m)
            if t:
                found.add(t)
    if MIN_MEMBERS <= len(found) <= MAX_MEMBERS:
        return sorted(found), "list"
    return [], "failed"


@dataclass
class WikipediaMembership(MembershipSource):
    raw_dir: Path
    manifest: Manifest
    http: HttpClient | None = None
    snapshot_days: tuple[int, ...] = (1, 15)
    name: str = "wikipedia"

    @classmethod
    def create(cls, raw_dir: Path, manifest: Manifest, per_second: float,
               snapshot_days: list[int]) -> "WikipediaMembership":
        http = HttpClient(per_second, headers={"User-Agent": USER_AGENT})
        return cls(raw_dir, manifest, http, tuple(snapshot_days))

    @property
    def folder(self) -> Path:
        return self.raw_dir / "membership" / "wikipedia"

    # --- download ---------------------------------------------------------------------
    def _revision_at(self, t: datetime) -> dict | None:
        resp = self.http.get(API_URL, params={
            "action": "query", "prop": "revisions", "titles": ARTICLE, "rvlimit": 1,
            "rvdir": "older", "rvstart": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rvprop": "ids|timestamp", "format": "json", "formatversion": 2, "redirects": 1})
        pages = resp.json().get("query", {}).get("pages", [])
        revs = pages[0].get("revisions") if pages else None
        return revs[0] if revs else None

    def download(self, start: date, end: date) -> list[Path]:
        index_file = self.folder / "snapshots.json.gz"
        index = read_json_gz(index_file) if index_file.exists() else {}
        written = []
        for t in tqdm(snapshot_times(start, end, list(self.snapshot_days)), desc="membership", unit="snapshot"):
            key = t.isoformat()
            if key not in index:
                rev = self._revision_at(t)
                if rev is None:
                    log.warning("no Wikipedia revision before %s", key)
                    continue
                index[key] = {"revid": rev["revid"], "rev_timestamp": rev["timestamp"]}
                write_json_gz(index_file, index)
            revid = index[key]["revid"]
            html_file = self.folder / "revisions" / f"{revid}.html.gz"
            if self.manifest.is_complete(html_file):
                continue
            resp = self.http.get(API_URL, params={
                "action": "parse", "oldid": revid, "prop": "text", "format": "json",
                "formatversion": 2})
            html = resp.json()["parse"]["text"]
            write_text_gz(html_file, html)
            members, _ = parse_members(html)
            self.manifest.record("membership", html_file, len(members), {"revid": revid})
            written.append(html_file)
        if index_file.exists():
            self.manifest.record("membership", index_file, len(index), {"start": str(start), "end": str(end)})
        return written

    # --- parse ------------------------------------------------------------------------
    def snapshots(self) -> pd.DataFrame:
        index_file = self.folder / "snapshots.json.gz"
        if not index_file.exists():
            return pd.DataFrame(columns=["snapshot_utc", "ticker", "source_ref", "status"])
        index = read_json_gz(index_file)
        bad = load_bad_revisions()
        parsed: dict[int, tuple[list[str], str]] = {}
        rows = []
        for key, info in sorted(index.items()):
            revid = int(info["revid"])
            if revid in bad:
                continue
            if revid not in parsed:
                f = self.folder / "revisions" / f"{revid}.html.gz"
                parsed[revid] = parse_members(read_text_gz(f)) if f.exists() else ([], "missing")
            tickers, method = parsed[revid]
            status = "ok" if tickers else "needs_review"
            ts = pd.Timestamp(key)
            if not tickers:
                rows.append({"snapshot_utc": ts, "ticker": None, "source_ref": f"wiki:{revid}",
                             "status": status, "method": method})
            for tk in tickers:
                rows.append({"snapshot_utc": ts, "ticker": tk, "source_ref": f"wiki:{revid}",
                             "status": status, "method": method})
        return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- spells
def load_bad_revisions(path: Path = REFERENCE / "membership_bad_revisions.csv") -> set[int]:
    if not path.exists():
        return set()
    df = pd.read_csv(path, comment="#")
    return set(int(x) for x in df["revid"].dropna())


def load_manual_changes(path: Path = REFERENCE / "ndx_changes_manual.csv") -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["effective_date", "ticker", "action", "source", "note"])
    df = pd.read_csv(path, comment="#", dtype=str).fillna("")
    df["effective_date"] = pd.to_datetime(df["effective_date"]).dt.tz_localize("UTC")
    df["ticker"] = df["ticker"].str.upper().str.strip()
    df["action"] = df["action"].str.lower().str.strip()
    bad = set(df["action"]) - {"add", "remove"}
    if bad:
        raise ValueError(f"ndx_changes_manual.csv: unknown action(s) {bad}")
    return df


def build_spells(snaps: pd.DataFrame, manual: pd.DataFrame | None = None,
                 window_days: int = 31) -> tuple[pd.DataFrame, list[str]]:
    """Snapshots -> spells (ticker, start_utc, end_utc[exclusive or NaT], source).

    A ticker's spell starts at the first snapshot where it appears and ends at the first
    later snapshot where it is absent. Manual changes then move a nearby boundary to the
    exact effective date. Returns (spells, warnings).
    """
    ok = snaps[(snaps["status"] == "ok") & snaps["ticker"].notna()]
    times = sorted(ok["snapshot_utc"].drop_duplicates())
    members = {t: set(g["ticker"]) for t, g in ok.groupby("snapshot_utc")}
    spells: list[dict] = []
    open_: dict[str, pd.Timestamp] = {}
    for t in times:
        cur = members[t]
        for tk in cur - set(open_):
            open_[tk] = t
        for tk in set(open_) - cur:
            spells.append({"ticker": tk, "start_utc": open_.pop(tk), "end_utc": t, "source": "wikipedia"})
    for tk, st in open_.items():
        spells.append({"ticker": tk, "start_utc": st, "end_utc": pd.NaT, "source": "wikipedia"})
    df = pd.DataFrame(spells, columns=["ticker", "start_utc", "end_utc", "source"])
    for col in ("start_utc", "end_utc"):
        df[col] = pd.to_datetime(df[col], utc=True)
    warnings: list[str] = []
    if manual is not None and len(manual):
        win = pd.Timedelta(days=window_days)
        for _, ch in manual.iterrows():
            d, tk = ch["effective_date"], ch["ticker"]
            col = "start_utc" if ch["action"] == "add" else "end_utc"
            cand = df[(df["ticker"] == tk) & df[col].notna() &
                      (df[col] >= d - win) & (df[col] <= d + win)]
            if cand.empty:
                warnings.append(f"manual {ch['action']} {tk} {d.date()}: no matching boundary "
                                f"within {window_days} days; not applied")
                continue
            idx = (cand[col] - d).abs().idxmin()
            df.loc[idx, col] = d
            df.loc[idx, "source"] = f"wikipedia+manual({ch.get('source', '')})"
    df = df.sort_values(["ticker", "start_utc"]).reset_index(drop=True)
    return df, warnings


def members_at(spells: pd.DataFrame, t: pd.Timestamp) -> list[str]:
    """Tickers whose spell covers time ``t`` (start <= t < end)."""
    t = pd.Timestamp(t)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    m = (spells["start_utc"] <= t) & (spells["end_utc"].isna() | (spells["end_utc"] > t))
    return sorted(spells.loc[m, "ticker"].unique())


def removed_members(spells: pd.DataFrame, first: pd.Timestamp, last: pd.Timestamp) -> list[str]:
    """Members at ``first`` that are no longer members at ``last``."""
    return sorted(set(members_at(spells, first)) - set(members_at(spells, last)))


def save_spells(spells: pd.DataFrame, derived_dir: Path) -> Path:
    derived_dir.mkdir(parents=True, exist_ok=True)
    out = derived_dir / "ndx_membership.csv"
    spells.to_csv(out, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    return out


def snapshot_counts(snaps: pd.DataFrame) -> pd.DataFrame:
    g = snaps.groupby("snapshot_utc").agg(
        members=("ticker", lambda s: s.notna().sum()), status=("status", "first"),
        method=("method", "first"), source_ref=("source_ref", "first")).reset_index()
    return g


def first_snapshot_on_or_after(snaps: pd.DataFrame, d: date) -> pd.Timestamp | None:
    t = pd.Timestamp(d, tz="UTC")
    s = sorted(x for x in snaps["snapshot_utc"].drop_duplicates() if x >= t)
    return s[0] if s else None


def last_snapshot_on_or_before(snaps: pd.DataFrame, d: date) -> pd.Timestamp | None:
    t = pd.Timestamp(d, tz="UTC") + timedelta(days=1)
    s = sorted(x for x in snaps["snapshot_utc"].drop_duplicates() if x < t)
    return s[-1] if s else None


def changes_between(spells: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Every addition/removal with a date in [start, end], for checking against Nasdaq."""
    s, e = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    adds = spells[(spells["start_utc"] >= s) & (spells["start_utc"] < e)]
    rems = spells[spells["end_utc"].notna() & (spells["end_utc"] >= s) & (spells["end_utc"] < e)]
    out = pd.concat([
        pd.DataFrame({"date": adds["start_utc"].dt.date, "ticker": adds["ticker"], "change": "added"}),
        pd.DataFrame({"date": rems["end_utc"].dt.date, "ticker": rems["ticker"], "change": "removed"}),
    ])
    return out.sort_values(["date", "change", "ticker"]).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    """Print membership changes for a year:  python -m quantagents.data.download.membership --year 2017"""
    import argparse
    from quantagents.config import CONFIG_DIR, load_config
    from quantagents.paths import Paths
    ap = argparse.ArgumentParser(description="List NASDAQ-100 membership changes found for one year")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--config", default=str(CONFIG_DIR / "base.yaml"))
    args = ap.parse_args(argv)
    f = Paths.from_config(load_config(args.config)).derived / "ndx_membership.csv"
    if not f.exists():
        print(f"{f} not found - run the membership download first")
        return 1
    spells = pd.read_csv(f)
    for c in ("start_utc", "end_utc"):
        spells[c] = pd.to_datetime(spells[c], utc=True)
    ch = changes_between(spells, date(args.year, 1, 2), date(args.year, 12, 31))
    print(f"Membership changes found in {args.year} (dates are within ~2 weeks unless corrected by hand):")
    print(ch.to_string(index=False) if len(ch) else "  none")
    print(f"\nMembers on {args.year}-12-31: {len(members_at(spells, pd.Timestamp(date(args.year, 12, 31), tz='UTC')))}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
