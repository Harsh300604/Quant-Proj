"""Response cache: hits cost nothing; any prompt change misses; a key swap still hits."""
from dataclasses import replace

import pytest

from quantagents.agents.schemas import MemoBody
from quantagents.config import CONFIG_DIR, load_config
from quantagents.llm.client import LLMClient
from quantagents.llm.ledger import Limits
from tests.llm_fakes import GOOD_MEMO, FakeSDK, reply


@pytest.fixture
def cfg():
    return load_config(CONFIG_DIR / "pilot.yaml")


def call(client, **kw):
    args = dict(node="memo", model="claude-haiku-5-5", system="sys", user="data", schema=MemoBody,
                max_tokens=800, effort="low")
    args.update(kw)
    return client.structured(**args)


def test_same_request_hits_without_calling_the_api(cfg):
    sdk = FakeSDK([reply(GOOD_MEMO)])
    c = LLMClient(cfg, "r1", sdk=sdk)
    a, b = call(c), call(c)
    assert len(sdk.messages.calls) == 1
    assert (a.api_calls, b.api_calls, b.cache_hits, b.usd) == (1, 0, 1, 0.0)
    assert a.parsed == b.parsed


@pytest.mark.parametrize("change", [{"system": "other"}, {"user": "other data"}, {"effort": "medium"},
                                    {"max_tokens": 900}, {"replicate": 1}, {"model": "claude-sonnet-5-5"}])
def test_any_change_is_a_miss(cfg, change):
    sdk = FakeSDK([reply(GOOD_MEMO), reply(GOOD_MEMO)])
    c = LLMClient(cfg, "r1", sdk=sdk)
    call(c)
    call(c, **change)
    assert len(sdk.messages.calls) == 2


def test_schema_change_is_a_miss(cfg):
    from pydantic import BaseModel

    class Other(BaseModel):
        x: str
    sdk = FakeSDK([reply(GOOD_MEMO), reply({"x": "y"})])
    c = LLMClient(cfg, "r1", sdk=sdk)
    call(c)
    call(c, schema=Other)
    assert len(sdk.messages.calls) == 2


def test_key_swap_and_key_label_change_still_hit(cfg):
    call(LLMClient(cfg, "r1", sdk=FakeSDK([reply(GOOD_MEMO)])))
    other_key = FakeSDK([])                                  # a different SDK client = a different API key
    lim = replace(Limits.from_config(cfg), key_label="personal", stage="stage0", key_stop=2.4, stage_stop=2.4)
    res = call(LLMClient(cfg, "r2", sdk=other_key, limits=lim))
    assert res.cache_hits == 1 and other_key.messages.calls == []
