"""Baseline and enhanced share the same universe, data, memos, briefing, constraints, costs and engine.
Only Otto's answer format, his two prompts and the weights step differ."""
import pandas as pd

from quantagents.agents.graph import quant_agents
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway
from tests.graph_helpers import graph_config, inputs_at, private_client
from tests.llm_fakes import CommitteeFake, node_of

DAY = "2015-04-01"


def test_only_the_decision_step_differs(synthetic_db, tmp_path, monkeypatch):
    monkeypatch.setenv("QA_STORE_ROOT", str(synthetic_db[0]))
    cfg = graph_config(synthetic_db[0], tmp_path)
    gw = Gateway(synthetic_db[1], freeze_at=cal.as_of_for(pd.Timestamp(DAY)))
    try:
        inp = inputs_at(gw, cfg, DAY)
        fb, fe = CommitteeFake(), CommitteeFake()
        base = quant_agents(inp, gw, cfg, private_client(cfg, tmp_path, fb, name="b"), "baseline")
        enh = quant_agents(inp, gw, cfg, private_client(cfg, tmp_path, fe, name="e"), "enhanced")
    finally:
        gw.close()
    assert base["briefing"] == enh["briefing"] and base["memos"] == enh["memos"]
    assert base["selected"] == enh["selected"]
    memo_b = [c for c in fb.calls if node_of(c) == "memo"]
    memo_e = [c for c in fe.calls if node_of(c) == "memo"]
    assert sorted(map(str, memo_b)) == sorted(map(str, memo_e))          # identical memo requests
    for node in ("emily", "bob", "dave"):                                # same prompts; only the schema differs
        rb = next(c for c in fb.calls if node_of(c) == node)
        re_ = next(c for c in fe.calls if node_of(c) == node)
        assert rb["system"] == re_["system"] and rb["messages"] == re_["messages"]
    assert [m["node"] for m in base["meetings"]] == [m["node"] for m in enh["meetings"]]
    # both portfolios obey the same constraint set
    for s in (base, enh):
        w = pd.Series(s["weights"]).reindex(list(inp.constraints.companies)).to_numpy()
        assert inp.constraints.violations(w) == []
