"""Universe rules (config ``universe.mode``; D39, D45)."""
from types import SimpleNamespace

import pandas as pd
import pytest

from quantagents.config import CONFIG_DIR, Universe, load_config
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway, LookAheadError
from quantagents.data.universe import resolve_universe, top_n_by_cap

CHOSEN = "2015-03-02"


@pytest.fixture(scope="module")
def gw(synthetic_db):
    g = Gateway(synthetic_db[1])
    yield g
    g.close()


def test_top_n_matches_market_caps_computed_by_hand(gw):
    """All synthetic companies have 500m shares, so the ranking is the ranking of actual prices."""
    t = cal.close_utc(CHOSEN)
    members = gw.get_universe(t)["company_id"].tolist()
    px = gw.get_prices(members, t, lookback_days=3).sort_values("date").groupby("company_id")["raw_close"].last()
    expected = px.sort_values(ascending=False).index[:3].tolist()
    got = top_n_by_cap(gw, t, 3)
    assert got["company_id"].tolist() == expected and got["rank"].tolist() == [1, 2, 3]


def test_top_n_is_deterministic(gw):
    t = cal.close_utc(CHOSEN)
    assert top_n_by_cap(gw, t, 3).equals(top_n_by_cap(gw, t, 3))


def test_ties_broken_by_company_id():
    class Fake:
        def get_universe(self, as_of):
            return pd.DataFrame({"company_id": ["ZZZ", "AAA", "MMM", "BIG"], "name": "", "sector": "",
                                 "has_prices": True})

        def get_index_weights(self, as_of):
            return pd.DataFrame({"company_id": ["BIG", "ZZZ", "MMM", "AAA"],
                                 "weight": [0.4, 0.2, 0.2, 0.2], "mcap": [4.0, 2, 2, 2]})
    out = top_n_by_cap(Fake(), cal.close_utc(CHOSEN), 3)
    assert out["company_id"].tolist() == ["BIG", "AAA", "MMM"]


def test_members_without_prices_are_never_chosen():
    class Fake:
        def get_universe(self, as_of):
            return pd.DataFrame({"company_id": ["A", "B"], "name": "", "sector": "", "has_prices": [False, True]})

        def get_index_weights(self, as_of):
            return pd.DataFrame({"company_id": ["A", "B"], "weight": [0.9, 0.1], "mcap": [9.0, 1]})
    assert top_n_by_cap(Fake(), cal.close_utc(CHOSEN), 1)["company_id"].tolist() == ["B"]


def test_later_member_never_chosen_and_rebuild_at_chosen_date_gives_same_list(gw, synthetic_db):
    """NEW joins on 2015-06-01: never in a list chosen on 2015-03-02, and a store rebuilt as if
    today were the chosen close (all later data removed) gives exactly the same list."""
    t = cal.close_utc(CHOSEN)
    full = top_n_by_cap(gw, t, 4)
    assert "NEW" not in full["company_id"].tolist()
    cut = Gateway(synthetic_db[2](t))
    try:
        pd.testing.assert_frame_equal(full, top_n_by_cap(cut, t, 4))
    finally:
        cut.close()


def test_keep_fixed_holds_the_list_through_the_period(gw):
    cfg = SimpleNamespace(universe=Universe(mode="top_n_by_cap", top_n=4, chosen_at=CHOSEN, keep_fixed=True))
    res = resolve_universe(cfg, gw)
    first = res.at(gw, cal.close_utc(CHOSEN))
    assert res.at(gw, cal.close_utc("2015-09-01")) == first          # OLD left the index; list unchanged
    assert "OLD" in first


def test_not_fixed_reranks_each_date(gw):
    cfg = SimpleNamespace(universe=Universe(mode="top_n_by_cap", top_n=4, chosen_at=CHOSEN, keep_fixed=False))
    res = resolve_universe(cfg, gw)
    later = res.at(gw, cal.close_utc("2015-09-01"))
    assert "OLD" not in later and "NEW" in later


def test_decision_before_the_choice_date_is_a_look_ahead(gw):
    cfg = SimpleNamespace(universe=Universe(mode="top_n_by_cap", top_n=2, chosen_at=CHOSEN))
    res = resolve_universe(cfg, gw)
    with pytest.raises(LookAheadError):
        res.at(gw, cal.close_utc("2015-02-02"))


def test_universe_csv_written(gw, tmp_path):
    cfg = SimpleNamespace(universe=Universe(mode="top_n_by_cap", top_n=3, chosen_at=CHOSEN))
    resolve_universe(cfg, gw, run_dir=tmp_path / "run")
    df = pd.read_csv(tmp_path / "run" / "universe.csv")
    assert list(df.columns[:3]) == ["rank", "chosen_at", "company_id"] and len(df) == 3


def test_modes_from_config():
    assert load_config(CONFIG_DIR / "base.yaml").universe.mode == "index_members"
    pilot = load_config(CONFIG_DIR / "pilot.yaml").universe
    assert pilot.mode == "tickers" and pilot.tickers == ["AAPL", "MSFT", "NVDA", "AMZN"]
    for name, end in (("proto20.yaml", "2023-12-31"), ("proto20_2021.yaml", "2021-12-31")):
        c = load_config(CONFIG_DIR / name)
        assert (c.universe.mode, c.universe.top_n, str(c.universe.chosen_at)) == ("top_n_by_cap", 20, "2021-01-04")
        assert c.benchmark.mode == "custom_cap_index" and str(c.dates.end) == end
        assert (c.selection.max_views, c.selection.max_per_sector) == (20, None)
        assert (c.budget.key_label, c.budget.stage) == ("student", "proto20")
    assert load_config(CONFIG_DIR / "base.yaml").benchmark.mode == "index"


def test_freeze_script_writes_and_checks(synthetic_db, tmp_path, monkeypatch, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("p20", CONFIG_DIR.parent / "scripts" / "proto20_universe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setenv("QA_STORE_ROOT", str(synthetic_db[0]))
    cfg = tmp_path / "p.yaml"
    cfg.write_text(f"extends: {(CONFIG_DIR / 'proto20.yaml').as_posix()}\n"
                   "dates: {warmup_start: 2014-01-01, start: 2015-03-01, end: 2015-12-31}\n"
                   "universe: {mode: top_n_by_cap, top_n: 3, chosen_at: 2015-03-02, keep_fixed: true}\n",
                   encoding="utf-8")
    frozen = tmp_path / "frozen.csv"
    assert mod.main(["--config", str(cfg), "--frozen", str(frozen)]) == 0
    assert len(pd.read_csv(frozen, comment="#")) == 3
    assert mod.main(["--config", str(cfg), "--frozen", str(frozen), "--check"]) == 0
    assert "OK: the live rule matches" in capsys.readouterr().out
    df = pd.read_csv(frozen, comment="#")
    df.loc[0, "company_id"] = "XXX"
    df.to_csv(frozen, index=False)
    assert mod.main(["--config", str(cfg), "--frozen", str(frozen), "--check", "--no-benchmark"]) == 1


@pytest.mark.parametrize("kwargs, msg", [
    ({"mode": "top_n_by_cap"}, "needs universe.top_n"),
    ({"mode": "tickers"}, "needs universe.tickers"),
    ({"mode": "index_members", "tickers": ["AAPL"]}, "only used with mode"),
])
def test_bad_universe_rejected(kwargs, msg):
    with pytest.raises(Exception, match=msg):
        Universe(**kwargs)
