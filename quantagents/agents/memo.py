"""Research memo node: one company, one decision date, one Haiku call (brief section 6, step 1).

Python reads the company's data through the point-in-time gateway, computes every number
(returns, volatility, margins, P/E, growth), and writes a compact text block. The LLM only reads
that block and fills in the ``MemoBody`` schema. Nothing after ``as_of`` can reach the memo: the
gateway is frozen at ``as_of``.

    python -m quantagents.agents.memo --config configs\\pilot.yaml --as-of 2015-03-02
    python -m quantagents.agents.memo --config configs\\proto20.yaml --as-of 2021-01-04 --companies AAPL,PDD,TMUS
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from quantagents.agents.schemas import MemoBody, ResearchMemo
from quantagents.config import CONFIG_DIR, Config, load_config
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway

log = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_VERSION = "memo_v1"
NEWS_WINDOW_DAYS = 31
MAX_HEADLINES = 15
SUMMARY_CHARS = 200
INDICATORS = [("rsi14", "RSI(14)", "{:.0f}"), ("close_sma50", "price vs 50-day average", "{:+.1%}"),
              ("close_sma200", "price vs 200-day average", "{:+.1%}"), ("macd_hist_pct", "MACD histogram (% of price)", "{:+.2%}"),
              ("adx14", "ADX(14) trend strength", "{:.0f}"), ("rvol20", "volume vs 20-day average", "{:.2f}x"),
              ("bb_pos", "position in Bollinger band (0 = lower, 1 = upper)", "{:.2f}")]


def system_prompt() -> str:
    return (PROMPT_DIR / f"{PROMPT_VERSION}.txt").read_text(encoding="utf-8").strip()


# ----------------------------------------------------------------------------- formatting helpers
def money(v, currency: str = "USD") -> str:
    """$1.23B for US dollars; 'CNY 30.14B' for other currencies (foreign filers report in their own)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    sign, a = ("-" if v < 0 else ""), abs(v)
    pre = "$" if currency == "USD" else f"{currency} "
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if a >= div:
            return f"{sign}{pre}{a / div:.2f}{unit}"
    return f"{sign}{pre}{a:,.2f}"


def currency_of(unit: str | None) -> str:
    return str(unit or "USD").split("/")[0]


def pct(v, signed: bool = True) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    return f"{v:+.1%}" if signed else f"{v:.1%}"


def _total_return(r: pd.Series, n: int) -> float:
    return float((1 + r.iloc[-n:]).prod() - 1) if len(r) >= n else float("nan")


# ----------------------------------------------------------------------------- the data block
def memo_input(gw: Gateway, company_id: str, as_of) -> str:
    """Everything the memo LLM sees, as text. All figures computed here, from data known at ``as_of``."""
    t = cal.require_utc(as_of)
    day = t.tz_convert(cal.ET).date()
    lines = [f"Decision date: {day} (US market close). Everything below was known at that moment.", ""]

    u = gw.get_universe(t)
    row = u[u["company_id"] == company_id]
    name = row["name"].iloc[0] if len(row) else company_id
    sector = row["sector"].iloc[0] if len(row) else "Unknown"
    is_us = row["is_us"].iloc[0] if len(row) else None
    where = "unknown" if is_us is None or pd.isna(is_us) else ("US" if bool(is_us) else "outside the US")
    lines += [f"Company: {name} (ticker {company_id})", f"Sector: {sector}; headquarters: {where}"]
    w = gw.get_index_weights(t)
    wr = w[w["company_id"] == company_id]
    mcap = float(wr["mcap"].iloc[0]) if len(wr) else float("nan")
    lines.append(f"Market value: {money(mcap)}; weight in the NASDAQ-100 (derived): "
                 f"{pct(float(wr['weight'].iloc[0]), signed=False) if len(wr) else 'n/a'}")

    # prices
    p = gw.get_prices([company_id], t, lookback_days=400)
    lines += ["", "PRICE (total returns include dividends)"]
    if len(p):
        r = p["ret"].fillna(0.0)
        close = p["close"].astype(float)
        last = p.iloc[-1]
        vol = float(r.iloc[-63:].std() * np.sqrt(252)) if len(r) >= 63 else float("nan")
        hi = float(close.iloc[-252:].max())
        lines += [f"Last close: {pd.Timestamp(last['date']).date()}, ${float(last['raw_close']):,.2f} per share",
                  f"Return: 1 month {pct(_total_return(r, 21))}, 3 months {pct(_total_return(r, 63))}, "
                  f"6 months {pct(_total_return(r, 126))}, 12 months {pct(_total_return(r, 252))}",
                  f"Volatility (last 3 months, annualised): {pct(vol, signed=False)}; "
                  f"distance from 52-week high: {pct(float(close.iloc[-1]) / hi - 1)}"]
    else:
        lines.append("No price data.")
    ind = gw.get_indicators([company_id], t)
    if len(ind):
        i0 = ind.iloc[0]
        parts = [f"{label} {fmt.format(float(i0[col]))}" for col, label, fmt in INDICATORS
                 if col in ind.columns and pd.notna(i0[col])]
        lines.append("Indicators: " + ("; ".join(parts) if parts else "not available yet"))

    # fundamentals
    lines += ["", "LATEST FINANCIAL FILINGS (SEC; each figure as of the filing date)"]
    f = gw.get_fundamentals([company_id], t)
    lines += fundamentals_lines(f, mcap)

    # news
    n = gw.get_news([company_id], t, window_days=NEWS_WINDOW_DAYS)
    lines += ["", f"NEWS (last {NEWS_WINDOW_DAYS} days: {len(n)} articles; newest {min(len(n), MAX_HEADLINES)} shown)"]
    if len(n):
        for a in n.sort_values("created_utc", ascending=False).head(MAX_HEADLINES).itertuples():
            s = html.unescape(a.summary or "").strip().replace("\n", " ")
            head = html.unescape(a.headline or "")
            s = s[:SUMMARY_CHARS] + ("..." if len(s) > SUMMARY_CHARS else "")
            lines.append(f"- {pd.Timestamp(a.created_utc).tz_convert(cal.ET).date()}: {head}" + (f" | {s}" if s else ""))
    else:
        lines.append("No news in this period.")
    return "\n".join(lines)


