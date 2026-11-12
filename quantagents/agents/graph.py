"""The agent graph (brief section 6): a pure function from one decision date to target weights.

    quant_agents(inputs, client, cfg, gateway) -> state with "weights", "multipliers" and the full record

LangGraph pipeline, one run per monthly rebalance; it keeps no state between rebalances (the
engine passes in last month's report and the history of past views):

  [0] coverage       (Python)  memo inputs for every company, read through the frozen gateway
  [1] memo  x N      (Haiku)   Send() fan-out, one research memo per company, run in parallel
  [2] briefing       (Python)  selection, memo summaries, price/risk table, simulated trading (D32),
                               risk stats (D33), track record (D34): the shared, cached prompt block
  [3] Market Analysis meeting: emily -> bob -> dave          (committee model)
  [4] Strategy meeting:        otto_draft                    (committee model)
  [5] draft_check    (Python)  what the constraints change, turnover, cost, risk of the draft
  [6] Decision meeting:        otto_final                    (committee model)
  [7] optimizer      (Python)  multipliers -> weights inside 0x-2x and the sector bands

LLMs never compute numbers: every figure they see is computed here. Every LLM output is
validated against its pydantic schema; a failed meeting is recorded and the graph falls back:
no final decision -> the draft; no draft -> no view (benchmark weights).
"""
from __future__ import annotations

import json
import operator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, TypedDict

import pandas as pd

from quantagents.agents import summaries
from quantagents.agents.memo import PROMPT_VERSION as MEMO_PROMPT, memo_from_text, memo_input, memo_markdown
from quantagents.agents.schemas import ResearchMemo, committee_schema, role_check
from quantagents.agents.selection import select
from quantagents.agents.sim_trading import format_pool, simulate_pool
from quantagents.agents.track_record import format_track_record, outcomes
from quantagents.data import calendar as cal
from quantagents.portfolio.baseline_opt import weights_from_multipliers
from quantagents.portfolio.constraints import ConstraintSet
from quantagents.portfolio.risk_stats import format_portfolio_stats, format_stock_table, portfolio_stats, stock_table

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
COMMITTEE_PROMPT = "committee_v1"
PERSONAS = {"emily": "emily_v1", "bob": "bob_v1", "dave": "dave_v1", "otto_draft": "otto_baseline_v1",
            "otto_final": "otto_decision_v1"}
ENHANCED_PERSONAS = {"otto_draft": "otto_enhanced_v1", "otto_final": "otto_enhanced_decision_v1"}
TITLES = {"emily": "Market analysis meeting: Emily (market news & fundamentals)",
          "bob": "Market analysis meeting: Bob (quantitative & simulated trading)",
          "dave": "Market analysis meeting: Dave (risk control)",
          "otto_draft": "Strategy meeting: Otto drafts the portfolio",
          "otto_final": "Decision meeting: Otto decides"}


def prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8").strip()


def benchmark_label(cfg) -> str:
    return ("the same companies at market-cap weight (custom cap-weighted index)"
            if cfg.benchmark.mode == "custom_cap_index"
            else "NASDAQ-100 derived cap weights of the companies in this run, scaled to 100%")


@dataclass
class GraphInputs:
    """Everything one rebalance's decision may depend on (all known at ``as_of``)."""
    as_of: pd.Timestamp
    companies: list[str]                      # benchmark order
    bench: pd.Series                          # benchmark weights (sum 1)
    sectors: pd.Series
    names: dict[str, str]
    constraints: ConstraintSet
    holdings: dict[str, float]                # current weights before trading (empty = all cash)
    prior_report: dict | None = None
    history: list[dict] = field(default_factory=list)
    benchmark_label: str = "the benchmark"

    @property
    def day(self) -> str:
        return str(cal.require_utc(self.as_of).tz_convert(cal.ET).date())


class AgentState(TypedDict, total=False):
    memo_inputs: dict
    memo_id: str                              # set only inside one Send() branch
    memos: Annotated[list, operator.add]
    selected: list
    rest: list
    briefing: str
    sections: dict
    reports: Annotated[dict, lambda a, b: {**a, **b}]
    meetings: Annotated[list, operator.add]
    check_text: str
    multipliers: dict
    labels: dict
    bl: dict
    decision_source: str
    weights: dict


