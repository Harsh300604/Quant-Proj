import duckdb
import pytest

from quantagents.data import quality


@pytest.fixture(scope="module")
def con(synthetic_db):
    c = duckdb.connect(str(synthetic_db[1]), read_only=True)
    yield c
    c.close()


def test_coverage_counts(con):
    cov = quality.coverage_by_month(con, "2015-01-01", "2015-12-31").set_index("rebalance")
    jan, jul = cov.iloc[0], cov.loc[[d for d in cov.index if d.month == 7][0]]
    assert jan["members"] == 4 and jan["with_prices"] == 4          # AAA, BBB, GOOGL, OLD
    assert jul["members"] == 4 and "OLD" not in jul["missing_prices"]


def test_ticker_reuse_flags_series_that_end_early(con):
    r = quality.ticker_reuse(con).set_index("company_id")
    # OLD left on 1 Jun 2015 but its prices run to 30 Jun -> fine; NEW joined 1 Jun with prices from March -> fine
    assert "OLD" not in r.index and "NEW" not in r.index


def test_index_vs_benchmark_runs(con):
    iv = quality.index_vs_benchmark(con, "QQQ")
    assert set(iv["year"]) == {2014, 2015} and (iv["tracking_error"] > 0).all()


def test_foreign_filers_listed(con):
    assert quality.foreign_filers(con).empty          # no 20-F filers in the synthetic world


def test_report_script_runs(synthetic_db, monkeypatch, capsys):
    import importlib.util
    from quantagents.config import REPO_ROOT
    monkeypatch.setenv("QA_STORE_ROOT", str(synthetic_db[0]))
    spec = importlib.util.spec_from_file_location("dr", REPO_ROOT / "scripts" / "data_report.py")
    dr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dr)
    assert dr.main(["--start", "2015-01-01", "--end", "2015-12-31"]) == 0
    out = capsys.readouterr().out
    assert "Coverage on the first rebalance" in out and "derived index vs QQQ" in out


def test_gateway_cli(synthetic_db, monkeypatch, capsys):
    from quantagents.data.gateway import main
    monkeypatch.setenv("QA_STORE_ROOT", str(synthetic_db[0]))
    assert main(["--as-of", "2015-03-01", "--show", "universe"]) == 0
    out = capsys.readouterr().out
    assert "close of 2015-03-02" in out and "weights sum to 1.000" in out
