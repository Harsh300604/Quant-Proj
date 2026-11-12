"""Compact memo summaries for the committee (brief section 6): about 400 tokens per selected
company and one line for each of the rest. Built by Python from the memo fields (no LLM call),
so the committee never receives all the full memos.
"""
from __future__ import annotations

FIELD_CHARS = 360          # about 90 tokens per text field
ONE_LINER_CHARS = 110


def _cut(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 3].rsplit(" ", 1)[0] + "..."


def summary(memo, name: str, sector: str, bench_weight: float) -> str:
    head = f"### {memo.company_id}: {name} ({sector}); benchmark weight {bench_weight:.2%}"
    if not memo.ok:
        return f"{head}\nNo valid research memo this month ({memo.error}). Treat as no information."
    lines = [head, f"Junior analyst's outlook: {memo.outlook_3m}, conviction {memo.conviction}",
             f"Business: {_cut(memo.business_summary, FIELD_CHARS)}",
             f"Price and technicals: {_cut(memo.price_and_technicals, FIELD_CHARS)}",
             f"Fundamentals: {_cut(memo.fundamentals, FIELD_CHARS)}",
             f"News: {_cut(memo.news, FIELD_CHARS)}"]
    if memo.positives:
        lines.append("Positives: " + "; ".join(_cut(p, 120) for p in memo.positives[:4]))
    if memo.risks:
        lines.append("Risks: " + "; ".join(_cut(r, 120) for r in memo.risks[:4]))
    if memo.data_gaps:
        lines.append("Data gaps: " + "; ".join(_cut(g, 80) for g in memo.data_gaps[:3]))
    return "\n".join(lines)


def one_liner(memo, sector: str, bench_weight: float) -> str:
    if not memo.ok:
        return f"- {memo.company_id} ({sector}, {bench_weight:.2%}): no valid memo"
    gist = memo.positives[0] if memo.outlook_3m in ("positive", "slightly_positive") and memo.positives else \
        memo.risks[0] if memo.outlook_3m in ("negative", "slightly_negative") and memo.risks else memo.business_summary
    return (f"- {memo.company_id} ({sector}, {bench_weight:.2%}): {memo.outlook_3m}/{memo.conviction}; "
            f"{_cut(gist, ONE_LINER_CHARS)}")