# ----------------------------------------------------------------------------- rendering helpers
def render_report(node: str, parsed) -> str:
    if parsed is None:
        return "(no valid answer this month)"
    d = parsed if isinstance(parsed, dict) else parsed.model_dump()
    if node in ("emily", "bob"):
        return d["summary"] + "\n" + "\n".join(f"- {a['company_id']}: {a['view']} ({a['conviction']}): {a['reason']}"
                                               for a in d["stocks"])
    if node == "dave":
        return (d["summary"] + "\nConcerns:\n" + ("\n".join(f"- {c}" for c in d["concerns"]) or "- none")
                + "\nRisk by company:\n" + "\n".join(f"- {s['company_id']}: {s['risk']}: {s['reason']}" for s in d["stocks"]))
    def otto(t):
        if t.get("rating") is not None:
            return f"- {t['company_id']}: {t['rating']} (confidence {t['confidence']:.1f}): {t['reason']}"
        return f"- {t['company_id']}: x{t['multiplier']:.2f}: {t['reason']}"
    return d["summary"] + "\n" + "\n".join(otto(t) for t in d["stocks"])


def by_company(items: list[dict], companies: list[str]) -> tuple[dict, list[str], list[str]]:
    """{company: item} for listed companies (first entry wins); (missing, unknown) ids."""
    out, unknown = {}, []
    for it in items:
        c = str(it.get("company_id", "")).strip().upper()
        if c in companies and c not in out:
            out[c] = it
        elif c not in companies:
            unknown.append(c)
    return out, [c for c in companies if c not in out], unknown


# ----------------------------------------------------------------------------- briefing (Python)
def build_briefing(inp: GraphInputs, gw, cfg, memos: dict[str, ResearchMemo], selected: list[str],
                   rest: list[str]) -> tuple[str, dict]:
    t = cal.require_utc(inp.as_of)
    bench = inp.bench
    cur = pd.Series(inp.holdings, dtype=float).reindex(inp.companies).fillna(0.0)
    prior = (inp.prior_report or {}).get("views") or {}
    sec = {}

    rows = ["company | name | sector | benchmark weight | current weight | current multiplier | last month's decision"]
    for c in inp.companies:
        last = f"x{prior[c]:.2f}" if c in prior else "-"
        rows.append(f"{c} | {inp.names.get(c, c)} | {inp.sectors[c]} | {bench[c]:.2%} | {cur[c]:.2%} | "
                    f"x{cur[c] / bench[c]:.2f} | {last}")
    if not inp.holdings:
        rows.append("(The portfolio is all cash: this is the run's first decision.)")
    band = cfg.constraints.sector_band_pp / 100
    sw = bench.groupby(inp.sectors.reindex(bench.index)).sum().sort_values(ascending=False)
    rows += ["", f"Sector bands (benchmark sector weight, allowed range +-{cfg.constraints.sector_band_pp:g} pp):"]
    rows += [f"- {s}: {v:.2%} (allowed {max(v - band, 0):.2%} to {min(v + band, 1):.2%})" for s, v in sw.items()]
    sec["portfolio"] = "\n".join(rows)

    names = lambda c: inp.names.get(c, c)  # noqa: E731
    sec["memos"] = "\n\n".join(summaries.summary(memos[c], names(c), inp.sectors[c], float(bench[c])) for c in selected)
    sec["others"] = "\n".join(summaries.one_liner(memos[c], inp.sectors[c], float(bench[c])) for c in rest) \
        or "None: every company is covered by a memo summary above."

    table, year = stock_table(gw, inp.companies, t, bench)
    sec["prices"] = format_stock_table(table, bench)
    pool = simulate_pool(gw, inp.companies, t, months=cfg.agents.sim_trading_months)
    sec["simulated_trading"] = format_pool(pool)
    rs = cfg.risk_score
    b_stats = portfolio_stats(bench, bench, inp.sectors, table, year, cfg.constraints.sector_band_pp, rs)
    c_stats = portfolio_stats(cur, bench, inp.sectors, table, year, cfg.constraints.sector_band_pp, rs)
    sec["risk"] = "\n".join([format_portfolio_stats("Benchmark", b_stats),
                             format_portfolio_stats("Current portfolio", c_stats),
                             f"Risk score R = {rs.beta:g} x beta + {rs.illiquidity:g} x (1 / liquidity ratio) + "
                             f"{rs.sector:g} x (largest active sector position / {cfg.constraints.sector_band_pp:g} pp) + "
                             f"{rs.volatility:g} x (volatility / benchmark volatility)."])
    tr = outcomes(gw, inp.history, t, cfg.views.horizon_months)
    first = inp.history[0]["rebalance"] if inp.history else inp.day
    sec["track_record"] = format_track_record(tr, t, cfg.views.horizon_months, cfg.agents.track_record_rebalances,
                                              first_rebalance=first)
    pr = inp.prior_report or {}
    sec["last_decision"] = (f"Otto's summary last month ({pr.get('rebalance', '?')}): {pr['summary']}"
                            if pr.get("summary") else "This is the first meeting of this run.")
    stats = {"benchmark": b_stats, "current": c_stats, "table": table, "year": year, "track_record_rows": len(tr)}

    text = "\n\n".join([
        prompt(COMMITTEE_PROMPT),
        "=" * 70 + f"\nBRIEFING FOR THE MEETING OF {inp.day} (market close)\nBenchmark: {inp.benchmark_label}\n"
        f"Company list (in order): {', '.join(selected)}",
        "1. PORTFOLIO AND BENCHMARK\n" + sec["portfolio"],
        "2. RESEARCH MEMO SUMMARIES (junior analysts, written today)\n" + sec["memos"],
        "3. OTHER COMPANIES IN THE UNIVERSE (no committee view; they stay at benchmark weight)\n" + sec["others"],
        "4. PRICE AND RISK TABLE (computed by Python from daily total returns)\n" + sec["prices"],
        "5. SIMULATED TRADING (computed by Python)\n" + sec["simulated_trading"],
        "6. RISK (computed by Python)\n" + sec["risk"],
        "7. TRACK RECORD OF THIS COMMITTEE'S OWN VIEWS\n" + sec["track_record"],
        "8. LAST MONTH'S DECISION\n" + sec["last_decision"],
    ])
    return text, {"sections": sec, "stats": stats}


