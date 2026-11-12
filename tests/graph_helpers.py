"""Helpers for the agent-graph tests (synthetic store, fake SDK, private cache and ledger)."""
from __future__ import annotations

import pandas as pd

from quantagents.agents.graph import GraphInputs, benchmark_label
from quantagents.config import CONFIG_DIR, load_config
from quantagents.data import calendar as cal
from quantagents.eval.benchmarks import renormalise
from quantagents.llm.cache import ResponseCache
from quantagents.llm.client import LLMClient
from quantagents.llm.ledger import Ledger
from quantagents.portfolio.constraints import ConstraintSet

COMPANIES = ["AAA", "BBB", "GOOGL", "OLD"]


def graph_config(root, tmp_path, end="2015-06-30"):
    f = tmp_path / "graph.yaml"
    f.write_text(f"extends: {(CONFIG_DIR / 'pilot.yaml').as_posix()}\nrun_id: graph_test\n"
                 f"dates: {{warmup_start: 2014-01-01, start: 2015-01-01, end: {end}}}\n"
                 f"universe: {{mode: tickers, tickers: [{', '.join(COMPANIES)}], add_removed_member: false}}\n"
                 "benchmark: {mode: custom_cap_index}\n", encoding="utf-8")
    return load_config(f)


def private_client(cfg, tmp_path, sdk, run_id="g", name="c"):
    """An LLMClient whose response cache and ledger live in tmp_path (no sharing between tests)."""
    c = LLMClient(cfg, run_id, sdk=sdk)
    c.cache = ResponseCache(tmp_path / f"{name}_responses.sqlite")
    c.ledger = Ledger(tmp_path / f"{name}_ledger.sqlite")
    return c


def inputs_at(gw, cfg, day: str, holdings=None, history=None, prior=None) -> GraphInputs:
    t = cal.as_of_for(pd.Timestamp(day))
    u = gw.get_universe(t).set_index("company_id")
    members = [c for c in COMPANIES if c in u.index]
    bench = renormalise(gw.get_index_weights(t).set_index("company_id")["weight"], members)
    sectors = u["sector"].reindex(bench.index).fillna("Unknown")
    order = sorted(bench.index, key=lambda c: (-float(bench[c]), c))
    return GraphInputs(t, order, bench, sectors, {c: str(u["name"].get(c, c)) for c in order},
                       ConstraintSet.from_config(cfg, bench, sectors), holdings or {}, prior, history or [],
                       benchmark_label(cfg))
