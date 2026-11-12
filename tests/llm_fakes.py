"""Test double for the Anthropic SDK client: records every request, returns scripted replies."""
from __future__ import annotations

import json
from types import SimpleNamespace


def reply(text: str | dict, stop_reason: str = "end_turn", input_tokens: int = 1000, output_tokens: int = 200,
          cache_read: int = 0, cache_write: int = 0, model: str = "claude-haiku-5-5"):
    if isinstance(text, dict):
        text = json.dumps(text)
    return SimpleNamespace(id="msg_test", model=model, stop_reason=stop_reason, stop_details=None,
                           content=[SimpleNamespace(type="text", text=text)],
                           usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                                                 cache_read_input_tokens=cache_read,
                                                 cache_creation_input_tokens=cache_write))


class FakeMessages:
    def __init__(self, replies, raise_exc: Exception | None = None):
        self.replies = list(replies)
        self.calls: list[dict] = []
        self.raise_exc = raise_exc

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_exc is not None:
            raise self.raise_exc
        if not self.replies:
            raise AssertionError("no scripted reply left")
        return self.replies.pop(0)


class FakeSDK:
    def __init__(self, replies=(), raise_exc: Exception | None = None):
        self.messages = FakeMessages(replies, raise_exc)


GOOD_MEMO = {"business_summary": "Makes phones.", "price_and_technicals": "Up 9% in a month.",
             "fundamentals": "Revenue $74.60B.", "news": "No major news.", "positives": ["strong margins"],
             "risks": ["high expectations"], "outlook_3m": "slightly_positive", "conviction": "medium",
             "data_gaps": []}
