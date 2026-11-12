"""Cost ledger: maths, the three budget stops (proto20 $32 of $40), worst-case pre-check, INR."""
import importlib.util
from dataclasses import replace

import pytest

from quantagents.agents.schemas import MemoBody
from quantagents.config import CONFIG_DIR, load_config
from quantagents.llm.client import LLMClient
from quantagents.llm.ledger import BudgetExceeded, Ledger, Limits
from quantagents.llm.pricing import cost_usd, worst_case_usd
from tests.llm_fakes import GOOD_MEMO, FakeSDK, reply


@pytest.fixture
def cfg():
    return load_config(CONFIG_DIR / "pilot.yaml")


def spend(ledger, usd, stage="proto20", key="student", run="r"):
    ledger.record(run_id=run, node="n", model="claude-haiku-5-5", key_label=key, stage=stage, variant="baseline",
                  usage={}, cache_hit=False, usd=usd, inr_per_usd=88.0)


def test_cost_maths_all_four_token_types():
    u = {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000,
         "cache_read_input_tokens": 1_000_000}
    assert cost_usd("claude-haiku-5-5", u) == pytest.approx(0.10 + 0.50 + 0.125 + 0.01)
    assert cost_usd("claude-sonnet-5-5", u) == pytest.approx(2.0 + 10.0 + 2.5 + 0.2)
    assert cost_usd("claude-haiku-5-5", {"input_tokens": 2000, "output_tokens": 400}) == pytest.approx(0.0004)


def test_worst_case_uses_all_max_tokens():
    assert worst_case_usd("claude-sonnet-5-5", 10_000, 4000) == pytest.approx(10_000 * 2.5e-6 + 4000 * 10e-6)


def test_proto20_stage_stops_at_32_dollars(cfg):
    lim = Limits.from_config(cfg)
    assert (lim.stage, lim.stage_budget, lim.stage_stop) == ("proto20", 40.0, 32.0)
    led = Ledger(":memory:")
    lim = replace(lim, run_budget=100.0)
    spend(led, 31.99)
    led.check(lim, "r", worst_case_usd=0.005)                     # still under $32
    with pytest.raises(BudgetExceeded, match=r"BLOCKED: stage 'proto20' at 80% of \$40.00"):
        led.check(lim, "r", worst_case_usd=0.02)                 # could cross $32
    spend(led, 0.02)
    with pytest.raises(BudgetExceeded, match="stage 'proto20'"):
        led.check(lim, "r", worst_case_usd=0.0)


def test_key_stop_counts_every_stage(cfg):
    led = Ledger(":memory:")
    lim = replace(Limits.from_config(cfg), run_budget=1000.0, stage_stop=1000.0)
    spend(led, 100.0, stage="stage2")
    spend(led, 42.0, stage="proto20")
    with pytest.raises(BudgetExceeded, match=r"key 'student' at 95% of \$150.00"):
        led.check(lim, "r", worst_case_usd=1.0)


def test_run_budget(cfg):
    led = Ledger(":memory:")
    lim = Limits.from_config(cfg)                               # pilot run budget $0.10
    spend(led, 0.099, run="pilot")
    with pytest.raises(BudgetExceeded, match="run 'pilot'"):
        led.check(lim, "pilot", worst_case_usd=0.002)
    led.check(lim, "another_run", worst_case_usd=0.002)


def test_client_refuses_before_calling_the_api(cfg):
    sdk = FakeSDK([reply(GOOD_MEMO)])
    c = LLMClient(cfg, "pilot", sdk=sdk)
    spend(c.ledger, 31.9999)          # a worst-case Haiku memo (~$0.0008) would cross $32
    with pytest.raises(BudgetExceeded):
        c.structured(node="memo", model="claude-haiku-5-5", system="s", user="u", schema=MemoBody,
                     max_tokens=1500, effort="low")
    assert sdk.messages.calls == []


def test_calls_recorded_with_usd_inr_and_cache_flag(cfg):
    c = LLMClient(cfg, "pilot", sdk=FakeSDK([reply(GOOD_MEMO, input_tokens=2000, output_tokens=400)]))
    for _ in range(2):
        c.structured(node="memo", model="claude-haiku-5-5", system="s", user="u", schema=MemoBody,
                     max_tokens=800, effort="low")
    df = c.ledger.frame()
    assert df["cache_hit"].tolist() == [0, 1]
    assert df["usd"].tolist() == pytest.approx([0.0004, 0.0])
    assert df["inr"].iloc[0] == pytest.approx(0.0004 * 88.0)
    assert set(df["key_label"]) == {"student"} and set(df["stage"]) == {"proto20"}


def test_ledger_report_simulation_blocks_and_does_not_touch_the_real_ledger(cfg, capsys):
    spec = importlib.util.spec_from_file_location("lr", CONFIG_DIR.parent / "scripts" / "ledger_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    LLMClient(cfg, "pilot", sdk=FakeSDK([reply(GOOD_MEMO)])).structured(
        node="memo", model="claude-haiku-5-5", system="s", user="u", schema=MemoBody, max_tokens=800, effort="low")
    assert mod.main(["--config", str(CONFIG_DIR / "pilot.yaml"), "--simulate-spend", "32.01"]) == 0
    out = capsys.readouterr().out
    assert "BLOCKED: stage 'proto20' at 80% of $40.00 budget" in out
    assert "student" in out and "sk-ant" not in out
    assert len(LLMClient(cfg, "x", sdk=FakeSDK()).ledger.frame()) == 1      # simulation not written
