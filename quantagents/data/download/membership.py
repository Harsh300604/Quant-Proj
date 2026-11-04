"""NASDAQ-100 membership by date, reconstructed for free from Wikipedia's page history.

Method (decision D2):
1. For every snapshot time (by default the 1st and 15th of each month, 00:00 UTC) ask the
   MediaWiki API which revision of the "Nasdaq-100" article was current at that moment.
2. Download that revision's HTML once per revision (gzipped) and parse the member tickers
   (see ``parse_members``: components table, nasdaq.com links, or "(TICKER)" text).
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
USER_AGENT = "QuantAgents-research/0.1 (academic backtest; https://github.com/Harsh300604/Quant-Proj) python-requests"
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


_NASDAQ_HREF = re.compile(
    r"nasdaq\.com/(?:symbol|market-activity/stocks|quotes?)/([A-Za-z]{1,5}(?:[.\-][A-Za-z])?)(?:[/?#]|$)", re.I)
_CONTAINERS = ("table", "ul", "ol", "div", "dl")


def _in_range(n: int) -> bool:
    return MIN_MEMBERS <= n <= MAX_MEMBERS


def _table_column_tickers(html: str) -> list[str]:
    """Tickers from a table with a 'Ticker'/'Symbol' column (current article layout)."""
    best: list[str] = []
    try:
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except (ValueError, ImportError):  # no <table> in this revision
        return best
    for tbl in tables:
        cols = [c for c in tbl.columns if _TICKER_COL.search(" ".join(map(str, c))
                                                            if isinstance(c, tuple) else str(c))]
        if not cols:
            continue
        tickers = sorted({t for t in (clean_ticker(v) for v in tbl[cols[0]].dropna()) if t})
        if _in_range(len(tickers)) and abs(len(tickers) - 100) < abs(len(best) - 100 if best else 999):
            best = tickers
    return best


def _href_tickers(el) -> set[str]:
    found = set()
    for a in el.iter("a"):
        m = _NASDAQ_HREF.search(a.get("href") or "")
        if m:
            t = clean_ticker(m.group(1))
            if t:
                found.add(t)
    return found


def _paren_tickers(el) -> set[str]:
    return {t for t in (clean_ticker(m) for m in _PAREN_TICKER.findall(el.text_content())) if t}


# Lists under these section headings describe PAST members or changes, never the current list.
_EXCLUDED_SECTION = re.compile(r"histor|former|past|previous|change|removed|addition|deletion|delist", re.I)


def _containers_with_section(root):
    """Yield (container element, heading text of the section it starts in), in page order."""
    heading = ""
    for el in root.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag in ("h2", "h3", "h4"):
            heading = re.sub(r"\s+", " ", "".join(el.itertext())).strip()
        elif tag in _CONTAINERS:
            yield el, heading


def _best_container(root, extract) -> list[str]:
    """Tightest single element (list, table or column block) whose tickers number 95-110,
    skipping sections about historical/former components or changes.

    Using the tightest container keeps out tickers mentioned elsewhere on the page.
    """
    best, best_size = None, None
    for el, heading in _containers_with_section(root):
        if _EXCLUDED_SECTION.search(heading) or any(
                _EXCLUDED_SECTION.search("".join(h.itertext())) for h in el.iter("h2", "h3", "h4")):
            continue  # in, or spanning, a section about past members or changes
        found = extract(el)
        if not _in_range(len(found)):
            continue
        size = len(el.text_content())
        if best is None or size < best_size or (size == best_size and abs(len(found) - 100) < abs(len(best) - 100)):
            best, best_size = found, size
    return sorted(best) if best else []


def parse_members(html: str) -> tuple[list[str], str]:
    """Return (sorted tickers, method).

    Tries, in order of reliability:
    1. 'table': a table with a Ticker/Symbol column;
    2. 'link':  links to nasdaq.com quote pages (old "Company (NASDAQ: XXX)" layout);
    3. 'paren': tickers in brackets, e.g. "Apple Inc. (AAPL)";
    for 2 and 3 using the tightest list/table/column block that holds 95-110 tickers.
    Returns ([], 'failed') if no method finds a plausible member count.
    """
    tickers = _table_column_tickers(html)
    if tickers:
        return tickers, "table"
    from lxml import html as lxml_html
    try:
        root = lxml_html.fromstring(html)
    except Exception:
        return [], "failed"
    for method, extract in (("link", _href_tickers), ("paren", _paren_tickers)):
        tickers = _best_container(root, extract)
        if tickers:
            return tickers, method
    return [], "failed"


def diagnose(html: str) -> str:
    """Plain-text description of a page's layout, for fixing the parser (safe to share)."""
    from lxml import html as lxml_html
    root = lxml_html.fromstring(html)
    lines = []
    try:
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except (ValueError, ImportError):
        tables = []
    lines.append(f"tables: {len(tables)}")
    for i, t in enumerate(tables[:8]):
        lines.append(f"  table {i}: {len(t)} rows, columns {[str(c)[:30] for c in t.columns][:6]}")
    lines.append(f"list items: {len(list(root.iter('li')))}; nasdaq.com links: {len(_href_tickers(root))}; "
                 f"(TICKER) patterns on page: {len(_paren_tickers(root))}")
    nav = navbox_titles(html)
    lines.append(f"members box as rendered TODAY (not used - may show current members): "
                 f"{len(nav)} links; template page: {navbox_template_name(html)}")
    boxes = [el for el in root.iter("table", "div") if "navbox" in (el.get("class") or "")]
    lines.append(f"navigation boxes on page: {len(boxes)}; their headings: "
                 f"{[re.sub(r'\\s+', ' ', visible_text(b)[:60]).strip() for b in boxes[:4]]}")
    text = root.text_content()
    for word in ("Apple", "Microsoft", "Activision"):
        i = text.find(word)
        if i >= 0:
            lines.append(f"text near '{word}': {text[max(0, i - 80):i + 160]!r}")
            break
    i = html.find("Apple")
    if i >= 0:
        lines.append(f"html near 'Apple': {html[max(0, i - 300):i + 300]!r}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- point-in-time rules
# IMPORTANT (found 5 Nov 2026): the HTML of an OLD revision is rendered with TODAY's templates.
# Mid-2016 to mid-2018 the article listed members only in the "List of NASDAQ-100 companies"
# navigation box, which is a template - so its rendered HTML shows 2026 members (look-ahead).
# Two rules keep membership point-in-time:
#  1. Every ticker parsed from a revision's HTML must also appear in that revision's own
#     wikitext (the raw text as saved on that date); others are dropped (``verify_in_wikitext``).
#  2. When the list lives in the template, we read the TEMPLATE's own revision as of the
#     snapshot time (its wikitext), map its company links to tickers using article-title ->
#     ticker pairs learned from revisions that show tickers, and report names we cannot map.
_WORD_TICKER = re.compile(r"(?<![A-Za-z])([A-Z]{1,5}(?:[.\-][A-Z])?)(?![A-Za-z])")
_WIKILINK = re.compile(r"\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|[^\[\]]*)?\]\]")


def normalise_title(t: str) -> str:
    t = t.replace("_", " ").strip()
    return t[:1].upper() + t[1:] if t else t


def wiki_title(href: str | None) -> str | None:
    """'/wiki/Apple_Inc.#x' -> 'Apple Inc.'; None for non-article links (Template:, File:, ...)."""
    from urllib.parse import unquote
    if not href or not href.startswith("/wiki/"):
        return None
    t = normalise_title(unquote(href[len("/wiki/"):].split("#")[0]))
    return None if not t or ":" in t else t


def learn_link_tickers(html: str, members: list[str]) -> dict[str, str]:
    """From a revision with verified members: {company article title: ticker}.

    For every list item / table row that mentions exactly one member ticker, the first
    article link in it is taken to be that company.
    """
    from lxml import html as lxml_html
    mset = set(members)
    out: dict[str, str] = {}
    for el in lxml_html.fromstring(html).iter("li", "tr"):
        hits = {clean_ticker(m) for m in _WORD_TICKER.findall(el.text_content())} & mset
        if len(hits) != 1:
            continue
        for a in el.iter("a"):
            t = wiki_title(a.get("href"))
            if t:
                out.setdefault(t, hits.pop())
                break
    return out


def visible_text(el) -> str:
    """Text of an element without embedded <style>/<script> code (Wikipedia puts CSS
    at the start of navigation boxes)."""
    return "".join(el.xpath(".//text()[not(ancestor::style) and not(ancestor::script)]"))


def _members_navbox(root):
    for el in root.iter("table", "div"):
        cls = el.get("class") or ""
        head = re.sub(r"\s+", " ", visible_text(el)[:300]).lower()
        if "navbox" in cls and "nasdaq-100 compan" in head:
            return el
    return None


def navbox_titles(html: str) -> list[str]:
    """Titles linked from the rendered members box. RENDERED WITH TODAY'S TEMPLATE:
    diagnostics only, never used for membership."""
    from lxml import html as lxml_html
    box = _members_navbox(lxml_html.fromstring(html))
    if box is None:
        return []
    titles = []
    for a in box.iter("a"):
        t = wiki_title(a.get("href"))
        if t and "nasdaq-100" not in t.lower() and t not in titles:
            titles.append(t)
    return titles


def navbox_template_name(html: str) -> str | None:
    """'Template:NASDAQ-100' (the members box's template page), from its 'v' (view) link."""
    from urllib.parse import unquote
    from lxml import html as lxml_html
    box = _members_navbox(lxml_html.fromstring(html))
    if box is None:
        return None
    for a in box.iter("a"):
        href = a.get("href") or ""
        if href.startswith("/wiki/Template:"):
            return unquote(href[len("/wiki/"):].split("#")[0]).replace("_", " ")
    return None


def wikitext_link_titles(wikitext: str) -> list[str]:
    """Article titles linked as [[Title]] or [[Title|label]] (namespaced links skipped)."""
    out = []
    for m in _WIKILINK.findall(wikitext):
        t = normalise_title(m)
        if t and ":" not in t and "nasdaq-100" not in t.lower() and t not in out:
            out.append(t)
    return out


def verify_in_wikitext(tickers: list[str], wikitext: str) -> tuple[list[str], list[str]]:
    """(kept, dropped): keep tickers that literally appear in the revision's own wikitext."""
    kept, dropped = [], []
    for t in tickers:
        forms = {t, t.replace("-", ".")}
        if any(re.search(rf"(?<![A-Za-z]){re.escape(f)}(?![A-Za-z])", wikitext) for f in forms):
            kept.append(t)
        else:
            dropped.append(t)
    return kept, dropped


def load_title_tickers(path: Path | None = None) -> dict[str, str]:
    """Hand-made {article title: ticker} for names the automatic matching cannot learn."""
    path = path or REFERENCE / "wiki_title_tickers.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, comment="#", dtype=str).fillna("")
    return {normalise_title(r.title): r.ticker.strip().upper() for r in df.itertuples() if r.title.strip()}


def parse_template(wikitext: str, title_map: dict[str, str]) -> tuple[list[str], list[str]]:
    """(member tickers, unmatched titles) from the members template's wikitext."""
    titles = wikitext_link_titles(wikitext)
    tickers = sorted({title_map[t] for t in titles if t in title_map})
    unmatched = [t for t in titles if t not in title_map]
    return tickers, unmatched


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


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

    def html_file(self, revid: int) -> Path:
        return self.folder / "revisions" / f"{revid}.html.gz"

    def wikitext_file(self, revid: int) -> Path:
        return self.folder / "wikitext" / f"{revid}.txt.gz"

    def template_file(self, title: str, revid: int) -> Path:
        return self.folder / "templates" / _safe(title) / f"{revid}.txt.gz"

    # --- download ---------------------------------------------------------------------
    def _revision_at(self, title: str, t: datetime, content: bool = False) -> dict | None:
        params = {"action": "query", "prop": "revisions", "titles": title, "rvlimit": 1,
                  "rvdir": "older", "rvstart": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "rvprop": "ids|timestamp" + ("|content" if content else ""),
                  "format": "json", "formatversion": 2, "redirects": 1}
        if content:
            params["rvslots"] = "main"
        pages = self.http.get(API_URL, params=params).json().get("query", {}).get("pages", [])
        revs = pages[0].get("revisions") if pages else None
        return revs[0] if revs else None

    @staticmethod
    def _content(rev: dict) -> str:
        if "slots" in rev:
            return rev["slots"]["main"].get("content", "")
        return rev.get("content", "")

    def _download_wikitext(self, revids: list[int]) -> None:
        todo = [r for r in revids if not self.manifest.is_complete(self.wikitext_file(r))]
        for i in range(0, len(todo), 10):   # small batches: large responses can be cut short
            batch = todo[i:i + 10]
            data = self.http.get(API_URL, params={
                "action": "query", "prop": "revisions", "revids": "|".join(map(str, batch)),
                "rvprop": "ids|content", "rvslots": "main", "format": "json", "formatversion": 2}).json()
            for page in data.get("query", {}).get("pages", []):
                for rev in page.get("revisions", []):
                    f = self.wikitext_file(int(rev["revid"]))
                    write_text_gz(f, self._content(rev))
                    self.manifest.record("membership", f, 1, {"revid": rev["revid"], "kind": "wikitext"})
        missing = [r for r in todo if not self.wikitext_file(r).exists()]
        if missing:
            log.warning("wikitext not returned for %d revision(s); rerun to retry: %s", len(missing), missing[:10])

    def download(self, start: date, end: date) -> list[Path]:
        index_file = self.folder / "snapshots.json.gz"
        index = read_json_gz(index_file) if index_file.exists() else {}
        written = []
        for t in tqdm(snapshot_times(start, end, list(self.snapshot_days)), desc="membership", unit="snapshot"):
            key = t.isoformat()
            if key not in index:
                rev = self._revision_at(ARTICLE, t)
                if rev is None:
                    log.warning("no Wikipedia revision before %s", key)
                    continue
                index[key] = {"revid": rev["revid"], "rev_timestamp": rev["timestamp"]}
                write_json_gz(index_file, index)
            revid = index[key]["revid"]
            html_file = self.html_file(revid)
            if not self.manifest.is_complete(html_file):
                resp = self.http.get(API_URL, params={
                    "action": "parse", "oldid": revid, "prop": "text", "format": "json",
                    "formatversion": 2})
                html = resp.json()["parse"]["text"]
                write_text_gz(html_file, html)
                members, _ = parse_members(html)
                self.manifest.record("membership", html_file, len(members), {"revid": revid})
                written.append(html_file)
            if "template_v2" not in index[key]:
                # unless the article has a proper members table, also fetch the members
                # template as it was at time t (preferred over bracket lists, see snapshots())
                html = read_text_gz(html_file)
                info = None
                if parse_members(html)[1] != "table":
                    tname = navbox_template_name(html)
                    trev = self._revision_at(tname, t, content=True) if tname else None
                    if trev:
                        f = self.template_file(tname, trev["revid"])
                        write_text_gz(f, self._content(trev))
                        self.manifest.record("membership", f, 1, {"template": tname, "revid": trev["revid"]})
                        info = {"title": tname, "revid": trev["revid"], "timestamp": trev["timestamp"]}
                index[key]["template_v2"] = info
                write_json_gz(index_file, index)
        self._download_wikitext(sorted({int(v["revid"]) for v in index.values()}))
        if index_file.exists():
            self.manifest.record("membership", index_file, len(index), {"start": str(start), "end": str(end)})
        return written

    # --- parse ------------------------------------------------------------------------
    def snapshots(self) -> pd.DataFrame:
        """One row per (snapshot, member), point-in-time verified. Also sets:
        ``self.unmatched`` - template names with no known ticker (snapshot_utc, revid, title)
        ``self.dropped``   - tickers removed because they are not in that revision's wikitext."""
        cols = ["snapshot_utc", "ticker", "source_ref", "status", "method"]
        self.unmatched = pd.DataFrame(columns=["snapshot_utc", "revid", "title"])
        self.dropped = pd.DataFrame(columns=["snapshot_utc", "revid", "ticker"])
        index_file = self.folder / "snapshots.json.gz"
        if not index_file.exists():
            return pd.DataFrame(columns=cols)
        index = read_json_gz(index_file)
        bad = load_bad_revisions()

        # 1. parse each article revision's HTML, then keep only tickers in its own wikitext
        html: dict[int, str] = {}
        parsed: dict[int, tuple[list[str], str]] = {}
        dropped_by_rev: dict[int, list[str]] = {}
        for info in index.values():
            revid = int(info["revid"])
            if revid in bad or revid in parsed:
                continue
            hf, wf = self.html_file(revid), self.wikitext_file(revid)
            if not hf.exists():
                parsed[revid] = ([], "missing")
                continue
            html[revid] = read_text_gz(hf)
            tickers, method = parse_members(html[revid])
            if tickers:
                if not wf.exists():
                    parsed[revid] = ([], f"{method}-unverified")
                    continue
                kept, dropped = verify_in_wikitext(tickers, read_text_gz(wf))
                dropped_by_rev[revid] = dropped
                tickers = kept if _in_range(len(kept)) else []
                method = method if tickers else f"{method}-failed-verification"
            parsed[revid] = (tickers, method)

        # 2. article title -> ticker, learned from verified revisions (later names win)
        title_map: dict[str, str] = {}
        for revid, (tickers, _) in sorted(parsed.items()):
            if tickers:
                title_map.update(learn_link_tickers(html[revid], tickers))
        title_map.update(load_title_tickers())

        # 3. per snapshot: article list, else the template as it was at that time
        rows, un, dr = [], [], []
        for key, info in sorted(index.items()):
            revid = int(info["revid"])
            if revid in bad:
                continue
            ts = pd.Timestamp(key)
            tickers, method = parsed.get(revid, ([], "missing"))
            ref = f"wiki:{revid}"
            tinfo = info.get("template_v2", info.get("template"))
            if method != "table" and tinfo:
                # priority: article table > template (as of time t) > nasdaq links > (TICKER) text
                tf = self.template_file(tinfo["title"], tinfo["revid"])
                if tf.exists():
                    tk, unmatched = parse_template(read_text_gz(tf), title_map)
                    if _in_range(len(tk)) or not tickers:
                        un += [{"snapshot_utc": ts, "revid": revid, "title": u} for u in unmatched]
                    if _in_range(len(tk)):
                        tickers, method, ref = tk, "template", f"wiki:{revid}+tpl:{tinfo['revid']}"
                    elif not tickers:
                        method, ref = "template-incomplete", f"wiki:{revid}+tpl:{tinfo['revid']}"
            dr += [{"snapshot_utc": ts, "revid": revid, "ticker": d} for d in dropped_by_rev.get(revid, [])]
            status = "ok" if tickers else "needs_review"
            if not tickers:
                rows.append({"snapshot_utc": ts, "ticker": None, "source_ref": ref, "status": status, "method": method})
            for tk in tickers:
                rows.append({"snapshot_utc": ts, "ticker": tk, "source_ref": ref, "status": status, "method": method})
        self.unmatched = pd.DataFrame(un, columns=["snapshot_utc", "revid", "title"])
        self.dropped = pd.DataFrame(dr, columns=["snapshot_utc", "revid", "ticker"])
        return pd.DataFrame(rows, columns=cols)


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
                 window_days: int = 180) -> tuple[pd.DataFrame, list[str]]:
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