def fundamentals_lines(f: pd.DataFrame, mcap: float) -> list[str]:
    if f.empty:
        return ["No financial filings known at this date."]
    out = []

    def get(metric, ptype):
        m = f[(f["metric"] == metric) & (f["period_type"] == ptype)]
        return m.iloc[0] if len(m) else None

    for ptype, label in (("quarter", "Latest quarter"), ("annual", "Latest full year")):
        rev = get("revenue", ptype)
        if rev is None:
            continue
        vals = {k: get(k, ptype) for k in ("gross_profit", "operating_income", "net_income", "eps_diluted",
                                           "op_cash_flow", "capex")}
        cur = currency_of(rev["unit"])
        same = {k: v for k, v in vals.items() if v is not None and v["period_end"] == rev["period_end"]
                and currency_of(v["unit"]) == cur}
        txt = f"{label} (period ending {pd.Timestamp(rev['period_end']).date()}, {rev['form']} filed " \
              f"{pd.Timestamp(rev['available_utc']).tz_convert(cal.ET).date()}): revenue {money(rev['value'], cur)}"
        for k, lab in (("gross_profit", "gross margin"), ("operating_income", "operating margin"),
                       ("net_income", "net margin")):
            if k in same and rev["value"]:
                txt += f"; {lab} {pct(same[k]['value'] / rev['value'], signed=False)}"
        if "net_income" in same:
            txt += f"; net income {money(same['net_income']['value'], cur)}"
        if "eps_diluted" in same:
            txt += f"; diluted EPS {same['eps_diluted']['value']:.2f} {cur}"
        if "op_cash_flow" in same and "capex" in same:
            txt += f"; free cash flow {money(same['op_cash_flow']['value'] - same['capex']['value'], cur)}"
        if ptype == "annual" and "net_income" in same and same["net_income"]["value"] > 0 and not math.isnan(mcap):
            if cur == "USD":
                txt += f"; price/earnings {mcap / same['net_income']['value']:.1f}"
            else:
                txt += f"; (figures in {cur}; price/earnings not computed, no exchange rate in the data)"
        out.append(txt)
    bs = {k: get(k, "instant") for k in ("cash", "long_term_debt", "total_liabilities", "equity", "total_assets")}
    known = {k: v for k, v in bs.items() if v is not None}
    if known:
        end = max(pd.Timestamp(v["period_end"]) for v in known.values())
        parts = [f"{lab} {money(known[k]['value'], currency_of(known[k]['unit']))}" for k, lab in (("cash", "cash"), ("long_term_debt", "long-term debt"),
                 ("total_liabilities", "total liabilities"), ("equity", "shareholders' equity")) if k in known]
        out.append(f"Balance sheet (latest, {end.date()}): " + "; ".join(parts))
    return out or ["No income-statement figures known at this date."]


