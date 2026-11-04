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