# ----------------------------------------------------------------------------- draft check (Python)
RATING_EQUIV = {"strong_sell": 0.5, "sell": 0.75, "hold": 1.0, "buy": 1.25, "strong_buy": 1.5}


def weights_for(inp: GraphInputs, cfg, decision: dict, variant: str, sigma) -> tuple[pd.Series, dict]:
    """Python turns Otto's decision into weights: multipliers -> projection (baseline);
    ratings + confidence -> Black-Litterman -> the same constraints (enhanced)."""
    if variant == "enhanced":
        from quantagents.portfolio.black_litterman import bl_weights
        return bl_weights(inp.constraints, sigma, decision, dict(cfg.views.rating_to_excess_return),
                          cfg.black_litterman.delta, cfg.black_litterman.tau)
    return weights_from_multipliers(inp.constraints, pd.Series(decision, dtype=float)), {}


def proposal_lines(decision: dict, w: pd.Series, bench: pd.Series, variant: str) -> list[str]:
    if variant == "enhanced":
        rated = [(c, r, conf) for c, (r, conf) in decision.items() if conf > 0 and r != "hold"]
        lines = ["Black-Litterman and the portfolio rules turn the draft views into these weights "
                 "(view -> weight as a multiple of benchmark weight):"]
        lines += [f"- {c}: {r} (confidence {conf:.1f}) -> x{float(w[c] / bench[c]):.2f}" for c, r, conf in rated]
        moved = [c for c in w.index if abs(float(w[c] / bench[c]) - 1) > 0.05 and c not in {x[0] for x in rated}]
        if moved:
            lines.append("Companies without a buy/sell view that still moved (through correlations, the sector bands "
                         "or the 100% total): " + ", ".join(f"{c} x{float(w[c] / bench[c]):.2f}" for c in moved))
        return lines if rated else ["The draft has no buy or sell views: the weights stay at the benchmark."]
    changed = [(c, decision.get(c, 1.0), float(w[c] / bench[c])) for c in w.index
               if abs(decision.get(c, 1.0) - float(w[c] / bench[c])) > 0.01]
    if not changed:
        return ["The portfolio rules accept every tilt as proposed."]
    return ["The portfolio rules change these tilts (proposed -> after the rules):"] + \
        [f"- {c}: x{p:.2f} -> x{e:.2f}" for c, p, e in changed]


