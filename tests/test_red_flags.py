"""Each red flag fires on a planted bad case and stays silent on a clean run."""
import numpy as np
import pandas as pd

from quantagents.eval.red_flags import check_run, format_flags


def write_run(d, nav=None, bench=None, weights=None, turnover=(1.0, 0.2), checks=None):
    d.mkdir(parents=True, exist_ok=True)
    days = pd.bdate_range("2021-01-04", "2022-12-30")
    rng = np.random.default_rng(1)
    rb = pd.Series(rng.normal(0.0002, 0.012, len(days)), index=days)
    rb.iloc[5:60] -= 0.004                                          # a losing stretch: 2021 not all up
    b = bench if bench is not None else (1 + rb).cumprod()
    n = nav if nav is not None else b * (1 + rng.normal(0, 0.0005, len(days))).cumprod()
    pd.DataFrame({"date": days, "nav": n.to_numpy(), "benchmark_nav": b.to_numpy()}).to_csv(d / "nav.csv", index=False)
    w = weights if weights is not None else pd.DataFrame(
        {"rebalance": ["2021-01-04"] * 3, "company_id": ["A", "B", "C"], "weight": [0.5, 0.3, 0.2],
         "benchmark": [0.5, 0.3, 0.2], "sector": ["IT", "IT", "HC"]})
    w.to_csv(d / "weights.csv", index=False)
    pd.DataFrame({"date": ["2021-01-05", "2021-02-02"], "event": "rebalance", "turnover": list(turnover)}).to_csv(
        d / "rebalances.csv", index=False)
    (checks if checks is not None else pd.DataFrame(
        {"rebalance": ["2021-01-04"], "as_of": ["2021-01-04 21:00:00+00:00"],
         "max_read": ["2021-01-04 21:00:00+00:00"], "gateway_calls": [10]})).to_csv(d / "checks.csv", index=False)
    return d


def flags(d):
    return {f["flag"] for f in check_run(d, min_mult=0.0, max_mult=2.0, band_pp=2.0)}


def test_clean_run_is_silent(tmp_path):
    d = write_run(tmp_path / "clean")
    assert check_run(d, min_mult=0.0, max_mult=2.0, band_pp=2.0) == []
    assert format_flags([]) == "red flags: 0 hits"


def test_each_flag_fires(tmp_path):
    days = pd.bdate_range("2021-01-04", "2022-12-30")
    steady = pd.Series(1.002, index=days).cumprod()                  # Sharpe huge, no losing year
    assert {"sharpe_above_2", "no_losing_year"} <= flags(write_run(tmp_path / "a", nav=steady))
    jump = pd.Series(1.0, index=days)
    jump.iloc[100:] = 1.2
    assert "big_day_without_benchmark" in flags(write_run(tmp_path / "b", nav=jump, bench=pd.Series(1.0, index=days)))
    w = pd.DataFrame({"rebalance": ["r"] * 3, "company_id": ["A", "B", "C"], "weight": [0.45, 0.45, 0.2],
                      "benchmark": [0.2, 0.3, 0.5], "sector": ["IT", "IT", "HC"]})
    f = flags(write_run(tmp_path / "c", weights=w))
    assert {"weight_outside_range", "sector_outside_band", "weights_do_not_sum_to_1"} <= f
    assert "turnover_above_100pct" in flags(write_run(tmp_path / "d", turnover=(1.0, 1.3)))
    late = pd.DataFrame({"rebalance": ["2021-01-04"], "as_of": ["2021-01-04 21:00:00+00:00"],
                         "max_read": ["2021-01-05 21:00:00+00:00"], "gateway_calls": [3]})
    assert "read_after_decision_time" in flags(write_run(tmp_path / "e", checks=late))


def test_one_year_is_not_judged_on_losing_years(tmp_path):
    days = pd.bdate_range("2021-01-04", "2021-12-31")
    up = pd.Series(np.linspace(1, 1.3, len(days)), index=days)
    d = write_run(tmp_path / "f")
    pd.DataFrame({"date": days, "nav": up.to_numpy(), "benchmark_nav": up.to_numpy()}).to_csv(d / "nav.csv", index=False)
    assert "no_losing_year" not in flags(d)
