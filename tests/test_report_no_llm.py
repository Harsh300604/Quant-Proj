"""The results report runs from stored files only (sockets are blocked in every test) and refuses
to compare runs of different periods."""
import pytest

from quantagents.engine.backtest import run
from quantagents.eval.report import build
from tests.graph_helpers import graph_config


def test_report_from_stored_runs(synthetic_db, tmp_path, monkeypatch):
    monkeypatch.setenv("QA_STORE_ROOT", str(synthetic_db[0]))
    cfg = graph_config(synthetic_db[0], tmp_path)
    run(cfg, "hold_benchmark", "rep_hold", fresh=True, quiet=True)
    run(cfg, "random", "rep_rnd", seed=2, fresh=True, quiet=True)
    out = build(["rep_hold", "rep_rnd"], "rep_test", cfg.source_file)
    md = (out / "results.md").read_text(encoding="utf-8")
    assert "rep_hold" in md and "rep_rnd" in md and "QQQ (reference)" in md and "Read with care" in md
    assert (out / "results.csv").exists() and "<svg" in (out / "growth_of_1.html").read_text(encoding="utf-8")
    (tmp_path / "s").mkdir()
    short = graph_config(synthetic_db[0], tmp_path / "s", end="2015-04-30")
    run(short, "hold_benchmark", "rep_short", fresh=True, quiet=True)
    with pytest.raises(ValueError, match="different periods"):
        build(["rep_hold", "rep_short"], "rep_bad", cfg.source_file)