def overweight_intent(decision: dict, variant: str) -> set[str]:
    if variant == "enhanced":
        return {c for c, (r, conf) in decision.items() if r in ("buy", "strong_buy") and conf > 0}
    return {c for c, m in decision.items() if m > 1.0}


def check_draft(inp: GraphInputs, cfg, decision: dict, stats: dict, dave: dict | None, variant: str = "baseline",
                sigma=None) -> str:
    w, _ = weights_for(inp, cfg, decision, variant, sigma)
    bench = inp.bench
    allc = sorted(set(w.index) | set(inp.holdings))
    cur = pd.Series(inp.holdings, dtype=float).reindex(allc).fillna(0.0)
    trade = lambda target: float((target.reindex(allc).fillna(0.0) - cur).abs().sum())  # noqa: E731
    turnover = trade(w)          # same definition as the engine: sum of |trades| / portfolio value
    lines = proposal_lines(decision, w, bench, variant)
    sw = pd.DataFrame({"w": w, "b": bench, "s": inp.sectors.reindex(w.index)}).groupby("s")[["w", "b"]].sum()
    lines.append("Sector weights after the rules (portfolio vs benchmark): " +
                 "; ".join(f"{s} {r.w:.2%} vs {r.b:.2%}" for s, r in sw.sort_values("b", ascending=False).iterrows()))
    lines.append(f"Estimated trading to reach this portfolio: {turnover:.1%} of the portfolio, costing about "
                 f"{turnover * cfg.cost_bps / 1e4:.3%} of its value."
                 + (" (First decision: the portfolio starts from cash, so 100% must be bought whatever you decide.)"
                    if not inp.holdings else ""))
    if inp.holdings:
        lines.append(f"For comparison: keeping the current weights would trade 0%; returning exactly to the "
                     f"benchmark would trade {trade(bench):.1%}.")
    d_stats = portfolio_stats(w, bench, inp.sectors, stats["table"], stats["year"], cfg.constraints.sector_band_pp,
                              cfg.risk_score)
    lines += [format_portfolio_stats("Draft portfolio", d_stats), format_portfolio_stats("Benchmark", stats["benchmark"]),
              format_portfolio_stats("Current portfolio", stats["current"])]
    if dave:
        risky = {s["company_id"] for s in dave.get("stocks", []) if s.get("risk") == "high"}
        over = [c for c in w.index if c in risky and c in overweight_intent(decision, variant)]
        if over:
            lines.append("Dave rated these high risk, and the draft overweights them: " + ", ".join(over))
    return "\n".join(lines)


