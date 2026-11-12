"""Selection: at most max_views names and max_per_sector per sector; deterministic; all names when
the universe is small and there is no per-sector cap (proto20, D42)."""
import pandas as pd

from quantagents.agents.schemas import ResearchMemo
from quantagents.agents.selection import select, signal_strength
from tests.llm_fakes import GOOD_MEMO


def memo(c, outlook="neutral", conviction="low", ok=True):
    m = ResearchMemo(**{**GOOD_MEMO, "outlook_3m": outlook, "conviction": conviction}, company_id=c, as_of="d",
                     model="m", prompt_version="p")
    return m if ok else ResearchMemo.no_view(c, "d", "m", "p", "broken")


def universe(n, sectors=("IT", "HC", "CS", "CD")):
    ids = [f"C{i:03d}" for i in range(n)]
    bench = pd.Series(range(n, 0, -1), index=ids, dtype=float)
    return ids, bench / bench.sum(), pd.Series([sectors[i % len(sectors)] for i in range(n)], index=ids)


def test_small_universe_without_sector_cap_selects_everyone():
    ids, bench, sectors = universe(20)
    memos = {c: memo(c) for c in ids}
    sel, rest = select(memos, bench, sectors, 20, None)
    assert sel == list(bench.sort_values(ascending=False).index) and rest == []


def test_caps_on_count_and_sector():
    ids, bench, sectors = universe(100)
    memos = {c: memo(c, "positive" if i % 2 else "slightly_negative", ["low", "medium", "high"][i % 3])
             for i, c in enumerate(ids)}
    sel, rest = select(memos, bench, sectors, 20, 3)
    assert len(sel) <= 20 and len(sel) + len(rest) == 100
    assert sectors[sel].value_counts().max() <= 3
    assert all(signal_strength(memos[c]) >= max(signal_strength(memos[r]) for r in rest if sectors[r] == sectors[c])
               for c in sel if sectors[rest].eq(sectors[c]).any())


def test_selection_is_deterministic_with_stable_tie_breaks():
    ids, bench, sectors = universe(40)
    memos = {c: memo(c, "positive", "high") for c in ids}         # every signal ties
    a = select(memos, bench, sectors, 10, None)
    b = select(dict(reversed(list(memos.items()))), bench, sectors, 10, None)
    assert a == b and a[0] == ids[:10]                          # ties -> larger benchmark weight first


def test_failed_memo_has_no_signal():
    assert signal_strength(memo("X", "positive", "high", ok=False)) == 0
    assert signal_strength(memo("X", "negative", "high")) == 6
