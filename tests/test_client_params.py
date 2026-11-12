"""Requests built by llm/client.py (brief section 8 API rules)."""
import pytest
from pydantic import BaseModel

from quantagents.agents.schemas import MemoBody
from quantagents.config import CONFIG_DIR, load_config
from quantagents.llm.client import ALLOWED_REQUEST_KEYS, LLMClient, _assert_allowed, build_request
from tests.llm_fakes import GOOD_MEMO, FakeSDK, reply


def req(model="claude-haiku-5-5", effort="low", off=True, schema=MemoBody):
    return build_request(model=model, system="sys", user="data", schema=schema, max_tokens=1500,
                         effort=effort, thinking_off=off)


def all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k != "schema":
                yield k
                yield from all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from all_keys(v)


@pytest.mark.parametrize("model", ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"])
def test_no_sampling_params_no_tool_choice_and_max_tokens_set(model):
    r = req(model=model)
    assert set(r) <= ALLOWED_REQUEST_KEYS and r["max_tokens"] == 1500
    assert not {"temperature", "top_p", "top_k", "tool_choice"} & set(all_keys(r))


def test_request_actually_sent_is_the_allow_listed_one():
    cfg = load_config(CONFIG_DIR / "pilot.yaml")
    sdk = FakeSDK([reply(GOOD_MEMO)])
    LLMClient(cfg, "t", sdk=sdk).structured(node="memo", model="claude-haiku-5-5", system="s", user="u",
                                            schema=MemoBody, max_tokens=800, effort="low")
    sent = sdk.messages.calls[0]
    assert set(sent) <= ALLOWED_REQUEST_KEYS
    assert sent["output_config"]["format"]["type"] == "json_schema" and sent["output_config"]["effort"] == "low"
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_thinking_off_maps_to_what_each_model_accepts():
    assert req("claude-sonnet-5-5", "medium")["thinking"] == {"type": "between_tools"}
    assert req("claude-haiku-5-5")["thinking"] == {"type": "disabled"}
    assert "thinking" not in req("claude-opus-5-5")          # cannot be disabled on Opus 5.5
    assert "thinking" not in req("claude-sonnet-5-5", off=False)


def test_between_tools_only_at_high_effort_or_below():
    with pytest.raises(ValueError, match="between_tools"):
        req("claude-sonnet-5-5", "xhigh")


@pytest.mark.parametrize("model", ["claude-haiku-4-5", "claude-sonnet-4-6", "gpt-4"])
def test_only_allowed_models(model):
    with pytest.raises(ValueError, match="not allowed"):
        req(model=model)


@pytest.mark.parametrize("extra", [{"temperature": 0.0}, {"top_p": 0.9}, {"top_k": 5},
                                   {"tool_choice": {"type": "any"}}, {"metadata": {"x": 1}}])
def test_allow_list_rejects_anything_else(extra):
    with pytest.raises(ValueError):
        _assert_allowed({**req(), **extra})


def test_nested_sampling_param_rejected():
    r = req()
    r["output_config"] = {**r["output_config"], "temperature": 0.1}
    with pytest.raises(ValueError, match="temperature"):
        _assert_allowed(r)


def test_schema_may_contain_any_field_name():
    class S(BaseModel):
        temperature_view: str
        top_k_names: list[str]
    assert "output_config" in req(schema=S)