# ----------------------------------------------------------------------------- the graph
def build_graph(inp: GraphInputs, gw, cfg, client, variant: str = "baseline", anon=None,
                inputs_dir: Path | None = None):
    """``anon``: an Anonymizer for the names-hidden run (everything sent to an LLM is scrubbed and
    the answers mapped back). ``inputs_dir``: where to save every LLM input (audit, leak scan)."""
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Send

    from quantagents.portfolio.black_litterman import monthly_covariance

    committee_model = cfg.models.active.committee
    thinking_off = cfg.models.committee.thinking == "between_tools"
    schema = committee_schema(variant)
    personas = {**PERSONAS, **(ENHANCED_PERSONAS if variant == "enhanced" else {})}
    ctx: dict[str, Any] = {}
    shown = (lambda s: anon.scrub(s)) if anon is not None else (lambda s: s)  # noqa: E731
    real = (lambda c: anon.real_id(c)) if anon is not None else (lambda c: c)  # noqa: E731

    def save(name: str, text: str) -> None:
        if inputs_dir is not None:
            inputs_dir.mkdir(parents=True, exist_ok=True)
            (inputs_dir / f"{name}.txt").write_text(text, encoding="utf-8")

    def coverage(state: AgentState) -> dict:
        return {"memo_inputs": {c: shown(memo_input(gw, c, inp.as_of)) for c in inp.companies}}

    def fan_out(state: AgentState):
        return [Send("memo", {"memo_id": c, "memo_inputs": {c: state["memo_inputs"][c]}}) for c in inp.companies]

    def memo(state: AgentState) -> dict:
        c = state["memo_id"]
        save(f"memo_{c}", state["memo_inputs"][c])
        m = memo_from_text(client, cfg, c, inp.day, state["memo_inputs"][c])
        return {"memos": [m.model_dump()]}

    def briefing(state: AgentState) -> dict:
        memos = {d["company_id"]: ResearchMemo(**d) for d in state["memos"]}
        selected, rest = select(memos, inp.bench, inp.sectors, cfg.selection.max_views, cfg.selection.max_per_sector)
        text, extra = build_briefing(inp, gw, cfg, memos, selected, rest)
        ctx["stats"] = extra["stats"]
        if variant == "enhanced":
            ctx["sigma"] = monthly_covariance(extra["stats"]["year"], list(inp.constraints.companies))
        save("committee_briefing", shown(text))
        return {"selected": selected, "rest": rest, "briefing": text, "sections": extra["sections"]}

    def meeting(node: str, notes_from: tuple[str, ...]):
        def run(state: AgentState) -> dict:
            reports = state.get("reports", {})
            parts = [prompt(personas[node])]
            for prev in notes_from:
                parts.append(f"--- {TITLES[prev]} ---\n{render_report(prev, reports.get(prev))}")
            if node == "otto_final":
                parts.append(f"--- Python's check of your draft ---\n{state.get('check_text', '')}")
            parts.append(f"Company list (in order): {', '.join(state['selected'])}")
            user = shown("\n\n".join(parts))
            save(node, user)
            res = client.structured(node=node, model=committee_model, system=shown(state["briefing"]), user=user,
                                    schema=schema, max_tokens=cfg.models.committee.max_tokens,
                                    effort=cfg.models.committee.effort, thinking_off=thinking_off,
                                    check=role_check(node, variant))
            parsed = res.parsed.model_dump() if res.ok else None
            missing = unknown = []
            if parsed is not None:
                for s in parsed["stocks"]:
                    s["company_id"] = real(s["company_id"])
                _, missing, unknown = by_company(parsed["stocks"], state["selected"])
            entry = {"node": node, "title": TITLES[node], "input": user, "ok": res.ok, "error": res.error,
                     "output": render_report(node, parsed), "missing": missing, "unknown": unknown,
                     "attempts": res.attempts, "api_calls": res.api_calls, "cache_hits": res.cache_hits,
                     "usd": res.usd, "usage": res.usage}
            return {"reports": {node: parsed}, "meetings": [entry]}
        return run

    def decision_of(parsed: dict | None, selected: list[str]) -> dict | None:
        """{company: multiplier} (baseline) or {company: (rating, confidence)} (enhanced); missing = no view."""
        if parsed is None:
            return None
        found, _, _ = by_company(parsed["stocks"], selected)
        if variant == "enhanced":
            return {c: (found[c]["rating"], float(found[c]["confidence"])) if c in found else ("hold", 0.0)
                    for c in selected}
        return {c: float(found[c]["multiplier"]) if c in found else 1.0 for c in selected}

    def draft_check(state: AgentState) -> dict:
        draft = decision_of(state["reports"].get("otto_draft"), state["selected"])
        if draft is None:
            return {"check_text": "Otto's draft is unavailable (no valid answer); the decision meeting starts from "
                                  "the benchmark weights (no views)."}
        return {"check_text": check_draft(inp, cfg, draft, ctx["stats"], state["reports"].get("dave"), variant,
                                          ctx.get("sigma"))}

    def optimizer(state: AgentState) -> dict:
        final = decision_of(state["reports"].get("otto_final"), state["selected"])
        draft = decision_of(state["reports"].get("otto_draft"), state["selected"])
        if final is not None:
            dec, source = final, "decision meeting"
        elif draft is not None:
            dec, source = draft, "strategy meeting draft (the decision meeting gave no valid answer)"
        else:
            dec = {c: ("hold", 0.0) if variant == "enhanced" else 1.0 for c in state["selected"]}
            source = "no view: benchmark weights (no valid decision)"
        w, details = weights_for(inp, cfg, dec, variant, ctx.get("sigma"))
        if variant == "enhanced":   # track record and transcript: a multiplier-equivalent plus the label
            mult = {c: RATING_EQUIV[r] if conf > 0 else 1.0 for c, (r, conf) in dec.items()}
            labels = {c: f"{r} ({conf:.1f})" for c, (r, conf) in dec.items()}
        else:
            mult, labels = dec, {}
        return {"multipliers": mult, "labels": labels, "decision_source": source,
                "weights": {c: float(v) for c, v in w.items()}, "bl": details}

    g = StateGraph(AgentState)
    g.add_node("coverage", coverage)
    g.add_node("memo", memo)
    g.add_node("briefing", briefing)
    g.add_node("emily", meeting("emily", ()))
    g.add_node("bob", meeting("bob", ("emily",)))
    g.add_node("dave", meeting("dave", ("emily", "bob")))
    g.add_node("otto_draft", meeting("otto_draft", ("emily", "bob", "dave")))
    g.add_node("draft_check", draft_check)
    g.add_node("otto_final", meeting("otto_final", ("emily", "bob", "dave", "otto_draft")))
    g.add_node("optimizer", optimizer)
    g.add_edge(START, "coverage")
    g.add_conditional_edges("coverage", fan_out, ["memo"])
    g.add_edge("memo", "briefing")
    for a, b in (("briefing", "emily"), ("emily", "bob"), ("bob", "dave"), ("dave", "otto_draft"),
                 ("otto_draft", "draft_check"), ("draft_check", "otto_final"), ("otto_final", "optimizer"),
                 ("optimizer", END)):
        g.add_edge(a, b)
    return g.compile()


