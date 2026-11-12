"""Dave's risk numbers (D33): the benchmark scores beta 1, liquidity 1, sector 0, R = 0.75;
active sector bets show up; everything is point-in-time."""
import pandas as pd
import pytest

from quantagents.config import RiskScore
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway
from quantagents.eval.benchmarks import renormalise
from quantagents.portfolio.risk_stats import portfolio_stats, stock_table

AS_OF = cal.as_of_for(pd.Timestamp("2015-06-01"))
IDS = ["AAA", "BBB", "GOOGL", "OLD"]


def tables(db):
    gw = Gateway(db, freeze_at=AS_OF)
    try:
        bench = renormalise(gw.get_index_weights(AS_OF).set_index("company_id")["weight"], IDS)
        sectors = gw.get_universe(AS_OF).set_index("company_id")["sector"].reindex(bench.index)
        return (bench, sectors) + stock_table(gw, list(bench.index), AS_OF, bench)
    finally:
        gw.close()


def test_benchmark_scores_the_reference_values(synthetic_db):
    bench, sectors, table, year = tables(synthetic_db[1])
    s = portfolio_stats(bench, bench, sectors, table, year, 2.0, RiskScore())
    assert s["beta"] == pytest.approx(1.0, abs=1e-6) and s["liquidity_ratio"] == pytest.approx(1.0)
    assert s["max_active_sector"] == pytest.approx(0.0, abs=1e-12) and s["risk_score"] == pytest.approx(0.75, abs=1e-6)


def test_sector_bet_and_empty_portfolio(synthetic_db):
    bench, sectors, table, year = tables(synthetic_db[1])
    tilted = bench.copy()
    hc = sectors[sectors == "Health Care"].index
    tilted[hc] *= 1.2
    s = portfolio_stats(tilted, bench, sectors, table, year, 2.0, RiskScore())
    assert s["max_active_sector_name"] == "Health Care" and s["max_active_sector_signed"] > 0
    assert s["risk_score"] > 0.75
    assert portfolio_stats(pd.Series(dtype=float), bench, sectors, table, year, 2.0, RiskScore()) == {}


def test_stock_table_is_point_in_time(synthetic_db):
    a, b = tables(synthetic_db[1]), tables(synthetic_db[2](AS_OF))
    pd.testing.assert_frame_equal(a[2], b[2])
