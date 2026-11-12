"""Pydantic schemas for every LLM output (brief section 14: every output is schema-validated).

The ``*Body`` models are what the LLM fills in (sent as the structured-output schema). The
wrapper models add fields Python sets itself (company, date, model, whether the call worked).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Outlook = Literal["negative", "slightly_negative", "neutral", "slightly_positive", "positive"]
Conviction = Literal["low", "medium", "high"]


class MemoBody(BaseModel):
    """One-page research memo on one company, written by a junior analyst (Haiku)."""
    model_config = ConfigDict(extra="forbid")

    business_summary: str = Field(description="What the company does, in 1-2 sentences.")
    price_and_technicals: str = Field(description="Recent price trend and indicators, quoting the given numbers.")
    fundamentals: str = Field(description="Latest reported results and balance sheet, quoting the given numbers.")
    news: str = Field(description="What the recent news says; 'no recent news' if there is none.")
    positives: list[str] = Field(description="1-4 short points in favour of the stock over the next 3 months.")
    risks: list[str] = Field(description="1-4 short points against the stock over the next 3 months.")
    outlook_3m: Outlook = Field(description="Expected 3-month return relative to the NASDAQ-100 index.")
    conviction: Conviction = Field(description="How strong the evidence for that outlook is.")
    data_gaps: list[str] = Field(description="Important information that is missing from the input (may be empty).")


RiskLevel = Literal["low", "medium", "high"]
# Otto's tilt: a multiple of the benchmark weight, in steps of 0.25 (1.0 = benchmark weight = no view).
Multiplier = Literal[0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]


class CommitteeStock(BaseModel):
    """One company in a committee member's answer. Each role fills its own fields and sets the others to null."""
    model_config = ConfigDict(extra="forbid")
    company_id: str = Field(description="Ticker exactly as listed in the briefing.")
    view: Outlook | None = Field(description="Emily and Bob: expected 3-month return relative to the benchmark. "
                                             "Others: null.")
    conviction: Conviction | None = Field(description="Emily and Bob: strength of the evidence. Others: null.")
    risk: RiskLevel | None = Field(description="Dave: risk over the next 3 months. Others: null.")
    multiplier: Multiplier | None = Field(description="Otto: target weight as a multiple of the benchmark weight. "
                                                      "Others: null.")
    reason: str = Field(description="One short sentence (at most 25 words) quoting figures from the briefing.")


class CommitteeAnswer(BaseModel):
    """The one answer format of every committee meeting. A single schema keeps the prompt-cache
    prefix identical across the five calls (the output schema is part of the cached prompt)."""
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(description="2-5 sentences: Emily the news and fundamentals picture; Bob what the simulated "
                                     "trading shows; Dave the portfolio's risk; Otto the decision and its reasons.")
    concerns: list[str] = Field(description="Dave: 0-5 specific risk concerns. Others: an empty list.")
    stocks: list[CommitteeStock] = Field(description="One entry per company, in the order listed.")


# the fields each role must fill (checked in Python; a missing field counts as an invalid answer)
ROLE_FIELDS = {"emily": ("view", "conviction"), "bob": ("view", "conviction"), "dave": ("risk",),
               "otto_draft": ("multiplier",), "otto_final": ("multiplier",)}


def role_check(node: str):
    """A check for LLMClient.structured: '' if the role filled its fields for every company it listed."""
    fields = ROLE_FIELDS[node]

    def check(ans: CommitteeAnswer) -> str:
        bad = [s.company_id for s in ans.stocks if any(getattr(s, f) is None for f in fields)]
        return f"{node} left {'/'.join(fields)} empty for {', '.join(bad[:5])}" if bad else ""
    return check


class ResearchMemo(MemoBody):
    company_id: str
    as_of: str
    model: str
    prompt_version: str
    ok: bool = True                 # False = no valid answer; the fields hold the 'no view' default
    error: str = ""

    @classmethod
    def no_view(cls, company_id: str, as_of: str, model: str, prompt_version: str, error: str) -> "ResearchMemo":
        """Default when the LLM gave no valid answer: neutral outlook, low conviction (index weight)."""
        return cls(business_summary="", price_and_technicals="", fundamentals="", news="", positives=[], risks=[],
                   outlook_3m="neutral", conviction="low", data_gaps=["memo unavailable"],
                   company_id=company_id, as_of=as_of, model=model, prompt_version=prompt_version,
                   ok=False, error=error)
