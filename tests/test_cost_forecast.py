"""Forecast maths from a synthetic ledger: per-call profile -> any run size, model swap, +-20%."""
import pandas as pd
import pytest

from quantagents.eval.cost_forecast import cache_read_share, profile, project
from quantagents.llm.pricing import cost_usd, load_pricing


def ledger():
    rows = []
    for reb in range(2):
        for c in range(4):
            rows.append(dict(run_id="m", node="memo", model="claude-haiku-5-5", cache_hit=0, input_tokens=2000,
                             cache_creation_input_tokens=0, cache_read_input_tokens=1000, output_tokens=800))
        rows.append(dict(run_id="m", node="emily", model="claude-haiku-5-5", cache_hit=0, input_tokens=500,
                         cache_creation_input_tokens=10000, cache_read_input_tokens=0, output_tokens=1500))
        for n in ("bob", "dave", "otto_draft", "otto_final"):
            rows.append(dict(run_id="m", node=n, model="claude-haiku-5-5", cache_hit=0, input_tokens=3000,
                             cache_creation_input_tokens=0, cache_read_input_tokens=10000, output_tokens=1500))
    rows.append(dict(run_id="m", node="memo", model="claude-haiku-5-5", cache_hit=1, input_tokens=9e9,
                     cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=9e9))  # hits ignored
    rows.append(dict(run_id="other", node="memo", model="claude-haiku-5-5", cache_hit=0, input_tokens=9e9,
                     cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=9e9))
    return pd.DataFrame(rows)


def test_profile_and_projection():
    prof = profile(ledger(), "m", rebalances=2, companies=4)
    assert prof.loc["memo", "calls_per_rebalance"] == 1.0 and prof.loc["emily", "calls_per_rebalance"] == 1.0
    assert prof.loc["memo", "input_tokens"] == 2000
    prices = load_pricing()
    p = project(prof, rebalances=36, companies=20, memo_model="claude-haiku-5-5",
                committee_model="claude-sonnet-5-5", prices=prices)
    memo = cost_usd("claude-haiku-5-5", {"input_tokens": 2000, "cache_read_input_tokens": 1000, "output_tokens": 800},
                    prices) * 20 * 36
    emily = cost_usd("claude-sonnet-5-5", {"input_tokens": 500, "cache_creation_input_tokens": 10000,
                                           "output_tokens": 1500}, prices) * 36
    rest = cost_usd("claude-sonnet-5-5", {"input_tokens": 3000, "cache_read_input_tokens": 10000,
                                          "output_tokens": 1500}, prices) * 4 * 36
    assert p.memo_usd == pytest.approx(memo) and p.committee_usd == pytest.approx(emily + rest)
    assert p.low == pytest.approx(0.8 * p.usd) and p.high == pytest.approx(1.2 * p.usd)


def test_bigger_universe_adds_one_liners_and_memos():
    prof = profile(ledger(), "m", rebalances=2, companies=4)
    prices = load_pricing()
    small = project(prof, rebalances=1, companies=20, memo_model="claude-haiku-5-5",
                    committee_model="claude-sonnet-5-5", prices=prices)
    big = project(prof, rebalances=1, companies=100, memo_model="claude-haiku-5-5",
                  committee_model="claude-sonnet-5-5", prices=prices)
    assert big.memo_usd == pytest.approx(5 * small.memo_usd) and big.committee_usd > small.committee_usd


def test_cache_share():
    prof = profile(ledger(), "m", rebalances=2, companies=4)
    # committee: (10000 written + 4 x 10000 read) / (5 x total input per call)
    expected = 40000 / (500 + 10000 + 4 * (3000 + 10000))
    assert cache_read_share(prof) == pytest.approx(expected)
    with pytest.raises(ValueError):
        profile(ledger(), "nope", 1, 1)
