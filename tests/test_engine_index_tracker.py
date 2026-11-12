"""Holding the benchmark tracks the benchmark; resume gives an identical run; constraints hold."""
import json

import numpy as np
import pandas as pd
import pytest

from quantagents.config import CONFIG_DIR, load_config
from quantagents.engine.accounting import Book, simulate
from quantagents.engine.backtest import StopRequested, run
from quantagents.eval.benchmarks import cap_index_returns


@pytest.fixture
def cfg(synthetic_db, tmp_path, monkeypatch):
    monkeypatch.setenv("QA_STORE_ROOT", str(synthetic_db[0]))
    f = tmp_path / "engine.yaml"
    f.write_text(f"extends: {(CONFIG_DIR / 'pilot.yaml').as_posix()}\nrun_id: engine_test\n"
                 "dates: {warmup_start: 2014-01-01, start: 2015-01-01, end: 2015-08-31}\n"
                 "universe: {mode: tickers, tickers: [AAA, BBB, GOOGL, OLD], add_removed_member: false}\n"
                 "benchmark: {mode: custom_cap_index}\n", encoding="utf-8")
    return load_config(f)


def test_exact_match_when_shares_constant_no_dividends_no_gap():
    """Buy-and-hold at cap weights = the cap index, to 1e-8, when nothing but prices moves."""
    rng = np.random.default_rng(7)
    days = pd.bdate_range("2021-01-04", periods=60)
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.02, (60, 3)), axis=0)), index=days, columns=list("XYZ"))
    open_ = close.shift(1).fillna(close.iloc[0])                         # open = previous close
    shares = pd.Series({"X": 3.0, "Y": 1.0, "Z": 2.0})
    caps = close * shares
    weights = caps.div(caps.sum(axis=1), axis=0)
    idx = cap_index_returns(weights, close.pct_change())
    nav, _, _ = simulate(days[1:], open_, close, pd.DataFrame(0.0, index=days, columns=close.columns),
                         {days[1]: weights.iloc[0].to_dict()}, cost_bps=0.0, book=Book(cash=1.0))
    np.testing.assert_allclose(nav.pct_change().dropna().to_numpy(), idx.iloc[1:].to_numpy(), atol=1e-8)
    assert nav.iloc[0] - 1 == pytest.approx(idx.iloc[0], abs=1e-8)


def test_hold_benchmark_tracks_the_custom_index(cfg):
    s = run(cfg, "hold_benchmark", "track_hold", fresh=True, quiet=True)
    assert s["rebalances"] == 8 and s["first_turnover"] == pytest.approx(1.0)
    assert s["tracking_error"] < 0.01                     # synthetic dividends and share changes: small drift
    assert abs(s["total_return"] - s["benchmark_total_return"]) < 0.01
    # 10 bps on the first trade, plus small trades (OLD leaves the index, share-count changes)
    assert 0.001 <= s["total_cost"] < 0.002


def test_company_that_leaves_is_sold_and_dropped(cfg, synthetic_db):
    run(cfg, "hold_benchmark", "track_leave", fresh=True, quiet=True)
    w = pd.read_csv(synthetic_db[0] / "runs" / "track_leave" / "weights.csv")
    assert "OLD" in set(w[w["rebalance"] == "2015-05-01"]["company_id"])
    assert "OLD" not in set(w[w["rebalance"] == "2015-07-01"]["company_id"])


def test_random_tilts_respect_constraints_and_are_deterministic(cfg, synthetic_db):
    a = run(cfg, "random", "rnd_a", seed=3, fresh=True, quiet=True)
    b = run(cfg, "random", "rnd_b", seed=3, fresh=True, quiet=True)
    assert a["total_return"] == b["total_return"] and a["avg_turnover"] > 0.05
    w = pd.read_csv(synthetic_db[0] / "runs" / "rnd_a" / "weights.csv")
    ratio = w["weight"] / w["benchmark"]
    assert ratio.between(-1e-9, 2 + 1e-9).all()
    assert w.groupby("rebalance")["weight"].sum().round(9).eq(1).all()


def test_resume_after_a_stop_gives_an_identical_nav(cfg, synthetic_db):
    clean = run(cfg, "random", "resume_clean", seed=1, fresh=True, quiet=True)
    with pytest.raises(StopRequested):
        run(cfg, "random", "resume_cut", seed=1, fresh=True, stop_after=3, quiet=True)
    ck = json.loads((synthetic_db[0] / "runs" / "resume_cut" / "checkpoint.json").read_text())
    assert ck["next"] == 3
    resumed = run(cfg, "random", "resume_cut", seed=1, quiet=True)
    a = pd.read_csv(synthetic_db[0] / "runs" / "resume_clean" / "nav.csv")
    b = pd.read_csv(synthetic_db[0] / "runs" / "resume_cut" / "nav.csv")
    pd.testing.assert_frame_equal(a, b)
    assert clean["total_return"] == resumed["total_return"]


def test_checkpoint_from_another_strategy_is_not_reused(cfg, synthetic_db, capsys):
    with pytest.raises(StopRequested):
        run(cfg, "random", "resume_other", seed=1, fresh=True, stop_after=2, quiet=True)
    run(cfg, "hold_benchmark", "resume_other")
    assert "different config or strategy" in capsys.readouterr().out
