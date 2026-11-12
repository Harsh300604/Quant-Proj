"""View accuracy maths on a hand-made table."""
import pandas as pd
import pytest

from quantagents.eval.view_accuracy import accuracy


def frame(labels, mults, excess, made):
    return pd.DataFrame({"made": made, "company_id": [f"C{i}" for i in range(len(excess))], "multiplier": mults,
                         "label": labels, "excess": excess})


def test_baseline_buckets_hits_and_rank_ic():
    df = frame([""] * 6, [1.5, 1.0, 0.5, 1.5, 1.0, 0.5], [0.05, 0.0, -0.04, -0.02, 0.01, -0.03], ["d1"] * 3 + ["d2"] * 3)
    t, ic, n = accuracy(df)
    assert list(t.index) == ["x0.50", "x1.00", "x1.50"]
    assert t.loc["x0.50", "hit_rate"] == 1.0 and t.loc["x1.50", "hit_rate"] == 0.5
    assert t.loc["x1.50", "avg_excess"] == pytest.approx(0.015) and pd.isna(t.loc["x1.00", "hit_rate"])
    # d1: ranks agree exactly (1.0); d2: score ranks 3,2,1 vs excess ranks 2,3,1 -> 1 - 6*2/24 = 0.5
    assert n == 2 and ic == pytest.approx((1.0 + 0.5) / 2)


def test_enhanced_uses_ratings_and_confidence():
    df = frame(["buy (0.5)", "hold (0.0)", "strong_sell (1.0)"], [1.25, 1.0, 0.5], [0.02, 0.0, -0.05], ["d"] * 3)
    t, ic, _ = accuracy(df)
    assert list(t.index) == ["strong_sell", "hold", "buy"] and ic == pytest.approx(1.0)
