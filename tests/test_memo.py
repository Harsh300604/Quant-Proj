"""Research memo node on the synthetic store (SDK faked)."""
import pandas as pd
import pytest

from quantagents.agents.memo import memo_input, money, write_memo
from quantagents.config import CONFIG_DIR, load_config
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway, LookAheadError
from quantagents.llm.client import LLMClient
from tests.llm_fakes import GOOD_MEMO, FakeSDK, reply

AS_OF = cal.close_utc("2015-03-02")


@pytest.fixture(scope="module")
def gw(synthetic_db):
    g = Gateway(synthetic_db[1], freeze_at=AS_OF)
    yield g
    g.close()


def test_memo_input_has_prices_fundamentals_and_news(gw):
    text = memo_input(gw, "AAA", AS_OF)
    assert "Decision date: 2015-03-02" in text and "Return: 1 month" in text
    assert "Latest quarter" in text and "NEWS" in text
    assert "AAA news 1" in text            # 15:59 ET on 2 March: before the close
    assert "AAA news 2" not in text        # 16:01 ET: after the close


def test_memo_input_is_point_in_time(gw, synthetic_db):
    """The input text is identical when the store is rebuilt as if today were the decision time."""
    cut = Gateway(synthetic_db[2](AS_OF))
    try:
        assert memo_input(gw, "AAA", AS_OF) == memo_input(cut, "AAA", AS_OF)
    finally:
        cut.close()


def test_frozen_gateway_blocks_later_reads(gw):
    with pytest.raises(LookAheadError):
        memo_input(gw, "AAA", cal.close_utc("2015-04-01"))


def test_write_memo_ok_and_no_view(gw, synthetic_db, monkeypatch):
    cfg = load_config(CONFIG_DIR / "pilot.yaml")
    m, _ = write_memo(LLMClient(cfg, "t", sdk=FakeSDK([reply(GOOD_MEMO)])), cfg, gw, "AAA", AS_OF)
    assert m.ok and m.outlook_3m == "slightly_positive" and m.company_id == "AAA" and m.as_of == "2015-03-02"
    bad = FakeSDK([reply("{x"), reply("{y")])
    m2, _ = write_memo(LLMClient(cfg, "t2", sdk=bad), cfg, gw, "BBB", AS_OF)
    assert not m2.ok and m2.outlook_3m == "neutral"


def test_money_shows_foreign_currency():
    assert money(30.14e9, "CNY") == "CNY 30.14B" and money(-6.97e9) == "-$6.97B"
