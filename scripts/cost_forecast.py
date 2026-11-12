"""Cost forecast v1 -> docs/cost_forecast.md (no API calls; reads the cost ledger).

    python scripts\\cost_forecast.py                       # measured run: proto20_2021_base_dev
    python scripts\\cost_forecast.py --run-id pilot_base_dev --companies 5
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from quantagents.config import CONFIG_DIR, REPO_ROOT, load_config, load_stage_budgets
from quantagents.eval.cost_forecast import cache_read_share, profile, project
from quantagents.llm.ledger import Ledger
from quantagents.llm.pricing import load_pricing
from quantagents.paths import Paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(CONFIG_DIR / "proto20.yaml"))
    ap.add_argument("--run-id", default="proto20_2021_base_dev", help="the measured run")
    ap.add_argument("--companies", type=int, help="companies per rebalance in the measured run (default: from the run)")
    ap.add_argument("--out", default=str(REPO_ROOT / "docs" / "cost_forecast.md"))
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    paths = Paths.from_config(cfg)
    summary = json.loads((paths.runs / args.run_id / "summary.json").read_text(encoding="utf-8"))
    rebs = int(summary["rebalances"])
    ledger = Ledger(paths.ledger).frame()
    rows = ledger[(ledger["run_id"] == args.run_id) & (ledger["cache_hit"] == 0)]
    n_comp = args.companies or round((rows["node"] == "memo").sum() / rebs)
    prof = profile(ledger, args.run_id, rebs, n_comp)
    prices = load_pricing()
    tiers = cfg.models.tiers
    inr = cfg.budget.inr_per_usd
    stage = load_stage_budgets()[cfg.budget.stage]
    spent = float(ledger[(ledger["stage"] == cfg.budget.stage) & (ledger["key_label"] == cfg.budget.key_label)]["usd"].sum())
    measured_usd = float(rows["usd"].sum())

    def proj(r, n, tier):
        return project(prof, rebalances=r, companies=n, memo_model=tiers[tier].memo,
                       committee_model=tiers[tier].committee, prices=prices)

    dev = proj(1, 20, "dev")
    paper1 = proj(1, 20, "paper")
    p6 = [("Sonnet measurement pilot, thinking off (3 rebalances x 5 companies)", proj(3, 5, "paper"), 1.0),
          ("Sonnet measurement pilot, thinking on (rough: committee x2.5)", proj(3, 5, "paper"), 2.5),
          ("proto20 baseline, 2021-2023, paper tier (36 x 20)", proj(36, 20, "paper"), 1.0),
          ("proto20 enhanced, 2021-2023, paper tier (36 x 20)", proj(36, 20, "paper"), 1.0),
          ("proto20 names-hidden enhanced (optional, D44)", proj(36, 20, "paper"), 1.0)]
    full = [("Full baseline 2015-2023, paper tier (108 x ~100)", proj(108, 100, "paper")),
            ("Full enhanced 2015-2023, paper tier", proj(108, 100, "paper")),
            ("Full names-hidden enhanced, paper tier", proj(108, 100, "paper"))]

    def usd(p, mult=1.0):
        committee = p.committee_usd * mult
        return p.memo_usd + committee

    lines = [f"# Cost forecast v1 ({date.today()})", "",
             f"Measured on run `{args.run_id}`: {rebs} rebalances x {n_comp} companies, models "
             f"{', '.join(sorted(set(prof['model'])))}; it cost **${measured_usd:.4f}** (Rs {measured_usd * inr:.2f}). "
             f"Prices: `configs/pricing.yaml`. Exchange rate: Rs {inr:g} per USD. Ranges are +-20%.", "",
             "## Measured token profile (per API call)", "",
             "| node | model | calls per rebalance | fresh input | cache write | cache read | output |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for node, r in prof.iterrows():
        per = "per company" if node == "memo" else ""
        lines.append(f"| {node} | {r['model']} | {r['calls_per_rebalance']:.2f} {per} | {r['input_tokens']:,.0f} | "
                     f"{r['cache_creation_input_tokens']:,.0f} | {r['cache_read_input_tokens']:,.0f} | {r['output_tokens']:,.0f} |")
    lines += ["", f"Committee prompt-cache read share: **{cache_read_share(prof):.0%}** of committee input tokens "
              f"(memos: {cache_read_share(prof, ('memo',)):.0%}).", "",
              "## Per rebalance (20 companies)", "",
              f"- dev tier (Haiku committee): ${dev.usd:.4f} (memos ${dev.memo_usd:.4f}, committee ${dev.committee_usd:.4f})",
              f"- paper tier (Sonnet committee): ${paper1.usd:.4f} (memos ${paper1.memo_usd:.4f}, committee "
              f"${paper1.committee_usd:.4f}); the brief's planning figure was about $0.25", "",
              "## P6 runs against the MVP budget", "",
              "| run | USD | range | INR |", "|---|---:|---:|---:|"]
    total = 0.0
    for name, p, mult in p6:
        u = usd(p, mult)
        total += u
        lines.append(f"| {name} | ${u:.2f} | ${u * 0.8:.2f}-${u * 1.2:.2f} | Rs {u * inr:,.0f} |")
    remaining = stage.budget_usd - spent
    lines += [f"| **Total P6** | **${total:.2f}** | ${total * 0.8:.2f}-${total * 1.2:.2f} | Rs {total * inr:,.0f} |", "",
              f"MVP budget (stage `{cfg.budget.stage}`): ${stage.budget_usd:.2f}; spent so far ${spent:.4f}; remaining "
              f"${remaining:.2f}; automatic stop at ${stage.stop_at_usd:.2f}. "
              + ("The P6 plan fits, with room for reruns." if total * 1.2 < stage.stop_at_usd - spent else
                 "**The P6 plan may not fit below the automatic stop: ask the user before P6.**"), "",
              "## Full runs (main plan, after proto20; separate approval)", "",
              "| run | USD | range |", "|---|---:|---:|"]
    ftot = 0.0
    for name, p in full:
        ftot += p.usd
        lines.append(f"| {name} | ${p.usd:.2f} | ${p.low:.2f}-${p.high:.2f} |")
    lines += [f"| **Total** | **${ftot:.2f}** | ${ftot * 0.8:.2f}-${ftot * 1.2:.2f} |", "",
              "## Assumptions", "",
              "- Sonnet answers are assumed to be as long as Haiku's (the +-20% range covers moderate differences; "
              "the Sonnet pilot in P6 measures it).",
              "- The enhanced variant (P5) asks for a rating and confidence instead of a multiplier: about the same size.",
              "- Thinking on: committee cost x2.5 (brief section 8); thinking stays off unless the user approves (D46).",
              "- Full runs: ~100 memos per rebalance; the committee briefing adds ~40 tokens per extra company.",
              "- Reruns from the response cache cost $0.",
              "- The Sonnet pilot lines keep the 20-company committee size, so they are upper estimates "
              "(5 companies mean shorter briefings and answers).",
              "- Committee answers were about 2,000 output tokens per call on Haiku; output is about half of the "
              "Sonnet committee cost, so shorter answers are the main lever if the budget gets tight.", "",
              "## Summary to forward", "",
              f"We measured the full agent committee on {rebs} monthly decisions for {n_comp} companies: it cost "
              f"${measured_usd:.2f} on the cheap development model. On the paper's model mix, one monthly decision for "
              f"20 companies costs about ${paper1.usd:.2f}, so the three 36-month prototype runs plus the model pilot come "
              f"to about ${total:.0f} (${total * 0.8:.0f}-${total * 1.2:.0f}), against ${remaining:.0f} left of the "
              f"${stage.budget_usd:.0f} prototype budget. Nothing runs without approval first."]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwritten: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
