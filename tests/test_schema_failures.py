"""Invalid LLM output is retried, then logged and defaulted to 'no view' (brief section 14)."""
import logging

import pytest

from quantagents.agents.schemas import MemoBody, ResearchMemo
from quantagents.config import CONFIG_DIR, load_config
from quantagents.llm.client import LLMClient
from tests.llm_fakes import GOOD_MEMO, FakeSDK, reply


@pytest.fixture
def cfg():
    return load_config(CONFIG_DIR / "pilot.yaml")


def call(c):
    return c.structured(node="memo", model="claude-haiku-5-5", system="s", user="u", schema=MemoBody,
                        max_tokens=800, effort="low")


def test_invalid_json_is_retried_then_succeeds(cfg):
    sdk = FakeSDK([reply("{not json"), reply(GOOD_MEMO)])
    res = call(LLMClient(cfg, "r", sdk=sdk))
    assert res.ok and res.attempts == 2 and res.api_calls == 2


@pytest.mark.parametrize("bad", [reply("{not json"), reply({"business_summary": "only one field"}),
                                 reply({**GOOD_MEMO, "outlook_3m": "to the moon"}),
                                 reply(GOOD_MEMO, stop_reason="max_tokens"),
                                 reply("", stop_reason="refusal")])
def test_two_failures_give_no_view_and_are_still_billed(cfg, bad, caplog):
    sdk = FakeSDK([bad, bad])
    c = LLMClient(cfg, "r", sdk=sdk)
    with caplog.at_level(logging.WARNING):
        res = call(c)
    assert not res.ok and res.parsed is None and res.api_calls == 2
    assert "no valid answer" in caplog.text
    assert c.ledger.spent(run_id="r") > 0
    memo = ResearchMemo.no_view("AAPL", "2015-03-02", "claude-haiku-5-5", "memo_v1", res.error)
    assert (memo.ok, memo.outlook_3m, memo.conviction) == (False, "neutral", "low")


def test_rerun_after_a_failure_is_free(cfg):
    call(LLMClient(cfg, "r", sdk=FakeSDK([reply("{bad"), reply(GOOD_MEMO)])))
    sdk = FakeSDK([])
    res = call(LLMClient(cfg, "r", sdk=sdk))
    assert res.ok and res.cache_hits == 2 and sdk.messages.calls == []
