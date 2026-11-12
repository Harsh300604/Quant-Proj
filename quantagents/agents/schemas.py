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


class StockAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: str = Field(description="Ticker exactly as listed in the briefing.")
    view: Outlook = Field(description="Expected 3-month return relative to the benchmark.")
    conviction: Conviction
    reason: str = Field(description="One sentence, quoting figures from the briefing.")


class EmilyReport(BaseModel):
    """Market news & fundamentals analyst."""
    model_config = ConfigDict(extra="forbid")
    market_summary: str = Field(description="2-4 sentences on the news and fundamentals picture across the companies.")
    assessments: list[StockAssessment] = Field(description="One entry per company, in the order listed.")


class BobReport(BaseModel):
    """Quantitative & simulated-trading analyst."""
    model_config = ConfigDict(extra="forbid")
    simulated_trading_takeaway: str = Field(
        description="2-4 sentences: which simulated rules worked recently and what that suggests now.")
    assessments: list[StockAssessment] = Field(description="One entry per company, in the order listed.")


class StockRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: str
    risk: RiskLevel
    note: str = Field(description="One sentence, quoting figures from the briefing.")


class DaveReport(BaseModel):
    """Risk control analyst."""
    model_config = ConfigDict(extra="forbid")
    portfolio_risk_summary: str = Field(description="2-4 sentences on the current portfolio's risk numbers.")
    concerns: list[str] = Field(description="0-5 specific concerns (concentration, sectors, volatility, liquidity, "
                                            "disagreement between Emily and Bob).")
    stocks: list[StockRisk] = Field(description="One entry per company, in the order listed.")


class Tilt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: str
    multiplier: Multiplier = Field(description="Target weight as a multiple of the benchmark weight.")
    reason: str = Field(description="One sentence.")


class BaselineTilts(BaseModel):
    """Otto's decision (baseline variant): a multiplier of benchmark weight per company."""
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(description="3-5 sentences explaining the overall decision.")
    tilts: list[Tilt] = Field(description="One entry per company, in the order listed.")


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