MAX_JUMP = 25   # real index changes between two snapshots ~2 weeks apart are far smaller


def snapshot_jumps(snaps: pd.DataFrame) -> pd.DataFrame:
    """Tickers added/removed between consecutive OK snapshots (to spot bad parses)."""
    ok = snaps[(snaps["status"] == "ok") & snaps["ticker"].notna()]
    sets = [(t, set(g["ticker"])) for t, g in ok.groupby("snapshot_utc")]
    rows = []
    for (t0, a), (t1, b) in zip(sets, sets[1:]):
        rows.append({"start": t0, "end": t1, "added": len(b - a), "removed": len(a - b),
                     "change": len(a ^ b), "sample": ", ".join(sorted(b - a)[:6])})
    return pd.DataFrame(rows, columns=["start", "end", "added", "removed", "change", "sample"])


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
    """python -m quantagents.data.download.membership --year 2017   (changes found in a year)
    python -m quantagents.data.download.membership --diagnose      (why snapshots fail to parse)"""
    import argparse
    from quantagents.config import CONFIG_DIR, load_config
    from quantagents.paths import Paths
    ap = argparse.ArgumentParser(description="NASDAQ-100 membership reports")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--year", type=int, help="list membership changes found in this year")
    g.add_argument("--diagnose", action="store_true", help="explain snapshots that need review")
    ap.add_argument("--config", default=str(CONFIG_DIR / "base.yaml"))
    args = ap.parse_args(argv)
    paths = Paths.from_config(load_config(args.config))

    if args.diagnose:
        src = WikipediaMembership(paths.raw, Manifest(paths.raw))
        snaps = src.snapshots()
        if snaps.empty:
            print("no snapshots downloaded yet")
            return 1
        counts = snapshot_counts(snaps)
        counts["year"] = counts["snapshot_utc"].dt.year
        print("Parser version: 6 (skips historical lists; template preferred; jump check)")
        print("Snapshots by year (ok / need review) and parse method:")
        for y, g_ in counts.groupby("year"):
            methods = ", ".join(f"{m}={n}" for m, n in g_["method"].value_counts().items())
            print(f"  {y}: {int((g_['status'] == 'ok').sum())} ok / {int((g_['status'] != 'ok').sum())} review  ({methods})")
        if len(src.dropped):
            d = src.dropped.groupby("ticker").size().sort_values(ascending=False)
            print(f"\nTickers removed by the point-in-time check (in the page HTML but not in that "
                  f"date's own text) - {len(d)} tickers: {', '.join(d.index[:30])}")
        if len(src.unmatched):
            u = src.unmatched.groupby("title").agg(snapshots=("revid", "size"),
                                                   first=("snapshot_utc", "min"),
                                                   last=("snapshot_utc", "max")).reset_index()
            print(f"\nNames in the members template (as it was on each date) with no known ticker ({len(u)}):")
            print("(non-companies here are harmless; for companies, add 'title,ticker' rows to "
                  "reference\\wiki_title_tickers.csv)")
            for r in u.sort_values("first").itertuples():
                print(f"  {r.title!r}: {r.snapshots} snapshots, {r.first.date()} to {r.last.date()}")
        jumps = snapshot_jumps(snaps)
        big = jumps[jumps["change"] > MAX_JUMP]
        top = jumps.sort_values("change", ascending=False).head(5)
        print(f"\nLargest changes between consecutive snapshots (more than {MAX_JUMP} = suspicious):")
        for r in top.itertuples():
            print(f"  {r.start.date()} -> {r.end.date()}: +{r.added} / -{r.removed}  (added e.g. {r.sample})")
        print(f"Suspicious jumps: {len(big)}")
        bad = counts[counts["status"] != "ok"]
        if bad.empty:
            print("All snapshots parsed." if big.empty else "All snapshots parsed, but check the suspicious jumps above.")
            return 0
        for _, row in bad.iloc[[0, len(bad) // 2, -1]].drop_duplicates("source_ref").iterrows():
            revid = int(str(row["source_ref"]).split(":")[1].split("+")[0])
            f = src.folder / "revisions" / f"{revid}.html.gz"
            print(f"\n=== snapshot {row['snapshot_utc'].date()} revision {revid} ===")
            print(diagnose(read_text_gz(f)) if f.exists() else "  (revision file missing)")
        return 0

    f = paths.derived / "ndx_membership.csv"
    if not f.exists():
        print(f"{f} not found - run the membership download first")
        return 1
    spells = pd.read_csv(f)
    for c in ("start_utc", "end_utc"):
        spells[c] = pd.to_datetime(spells[c], utc=True)
    ch = changes_between(spells, date(args.year, 1, 2), date(args.year + 1, 1, 15))
    print(f"Membership changes found from {args.year}-01-02 to {args.year + 1}-01-15 "
          f"(the December reconstitution appears in the 1 January snapshot; dates are within "
          f"~2 weeks unless corrected by hand):")
    print(ch.to_string(index=False) if len(ch) else "  none")
    print(f"\nMembers on {args.year}-12-31: {len(members_at(spells, pd.Timestamp(date(args.year, 12, 31), tz='UTC')))}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
