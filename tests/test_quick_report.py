"""The quick report builds from stored files only (sockets are blocked in every test)."""
from quantagents.engine.backtest import run
from quantagents.eval.quick_report import build
from tests.graph_helpers import graph_config


def test_quick_report_from_a_stored_run(synthetic_db, tmp_path, monkeypatch):
    monkeypatch.setenv("QA_STORE_ROOT", str(synthetic_db[0]))
    cfg = graph_config(synthetic_db[0], tmp_path)
    run(cfg, "hold_benchmark", "qr_hold", fresh=True, quiet=True)
    page = build("qr_hold", cfg.source_file)
    assert page.startswith("<!doctype html>") and "<svg" in page and "QQQ (reference)" in page
    assert "Information ratio" in page and "Red flags: 0 hits" in page