def quant_agents(inp: GraphInputs, gw, cfg, client, variant: str = "baseline", anon=None,
                 inputs_dir: Path | None = None) -> dict:
    """Run the graph for one rebalance. Pure apart from the response cache, the cost ledger and the
    saved copies of the LLM inputs."""
    if variant not in ("baseline", "enhanced"):
        raise ValueError(f"unknown variant {variant!r}")
    app = build_graph(inp, gw, cfg, client, variant, anon, inputs_dir)
    state = app.invoke({"reports": {}}, config={"max_concurrency": cfg.agents.memo_concurrency,
                                                "recursion_limit": 50})
    state["memos"] = sorted(state["memos"], key=lambda d: d["company_id"])   # parallel order is not fixed
    return state


# ----------------------------------------------------------------------------- strategy for the engine
class AgentCommittee:
    """The engine strategy ``agents``: decide(ctx) -> Decision, writing memos and a transcript."""
    name = "agents"

    def __init__(self, cfg, run_id: str, run_dir: Path, variant: str = "baseline", client=None):
        from quantagents.llm.client import LLMClient
        self.cfg, self.run_id, self.run_dir, self.variant = cfg, run_id, Path(run_dir), variant
        self.client = client or LLMClient(cfg, run_id, variant=variant)

    def decide(self, ctx):
        from quantagents.agents.transcript import render
        from quantagents.engine.strategies import Decision
        u = ctx.gateway.get_universe(ctx.as_of).set_index("company_id")
        label = benchmark_label(self.cfg)
        order = sorted(ctx.bench.index, key=lambda c: (-float(ctx.bench[c]), c))     # largest first
        inp = GraphInputs(as_of=ctx.as_of, companies=order, bench=ctx.bench, sectors=ctx.sectors,
                          names={c: str(u["name"].get(c, c)) for c in ctx.bench.index},
                          constraints=ctx.constraints, holdings=ctx.holdings, prior_report=ctx.prior_report,
                          history=list(getattr(ctx, "history", []) or []), benchmark_label=label)
        anon = None
        if self.cfg.names_hidden:
            from quantagents.agents.anonymize import for_run
            anon = for_run(ctx.gateway, ctx.as_of, list(ctx.bench.index), self.run_dir)
        day = inp.day
        before = dict(self.client.stats)
        state = quant_agents(inp, ctx.gateway, self.cfg, self.client, self.variant, anon,
                             self.run_dir / "llm_inputs" / day)
        cost = {k: self.client.stats[k] - before.get(k, 0) for k in ("usd", "api_calls", "cache_hits")}
        mdir = self.run_dir / "memos" / day
        mdir.mkdir(parents=True, exist_ok=True)
        for d in state["memos"]:
            m = ResearchMemo(**d)
            (mdir / f"{m.company_id}.json").write_text(json.dumps(d, indent=2), encoding="utf-8")
            (mdir / f"{m.company_id}.md").write_text(memo_markdown(m), encoding="utf-8")
        tdir = self.run_dir / "transcripts"
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / f"{day}.md").write_text(render(inp, state, cost, self.cfg, MEMO_PROMPT), encoding="utf-8")
        ddir = self.run_dir / "decisions"
        ddir.mkdir(parents=True, exist_ok=True)
        final = state["reports"].get("otto_final") or state["reports"].get("otto_draft") or {}
        report = {"rebalance": day, "summary": final.get("summary", ""), "views": state["multipliers"],
                  "labels": state.get("labels") or {}, "variant": self.variant, "names_hidden": self.cfg.names_hidden,
                  "source": state["decision_source"], "llm": cost,
                  "failed_meetings": [m["node"] for m in state["meetings"] if not m["ok"]],
                  "failed_memos": [d["company_id"] for d in state["memos"] if not d["ok"]]}
        (ddir / f"{day}.json").write_text(json.dumps({**report, "weights": state["weights"]}, indent=2),
                                          encoding="utf-8")
        return Decision(pd.Series(state["weights"], dtype=float), report)

    def summary(self) -> str:
        return self.client.summary()


