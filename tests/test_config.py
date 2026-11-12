import pytest
import yaml

from quantagents.config import CONFIG_DIR, load_config, load_key_budgets


def write(tmp_path, data, name="c.yaml"):
    base = yaml.safe_load(open(CONFIG_DIR / "base.yaml", encoding="utf-8"))
    def merge(a, b):
        for k, v in b.items():
            a[k] = merge(a.get(k, {}), v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
        return a
    p = tmp_path / name
    p.write_text(yaml.safe_dump(merge(base, data)), encoding="utf-8")
    return p


def test_base_and_pilot_load():
    base = load_config(CONFIG_DIR / "base.yaml")
    pilot = load_config(CONFIG_DIR / "pilot.yaml")
    assert base.cost_bps == 10 and base.constraints.sector_band_pp == 2.0
    assert base.models.active.memo == "claude-haiku-5-5"
    assert pilot.universe.tickers == ["AAPL", "MSFT", "NVDA", "AMZN"]
    assert pilot.universe.add_removed_member
    assert pilot.dates.end.isoformat() == "2015-03-31"
    # pilot inherits everything else from base
    assert pilot.views.rating_to_excess_return == base.views.rating_to_excess_return


def test_paper_tier_uses_sonnet_committee(tmp_path):
    cfg = load_config(write(tmp_path, {"models": {"tier": "paper"}}))
    assert cfg.models.active.committee == "claude-sonnet-5-5"


@pytest.mark.parametrize("override, msg", [
    ({"constraints": {"max_multiple_of_index": 0.5}}, "multiples"),
    ({"constraints": {"min_multiple_of_index": 1.5, "max_multiple_of_index": 1.2}}, "max_multiple"),
    ({"models": {"tier": "turbo"}}, "tier"),
    ({"models": {"tiers": {"dev": {"memo": "claude-haiku-4-5", "committee": "claude-haiku-5-5"}}}}, "not allowed"),
    ({"dates": {"start": "2024-01-01"}}, "dates"),
    ({"views": {"rating_to_excess_return": {"strong_sell": 0.06, "sell": -0.03, "hold": 0, "buy": 0.03, "strong_buy": -0.06}}}, "increasing"),
    ({"budget": {"key_label": "nobody"}}, "key_label"),
    ({"budget": {"stage": "stage9"}}, "stage"),
    ({"budget": {"key_label": "personal", "stage": "proto20"}}, "is for key_label 'student'"),
    ({"unexpected_field": 1}, "unexpected_field"),
])
def test_bad_values_rejected(tmp_path, override, msg):
    with pytest.raises(Exception, match=msg):
        load_config(write(tmp_path, override))


@pytest.mark.parametrize("key", ["temperature", "top_p", "top_k"])
def test_sampling_params_rejected(tmp_path, key):
    with pytest.raises(ValueError, match="sampling parameters"):
        load_config(write(tmp_path, {"models": {"memo": {key: 0.0}}}))


def test_key_budgets():
    b = load_key_budgets()
    assert b["personal"].budget_usd == 3.0
    assert b["personal"].stop_at_usd == pytest.approx(2.40)
    assert b["student"].budget_usd == 150.0
    assert b["student"].stop_at_usd <= 150.0


def test_funding_stages():
    from quantagents.config import PROJECT_CAP_USD, load_stage_budgets
    st = load_stage_budgets()
    assert st["stage0"].key_label == "personal" and st["stage0"].stop_at_usd == pytest.approx(2.40)
    assert st["stage2"].budget_usd == 90
    assert sum(s.budget_usd for s in st.values() if s.key_label == "student") <= PROJECT_CAP_USD


def test_proto20_mvp_budget():
    """D46: $40 on the student key, automatic stop at $32; stage1 removed; contingency $20."""
    from quantagents.config import load_stage_budgets
    st = load_stage_budgets()
    p = st["proto20"]
    assert p.key_label == "student" and p.budget_usd == 40.0 and p.stop_at_usd == pytest.approx(32.0)
    assert "stage1" not in st and st["contingency"].budget_usd == 20.0
    assert sum(s.budget_usd for s in st.values() if s.key_label == "student") == pytest.approx(150.0)


def test_base_and_pilot_run_on_the_proto20_budget():
    for name in ("base.yaml", "pilot.yaml"):
        cfg = load_config(CONFIG_DIR / name)
        assert (cfg.budget.key_label, cfg.budget.stage) == ("student", "proto20")


def test_stage_total_above_cap_rejected(tmp_path):
    from quantagents.config import load_stage_budgets
    f = tmp_path / "stages.yaml"
    f.write_text("a: {key_label: student, budget_usd: 100, stop_fraction: 0.8}\n"
                 "b: {key_label: student, budget_usd: 60, stop_fraction: 0.8}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cap"):
        load_stage_budgets(f)


def test_student_stage_config_loads(tmp_path):
    cfg = load_config(write(tmp_path, {"budget": {"key_label": "student", "stage": "stage2"}}))
    assert cfg.budget.stage == "stage2"
