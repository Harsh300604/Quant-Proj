"""The API key never appears in the ledger, the cache, logs or exceptions."""
import logging

import pytest

from quantagents.agents.schemas import MemoBody
from quantagents.config import CONFIG_DIR, load_config
from quantagents.env_secrets import Secrets
from quantagents.llm import client as client_mod
from quantagents.llm.client import LLMClient, LLMError
from tests.llm_fakes import GOOD_MEMO, FakeSDK, reply

FAKE_KEY = "sk-ant-api03-FAKEKEY-do-not-leak-1234567890"


@pytest.fixture
def cfg():
    return load_config(CONFIG_DIR / "pilot.yaml")


def call(c):
    return c.structured(node="memo", model="claude-haiku-5-5", system="s", user="u", schema=MemoBody,
                        max_tokens=800, effort="low")


def test_key_only_goes_to_the_sdk_constructor(cfg, monkeypatch, caplog):
    from pydantic import SecretStr
    import anthropic
    import quantagents.env_secrets as es
    got = {}
    monkeypatch.setattr(es, "load_secrets", lambda *a, **k: Secrets({"ANTHROPIC_API_KEY": SecretStr(FAKE_KEY)}))

    def fake_ctor(api_key=None, max_retries=None, **kw):
        got["api_key"] = api_key
        return FakeSDK([reply(GOOD_MEMO)])
    monkeypatch.setattr(anthropic, "Anthropic", fake_ctor)
    c = LLMClient(cfg, "r")
    with caplog.at_level(logging.DEBUG):
        assert call(c).ok
    assert got["api_key"] == FAKE_KEY
    for f in (c.paths.ledger, c.paths.response_cache):
        assert FAKE_KEY.encode() not in f.read_bytes()
    assert FAKE_KEY not in caplog.text and FAKE_KEY not in repr(c.__dict__)


def test_exception_text_never_carries_the_key(cfg):
    boom = RuntimeError(f"request failed with headers x-api-key: {FAKE_KEY}")
    c = LLMClient(cfg, "r", sdk=FakeSDK(raise_exc=boom))
    with pytest.raises(LLMError) as ei:
        call(c)
    assert FAKE_KEY not in str(ei.value) and ei.value.__cause__ is None and ei.value.__suppress_context__


def test_client_module_never_logs_requests():
    import inspect
    src = inspect.getsource(client_mod)
    assert "log.info(req" not in src and "print(" not in src
