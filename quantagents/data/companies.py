"""Company-level universe (decision D27): one entry per company, not per share class.

Tickers are grouped into one company when:
- **share classes**: the same Wikipedia company article is linked to both tickers in the
  member lists *and* the tickers look like class variants of each other (GOOG/GOOGL,
  FOX/FOXA, DISCA/DISCK: common prefix of 3+ letters, differing only in the last letter);
- **renames**: ``reference/ticker_aliases.csv`` maps one to the other (FB -> META);
- ``reference/company_overrides.csv`` says so (hand corrections; wins over everything).

The company id is the group's ticker that appears in the most membership snapshots.
Every grouping is written to ``derived/company_map.csv`` with its reason, for review.
Tracking stocks (e.g. LMCA vs BATRA) are different assets and are NOT merged unless
an override says so.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from quantagents.config import REPO_ROOT

OVERRIDES = REPO_ROOT / "reference" / "company_overrides.csv"


def looks_like_share_classes(a: str, b: str) -> bool:
    """GOOG/GOOGL, FOX/FOXA, DISCA/DISCK, LBTYA/LBTYK -> True; AAPL/AMZN -> False."""
    if a == b:
        return False
    p = os.path.commonprefix([a, b])
    return len(p) >= 3 and len(a) - len(p) <= 1 and len(b) - len(p) <= 1


class _UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        self.parent[self.find(a)] = self.find(b)


def load_company_overrides(path: Path = OVERRIDES) -> dict[str, str]:
    if not path.exists():
        return {}
    df = pd.read_csv(path, comment="#", dtype=str).fillna("")
    return {r.ticker.strip().upper(): r.company_id.strip().upper() for r in df.itertuples()
            if r.ticker.strip() and r.company_id.strip()}


def build_company_map(tickers: list[str], link_pairs: pd.DataFrame, aliases: dict[str, str],
                      snapshot_counts: dict[str, int],
                      overrides: dict[str, str] | None = None) -> pd.DataFrame:
    """Columns: ticker, company_id, reason. One row per index ticker."""
    tickers = sorted(set(tickers))
    tset = set(tickers)
    uf = _UnionFind()
    reasons: dict[str, set[str]] = {t: set() for t in tickers}
    for t in tickers:
        uf.find(t)
    # share classes: same article, class-like tickers
    for title, g in link_pairs[link_pairs["ticker"].isin(tset)].groupby("title"):
        tks = sorted(set(g["ticker"]))
        for i, a in enumerate(tks):
            for b in tks[i + 1:]:
                if looks_like_share_classes(a, b):
                    uf.union(a, b)
                    reasons[a].add(f"share class of {b} ({title})")
                    reasons[b].add(f"share class of {a} ({title})")
    # renames
    for old, new in aliases.items():
        if old in tset:
            uf.union(old, new)
            reasons[old].add(f"renamed -> {new}")
            if new in tset:
                reasons[new].add(f"renamed from {old}")
    groups: dict[str, list[str]] = {}
    for t in tickers:
        groups.setdefault(uf.find(t), []).append(t)
    cid = {}
    for members in groups.values():
        best = sorted(members, key=lambda x: (-snapshot_counts.get(x, 0), x))[0]
        for t in members:
            cid[t] = best
    for t, c in (overrides if overrides is not None else load_company_overrides()).items():
        if t in tset:
            cid[t] = c
            reasons[t].add("override")
    return pd.DataFrame([{"ticker": t, "company_id": cid[t],
                          "reason": "; ".join(sorted(reasons[t])) or "single ticker"} for t in tickers])


def to_company_snapshots(snaps: pd.DataFrame, company_map: pd.DataFrame) -> pd.DataFrame:
    """Replace tickers by company ids; one row per company per snapshot."""
    m = dict(zip(company_map["ticker"], company_map["company_id"]))
    out = snaps.copy()
    out["ticker"] = out["ticker"].map(lambda t: m.get(t, t) if isinstance(t, str) else t)
    return out.drop_duplicates(subset=["snapshot_utc", "ticker"]).reset_index(drop=True)


def ticker_names(link_pairs: pd.DataFrame) -> pd.DataFrame:
    """Most-used Wikipedia article title per ticker (the company's name), plus all titles."""
    rows = []
    for tk, g in link_pairs.groupby("ticker"):
        g = g.sort_values("revisions", ascending=False)
        rows.append({"ticker": tk, "name": g["title"].iloc[0], "all_names": " | ".join(g["title"])})
    return pd.DataFrame(rows, columns=["ticker", "name", "all_names"])
