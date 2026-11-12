"""Which companies the committee forms views on (brief section 6, "Coverage and the top 20").

Deterministic Python ranking of memo signals, not a momentum filter:
signal strength = |outlook| x conviction weight; ties go to the larger benchmark weight, then
to the company id. At most ``max_views`` names and at most ``max_per_sector`` per sector.
When the universe has no more than ``max_views`` companies and there is no per-sector cap
(proto20, D42), every company is selected and the "one-liners for the rest" list is empty.
"""
from __future__ import annotations

import pandas as pd

OUTLOOK_SCORE = {"negative": -2, "slightly_negative": -1, "neutral": 0, "slightly_positive": 1, "positive": 2}
CONVICTION_WEIGHT = {"low": 1, "medium": 2, "high": 3}


def signal_strength(memo) -> int:
    if not getattr(memo, "ok", True):
        return 0
    return abs(OUTLOOK_SCORE[memo.outlook_3m]) * CONVICTION_WEIGHT[memo.conviction]


def select(memos: dict, bench: pd.Series, sectors: pd.Series, max_views: int,
           max_per_sector: int | None) -> tuple[list[str], list[str]]:
    """(selected, rest), both ordered: selected by benchmark weight (largest first), rest likewise."""
    companies = list(bench.sort_values(ascending=False, kind="mergesort").index)
    by_weight = lambda ids: sorted(ids, key=lambda c: (-float(bench[c]), c))  # noqa: E731
    if len(companies) <= max_views and max_per_sector is None:
        return by_weight(companies), []
    ranked = sorted(companies, key=lambda c: (-signal_strength(memos[c]) if c in memos else 0, -float(bench[c]), c))
    chosen, per_sector = [], {}
    for c in ranked:
        s = sectors.get(c, "Unknown")
        if max_per_sector is not None and per_sector.get(s, 0) >= max_per_sector:
            continue
        chosen.append(c)
        per_sector[s] = per_sector.get(s, 0) + 1
        if len(chosen) == max_views:
            break
    return by_weight(chosen), by_weight([c for c in companies if c not in chosen])
