"""Sonnet measurement pilot (main plan Phase 6, brief section 8): committee thinking OFF vs ON.

Runs the agent committee on the paper tier (memos Haiku, committee Sonnet) for the first N
rebalances of a config, twice: thinking off (`between_tools`) and thinking on (the model's
default at effort medium). Writes runs/thinking_pilot/summary.md: tokens, cost per call and per
rebalance, the decisions side by side and sample reasoning, for the user to judge.
Thinking stays OFF unless the user decides otherwise (D46). PAID: ask the user first.

    python scripts\\thinking_pilot.py --config configs\\pilot.yaml --rebalances 3
"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from quantagents.config import CONFIG_DIR, load_config
from quantagents.engine.backtest import StopRequested, run
from quantagents.llm.ledger import Ledger
from quantagents.paths import Paths

TOKENS = ["input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens", "usd"]


def variant_cfg(cfg, thinking: str, budget: float):
    models = cfg.models.model_copy(update={
        "tier": "paper",
        "committee": cfg.models.committee.model_copy(update={"thinking": thinking,
                                                              "max_tokens": 6000 if thinking == "between_tools" else 16000})})
    return cfg.model_copy(update={"models": models,
                                  "budget": cfg.budget.model_copy(update={"run_budget_usd": budget})})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(CONFIG_DIR / "pilot.yaml"))
    ap.add_argument("--rebalances", type=int, default=3)
    ap.add_argument("--variant", default="baseline", choices=["baseline", "enhanced"])
    ap.add_argument("--run-budget", type=float, default=1.50, help="USD cap per run (each of the two runs)")
    args = ap.parse_args(argv)
    base = load_config(args.config)
    paths = Paths.from_config(base)
    out = paths.runs / "thinking_pilot"
    out.mkdir(parents=True, exist_ok=True)
    runs = {"off": "thinking_off_pilot", "on": "thinking_on_pilot"}
    for key, rid in runs.items():
        cfg = variant_cfg(base, "between_tools" if key == "off" else "default", args.run_budget)
        try:
            run(cfg, "agents", rid, stop_after=args.rebalances, variant=args.variant)
        except StopRequested:
            pass
    led = Ledger(paths.ledger).frame()
    lines = [f"# Thinking pilot: committee on Sonnet, thinking off vs on ({args.rebalances} rebalances, "
             f"{args.variant})", ""]
    lines += ["| run | node | API calls | avg fresh input | avg cache read | avg output | USD |",
              "|---|---|---:|---:|---:|---:|---:|"]
    tot = {}
    for key, rid in runs.items():
        d = led[(led["run_id"] == rid) & (led["cache_hit"] == 0)]
        tot[key] = float(d["usd"].sum())
        for node, g in d.groupby("node"):
            lines.append(f"| {key} | {node} | {len(g)} | {g['input_tokens'].mean():,.0f} | "
                         f"{g['cache_read_input_tokens'].mean():,.0f} | {g['output_tokens'].mean():,.0f} | "
                         f"{g['usd'].sum():.4f} |")
    lines += ["", f"Total: thinking off ${tot['off']:.4f}, thinking on ${tot['on']:.4f} "
                  f"(x{tot['on'] / tot['off']:.2f})" if tot.get("off") else "", "",
              "## Decisions side by side", ""]
    for f in sorted((paths.runs / runs["off"] / "decisions").glob("*.json")):
        a = json.loads(f.read_text(encoding="utf-8"))
        g = paths.runs / runs["on"] / "decisions" / f.name
        b = json.loads(g.read_text(encoding="utf-8")) if g.exists() else {}
        lines += [f"### {a['rebalance']}", "", "| company | thinking off | thinking on |", "|---|---|---|"]
        for c in a["views"]:
            fa = (a.get("labels") or {}).get(c) or f"x{a['views'][c]:.2f}"
            fb = (b.get("labels") or {}).get(c) or (f"x{b['views'][c]:.2f}" if c in b.get("views", {}) else "-")
            lines.append(f"| {c} | {fa} | {fb} |")
        lines += ["", f"Off: {a.get('summary', '')}", "", f"On: {b.get('summary', '')}", ""]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))
    print(f"written: {out / 'summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