def main(argv: list[str] | None = None) -> int:
    """Free preview: print the committee briefing for one date (memos replaced by placeholders, no API call)."""
    import argparse
    import sys

    from quantagents.config import CONFIG_DIR, load_config
    from quantagents.data.gateway import Gateway
    from quantagents.data.universe import as_of_close, resolve_universe
    from quantagents.eval.benchmarks import renormalise
    from quantagents.paths import Paths
    from quantagents.portfolio.constraints import ConstraintSet
    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument("--config", default=str(CONFIG_DIR / "proto20.yaml"))
    ap.add_argument("--as-of", required=True)
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    paths = Paths.from_config(cfg)
    t = as_of_close(args.as_of)
    full = Gateway(paths.duckdb_file)
    try:
        companies = resolve_universe(cfg, full).at(full, t)
    finally:
        full.close()
    gw = Gateway(paths.duckdb_file, freeze_at=t)
    try:
        u = gw.get_universe(t).set_index("company_id")
        bench = renormalise(gw.get_index_weights(t).set_index("company_id")["weight"], companies)
        sectors = u["sector"].reindex(bench.index).fillna("Unknown")
        order = sorted(bench.index, key=lambda c: (-float(bench[c]), c))
        inp = GraphInputs(t, order, bench, sectors, {c: str(u["name"].get(c, c)) for c in order},
                          ConstraintSet.from_config(cfg, bench, sectors), {}, benchmark_label=benchmark_label(cfg))
        day = inp.day
        memos = {c: ResearchMemo.no_view(c, day, "dry-run", MEMO_PROMPT, "dry run: memo not written") for c in order}
        selected, rest = select(memos, bench, sectors, cfg.selection.max_views, cfg.selection.max_per_sector)
        text, _ = build_briefing(inp, gw, cfg, memos, selected, rest)
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
        print(f"\n[{len(text):,} characters, about {len(text) // 4:,} tokens without the memo summaries; "
              f"20 real memo summaries add about 8,000 tokens]")
    finally:
        gw.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
