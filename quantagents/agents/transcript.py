"""One markdown transcript per rebalance: every meeting's input and output, the Python checks,
the final weights and the cost. Written to runs/<run_id>/transcripts/<date>.md.

Layout: decision summary first (what a reader wants), then the meetings in order, then the
shared briefing every committee member read (the prompt-cached block), then the memo list.
"""
from __future__ import annotations

import pandas as pd


def _block(text: str) -> str:
    return "```text\n" + text.strip() + "\n```"


def render(inp, state: dict, cost: dict, cfg, memo_prompt: str) -> str:
    bench = inp.bench
    w = pd.Series(state["weights"], dtype=float)
    mult = state["multipliers"]
    out = [f"# Committee meeting, {inp.day}", "",
           f"Decision at the market close of {inp.day}; trades at the next open. Benchmark: {inp.benchmark_label}.",
           f"Models: memos {cfg.models.active.memo}, committee {cfg.models.active.committee} "
           f"(tier `{cfg.models.tier}`, committee thinking `{cfg.models.committee.thinking}`, effort "
           f"`{cfg.models.committee.effort}`).",
           f"Cost of this meeting: ${cost['usd']:.4f} (Rs {cost['usd'] * cfg.budget.inr_per_usd:.2f}); "
           f"API calls {cost['api_calls']}, cache hits {cost['cache_hits']}.", ""]

    failed_memos = [d["company_id"] for d in state["memos"] if not d["ok"]]
    failed_meet = [m["node"] for m in state["meetings"] if not m["ok"]]
    out += ["## Decision", "", f"Source: **{state['decision_source']}**.", ""]
    if failed_memos or failed_meet:
        out.append(f"Problems: failed memos {failed_memos or 'none'}; failed meetings {failed_meet or 'none'}.")
        out.append("")
    out += ["| company | sector | benchmark | Otto's multiplier | final weight | final multiplier |",
            "|---|---|---:|---:|---:|---:|"]
    for c in inp.companies:
        m = mult.get(c)
        out.append(f"| {c} | {inp.sectors[c]} | {bench[c]:.2%} | {'' if m is None else f'x{m:.2f}'} | "
                   f"{w.get(c, 0.0):.2%} | x{w.get(c, 0.0) / bench[c]:.2f} |")
    out += ["", "Final multiplier = final weight / benchmark weight, after Python applied the portfolio rules.", ""]

    out += ["## Meetings", ""]
    for m in state["meetings"]:
        out += [f"### {m['title']}", "",
                f"Answer valid: {'yes' if m['ok'] else 'NO (' + m['error'] + ')'}; attempts {m['attempts']}; "
                f"API calls {m['api_calls']}, cache hits {m['cache_hits']}; ${m['usd']:.4f}; tokens in "
                f"{m['usage'].get('input_tokens', 0)} + cache read {m['usage'].get('cache_read_input_tokens', 0)} + "
                f"cache write {m['usage'].get('cache_creation_input_tokens', 0)}, out {m['usage'].get('output_tokens', 0)}.", ""]
        if m["missing"] or m["unknown"]:
            out += [f"Companies missing from the answer (treated as no view): {m['missing'] or 'none'}; "
                    f"unknown ids ignored: {m['unknown'] or 'none'}.", ""]
        out += ["**Input (after the shared briefing):**", "", _block(m["input"]), "", "**Output:**", "",
                _block(m["output"]), ""]
        if m["node"] == "otto_draft":
            out += ["### Python's check of the draft", "", _block(state.get("check_text", "")), ""]

    out += ["## Shared briefing (every committee member read this; prompt-cached)", "", _block(state["briefing"]), ""]
    out += ["## Research memos", "",
            f"{len(state['memos'])} memos ({cfg.models.active.memo}, prompt {memo_prompt}); full text in "
            f"`memos/{inp.day}/`. Selected for the committee: {', '.join(state['selected'])}. "
            f"Others: {', '.join(state['rest']) or 'none'}.", ""]
    for d in state["memos"]:
        out.append(f"- {d['company_id']}: {d['outlook_3m']}, conviction {d['conviction']}"
                   + ("" if d["ok"] else f" (NO VALID MEMO: {d['error']})"))
    return "\n".join(out) + "\n"