# ----------------------------------------------------------------------------- the node
def write_memo(client, cfg: Config, gw: Gateway, company_id: str, as_of) -> tuple[ResearchMemo, str]:
    t = cal.require_utc(as_of)
    text = memo_input(gw, company_id, t)
    return memo_from_text(client, cfg, company_id, str(t.tz_convert(cal.ET).date()), text), text


def memo_from_text(client, cfg: Config, company_id: str, day: str, text: str) -> ResearchMemo:
    """The LLM part only (no gateway access), so the agent graph can run memos in parallel threads."""
    model = cfg.models.active.memo
    res = client.structured(node="memo", model=model, system=system_prompt(), user=text, schema=MemoBody,
                            max_tokens=cfg.models.memo.max_tokens, effort=cfg.models.memo.effort, thinking_off=True)
    if res.ok:
        return ResearchMemo(**res.parsed.model_dump(), company_id=company_id, as_of=day, model=model,
                            prompt_version=PROMPT_VERSION)
    return ResearchMemo.no_view(company_id, day, model, PROMPT_VERSION, res.error)


def memo_markdown(m: ResearchMemo) -> str:
    if not m.ok:
        return f"# {m.company_id}, {m.as_of}\n\n**No valid memo** ({m.error}). Default: neutral outlook, low conviction.\n"
    bullet = lambda xs: "\n".join(f"- {x}" for x in xs) or "- (none)"  # noqa: E731
    return (f"# {m.company_id}, {m.as_of}\n\n**Outlook (3 months vs NASDAQ-100):** {m.outlook_3m}, "
            f"conviction {m.conviction}\n\n**Business:** {m.business_summary}\n\n**Price and technicals:** "
            f"{m.price_and_technicals}\n\n**Fundamentals:** {m.fundamentals}\n\n**News:** {m.news}\n\n"
            f"**Positives**\n{bullet(m.positives)}\n\n**Risks**\n{bullet(m.risks)}\n\n**Data gaps**\n"
            f"{bullet(m.data_gaps)}\n\n_{m.model}, prompt {m.prompt_version}_\n")


def main(argv: list[str] | None = None) -> int:
    from quantagents.data.universe import as_of_close, resolve_universe
    from quantagents.llm.client import LLMClient, LLMError
    from quantagents.llm.ledger import BudgetExceeded
    from quantagents.logs import setup_logging
    from quantagents.paths import Paths
    ap = argparse.ArgumentParser(description="Write research memos for one decision date")
    ap.add_argument("--config", default=str(CONFIG_DIR / "pilot.yaml"))
    ap.add_argument("--as-of", required=True, help="decision date (YYYY-MM-DD); its market close is used")
    ap.add_argument("--companies", help="comma-separated company ids (default: the config's universe)")
    ap.add_argument("--run-id", default="memo_check")
    ap.add_argument("--dry-run", action="store_true", help="print the first memo input and stop (no API call)")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    paths = Paths.from_config(cfg)
    setup_logging(paths.logs, "memo")
    t = as_of_close(args.as_of)
    full = Gateway(paths.duckdb_file)
    try:
        ids = [c.strip().upper() for c in args.companies.split(",")] if args.companies else \
            resolve_universe(cfg, full).at(full, t)
    finally:
        full.close()
    gw = Gateway(paths.duckdb_file, freeze_at=t)     # nothing after as_of can be read
    out = paths.runs / args.run_id / "memos" / str(t.tz_convert(cal.ET).date())
    out.mkdir(parents=True, exist_ok=True)
    try:
        if args.dry_run:
            print(memo_input(gw, ids[0], t))
            return 0
        client = LLMClient(cfg, args.run_id)
        print(f"Memos for {len(ids)} companies at {t} ({cfg.models.active.memo}, effort {cfg.models.memo.effort}): "
              f"{', '.join(ids)}")
        failed = 0
        for cid in ids:
            memo, text = write_memo(client, cfg, gw, cid, t)
            (out / f"{cid}.input.txt").write_text(text, encoding="utf-8")
            (out / f"{cid}.json").write_text(json.dumps(memo.model_dump(), indent=2), encoding="utf-8")
            (out / f"{cid}.md").write_text(memo_markdown(memo), encoding="utf-8")
            failed += not memo.ok
            print(f"  {cid}: {memo.outlook_3m}, conviction {memo.conviction}" + ("" if memo.ok else f"  (NO VIEW: {memo.error})"))
        print(f"memos: {len(ids)}, failed: {failed} | {client.summary()}")
        print(f"Files: {out}")
    except (BudgetExceeded, LLMError) as e:
        print(str(e))
        return 1
    finally:
        gw.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
