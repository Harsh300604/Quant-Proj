"""A broken committee answer is retried once, then the graph falls back (and logs it)."""
import pandas as pd
import pytest

from quantagents.agents.graph import quant_agents
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway
from quantagents.portfolio.baseline_opt import weights_from_multipliers
from tests.graph_helpers import graph_config, inputs_at, private_client
from tests.llm_fakes import CommitteeFake, companies_of, default_answer

DAY = "2015-03-02"


@pytest.fixture
def env(synthetic_db, tmp_path, monkeypatch):
    monkeypatch.setenv("QA_STORE_ROOT", str(synthetic_db[0]))
    cfg = graph_config(synthetic_db[0], tmp_path)
    gw = Gateway(synthetic_db[1], freeze_at=cal.as_of_for(pd.Timestamp(DAY)))
    yield cfg, gw, inputs_at(gw, cfg, DAY), tmp_path
    gw.close()


def go(env, answers):
    cfg, gw, inp, tmp = env
    fake = CommitteeFake(answers)
    client = private_client(cfg, tmp, fake)
    return quant_agents(inp, gw, cfg, client), fake, client


def test_broken_analyst_is_retried_then_skipped(env):
    state, fake, client = go(env, {"emily": "{not json"})
    assert fake.nodes().count("emily") == 2                      # one retry
    emily = next(m for m in state["meetings"] if m["node"] == "emily")
    assert not emily["ok"] and "schema" in emily["error"] and emily["api_calls"] == 2
    bob = next(m for m in state["meetings"] if m["node"] == "bob")
    assert "(no valid answer this month)" in bob["input"]        # Bob is told Emily has nothing
    assert state["decision_source"] == "decision meeting"
    assert (client.ledger.frame()["node"] == "emily").sum() == 2  # both attempts are in the ledger


def test_broken_final_decision_falls_back_to_the_draft(env):
    state, _, _ = go(env, {"otto_final": {"summary": "x", "concerns": [], "stocks": "nope"}})
    assert state["decision_source"].startswith("strategy meeting draft")
    assert max(state["multipliers"].values()) == 1.5


def test_no_valid_decision_means_benchmark_weights(env):
    state, _, _ = go(env, {"otto_draft": "{", "otto_final": "{"})
    assert state["decision_source"].startswith("no view")
    assert set(state["multipliers"].values()) == {1.0}
    expected = weights_from_multipliers(env[2].constraints)
    assert pd.Series(state["weights"]).sort_index().round(12).equals(expected.sort_index().round(12))


def test_multiplier_off_the_scale_is_rejected(env):
    def bad(req):
        a = default_answer("otto_final", req)
        a["stocks"][0]["multiplier"] = 1.1                    # not a step of 0.25
        return a
    state, fake, _ = go(env, {"otto_final": bad})
    assert fake.nodes().count("otto_final") == 2 and state["decision_source"].startswith("strategy meeting draft")


def test_missing_and_unknown_companies(env):
    def partial(req):
        cs = companies_of(req)
        e = {"view": None, "conviction": None, "risk": None}
        return {"summary": "s", "concerns": [], "stocks": [{"company_id": cs[0], **e, "multiplier": 2.0, "reason": "r"},
                                                           {"company_id": "ZZZ", **e, "multiplier": 0.0, "reason": "r"}]}
    state, _, _ = go(env, {"otto_final": partial})
    final = next(m for m in state["meetings"] if m["node"] == "otto_final")
    first = state["selected"][0]
    assert final["unknown"] == ["ZZZ"] and set(final["missing"]) == set(state["selected"][1:])
    assert state["multipliers"][first] == 2.0
    assert all(state["multipliers"][c] == 1.0 for c in state["selected"][1:])


def test_role_must_fill_its_own_fields(env):
    def no_risk(req):
        a = default_answer("dave", req)
        a["stocks"][1]["risk"] = None                          # Dave left a risk rating empty
        return a
    state, fake, _ = go(env, {"dave": no_risk})
    dave = next(m for m in state["meetings"] if m["node"] == "dave")
    assert fake.nodes().count("dave") == 2 and not dave["ok"] and "left risk empty" in dave["error"]


def test_every_meeting_uses_the_same_schema(env):
    """The output schema is part of the cached prompt prefix: one schema keeps it identical."""
    _, fake, _ = go(env, {})
    committee = [r for r in fake.calls if fake.nodes()[fake.calls.index(r)] != "memo"]
    assert len({str(r["output_config"]) for r in committee}) == 1
    assert len({r["system"][0]["text"] for r in committee}) == 1


def test_failed_memo_becomes_no_view_and_is_reported(env):
    state, _, _ = go(env, {"memo": "{"})
    assert all(not d["ok"] for d in state["memos"])
    assert "No valid research memo this month" in state["briefing"]
