"""The transcript holds every meeting's input and output, the Python check, the briefing and the decision."""
import pandas as pd

from quantagents.agents.graph import TITLES, quant_agents
from quantagents.agents.memo import PROMPT_VERSION
from quantagents.agents.transcript import render
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway
from tests.graph_helpers import graph_config, inputs_at, private_client
from tests.llm_fakes import CommitteeFake


def test_transcript_has_every_meeting(synthetic_db, tmp_path, monkeypatch):
    monkeypatch.setenv("QA_STORE_ROOT", str(synthetic_db[0]))
    cfg = graph_config(synthetic_db[0], tmp_path)
    gw = Gateway(synthetic_db[1], freeze_at=cal.as_of_for(pd.Timestamp("2015-03-02")))
    try:
        inp = inputs_at(gw, cfg, "2015-03-02")
        state = quant_agents(inp, gw, cfg, private_client(cfg, tmp_path, CommitteeFake()))
    finally:
        gw.close()
    md = render(inp, state, {"usd": 0.01, "api_calls": 9, "cache_hits": 0}, cfg, PROMPT_VERSION)
    for node, title in TITLES.items():
        assert f"### {title}" in md
        m = next(x for x in state["meetings"] if x["node"] == node)
        assert m["input"].strip()[:60] in md and m["output"].strip()[:40] in md
    assert "### Python's check of the draft" in md and state["check_text"][:50] in md
    assert "## Shared briefing" in md and "5. SIMULATED TRADING" in md and "7. TRACK RECORD" in md
    assert "Source: **decision meeting**" in md
    for c in inp.companies:
        assert f"| {c} |" in md
