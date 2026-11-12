"""The agent graph is a pure function of its inputs (plus the response cache); it never reads data
after the decision time; it runs inside the engine end to end (SDK faked, sockets blocked)."""
import json

import pandas as pd
import pytest

from quantagents.agents.graph import AgentCommittee, build_briefing, quant_agents
from quantagents.agents.schemas import ResearchMemo
from quantagents.agents.selection import select
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway
from quantagents.engine.backtest import run
from tests.graph_helpers import graph_config, inputs_at, private_client
from tests.llm_fakes import GOOD_MEMO, CommitteeFake, FakeSDK

DAY = "2015-04-01"


@pytest.fixture
def cfg(synthetic_db, tmp_path, monkeypatch):
    monkeypatch.setenv("QA_STORE_ROOT", str(synthetic_db[0]))
    return graph_config(synthetic_db[0], tmp_path)


def test_engine_runs_the_committee_end_to_end(cfg, synthetic_db, tmp_path):
    fake = CommitteeFake()
    run_dir = synthetic_db[0] / "runs" / "agents_e2e"
    strat = AgentCommittee(cfg, "agents_e2e", run_dir, client=private_client(cfg, tmp_path, fake))
    s = run(cfg, "agents", "agents_e2e", strategy=strat, fresh=True, quiet=True)
    assert s["rebalances"] == 6 and s["red_flags"] == [] and s["variant"] == "baseline"
    days = sorted(p.stem for p in (run_dir / "transcripts").glob("*.md"))
    assert days == ["2015-01-02", "2015-02-02", "2015-03-02", "2015-04-01", "2015-05-01", "2015-06-01"]
    # per rebalance: one memo per company, then exactly 5 committee calls in order
    nodes = fake.nodes()
    assert [n for n in nodes if n != "memo"] == ["emily", "bob", "dave", "otto_draft", "otto_final"] * 6
    checks = pd.read_csv(run_dir / "checks.csv")
    assert (pd.to_datetime(checks["max_read"]) <= pd.to_datetime(checks["as_of"])).all()
    d = json.loads((run_dir / "decisions" / "2015-03-02.json").read_text())
    assert d["source"] == "decision meeting" and abs(sum(d["weights"].values()) - 1) < 1e-9
    # track record: empty until the first 3-month outcome is known (Jan views end on 1 Apr)
    march = (run_dir / "transcripts" / "2015-03-02.md").read_text(encoding="utf-8")
    april = (run_dir / "transcripts" / "2015-04-01.md").read_text(encoding="utf-8")
    assert "No track record yet" in march and "ends on 2015-04-01" in march
    assert "Views made 2015-01-02 (outcome to 2015-04-01" in april and "Views made 2015-02-02" not in april


def test_same_inputs_and_cache_give_identical_outputs_without_api_calls(cfg, synthetic_db, tmp_path):
    gw = Gateway(synthetic_db[1], freeze_at=cal.as_of_for(pd.Timestamp(DAY)))
    try:
        inp = inputs_at(gw, cfg, DAY)
        first = quant_agents(inp, gw, cfg, private_client(cfg, tmp_path, CommitteeFake()))
        replay = private_client(cfg, tmp_path, FakeSDK([]))          # any API call would fail
        second = quant_agents(inp, gw, cfg, replay)
        assert replay.stats["api_calls"] == 0 and replay.stats["cache_hits"] == len(inp.companies) + 5
        for k in ("weights", "multipliers", "briefing", "selected", "memos", "check_text", "decision_source"):
            assert first[k] == second[k], k
        assert [m["output"] for m in first["meetings"]] == [m["output"] for m in second["meetings"]]
        assert gw.max_as_of <= inp.as_of                         # nothing read after the decision time
    finally:
        gw.close()


def test_briefing_is_identical_when_later_data_is_removed(cfg, synthetic_db):
    """Simulated trading, risk stats, price table and track record use only data known at the decision."""
    t = cal.as_of_for(pd.Timestamp(DAY))
    history = [{"rebalance": "2015-01-02", "views": {"AAA": 1.5, "BBB": 0.75, "GOOGL": 1.0, "OLD": 1.0},
                "bench": {"AAA": 0.1, "BBB": 0.7, "GOOGL": 0.1, "OLD": 0.1}}]
    texts = []
    for db in (synthetic_db[1], synthetic_db[2](t)):
        gw = Gateway(db, freeze_at=t)
        try:
            inp = inputs_at(gw, cfg, DAY, holdings={"AAA": 0.2, "BBB": 0.6, "GOOGL": 0.1, "OLD": 0.1}, history=history)
            memos = {c: ResearchMemo(**GOOD_MEMO, company_id=c, as_of=DAY, model="m", prompt_version="p")
                     for c in inp.companies}
            sel, rest = select(memos, inp.bench, inp.sectors, 20, None)
            texts.append(build_briefing(inp, gw, cfg, memos, sel, rest)[0])
        finally:
            gw.close()
    assert texts[0] == texts[1]
    assert "Views made 2015-01-02" in texts[0]


def test_enhanced_variant_is_not_built_yet(cfg, synthetic_db, tmp_path):
    gw = Gateway(synthetic_db[1], freeze_at=cal.as_of_for(pd.Timestamp(DAY)))
    try:
        with pytest.raises(NotImplementedError, match="P5"):
            quant_agents(inputs_at(gw, cfg, DAY), gw, cfg, private_client(cfg, tmp_path, CommitteeFake()), "enhanced")
    finally:
        gw.close()
