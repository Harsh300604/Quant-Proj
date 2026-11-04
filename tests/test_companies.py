"""Company-level universe (D27): share classes and renames grouped, nothing else."""
import pandas as pd
import pytest

from quantagents.data.companies import (
    build_company_map, looks_like_share_classes, ticker_names, to_company_snapshots,
)


@pytest.mark.parametrize("a, b, ok", [("GOOG", "GOOGL", True), ("FOX", "FOXA", True), ("DISCA", "DISCK", True),
                                      ("LBTYA", "LBTYK", True), ("AAPL", "AMZN", False), ("LMCA", "BATRA", False),
                                      ("NWS", "NWSA", True), ("CSCO", "CSX", False), ("AMAT", "AMAT", False)])
def test_looks_like_share_classes(a, b, ok):
    assert looks_like_share_classes(a, b) is ok


def pairs(rows):
    return pd.DataFrame(rows, columns=["title", "ticker", "revisions"])


def test_company_map_groups_classes_and_renames_only():
    lp = pairs([("Alphabet Inc.", "GOOGL", 50), ("Alphabet Inc.", "GOOG", 50), ("Google", "GOOG", 10),
                ("Liberty Media", "LMCA", 5), ("Liberty Media", "BATRA", 3),        # tracking stock: not merged
                ("Facebook", "FB", 40), ("Meta Platforms", "META", 10), ("Apple Inc.", "AAPL", 60)])
    counts = {"GOOGL": 200, "GOOG": 240, "LMCA": 40, "BATRA": 20, "FB": 190, "META": 40, "AAPL": 240}
    cm = build_company_map(list(counts), lp, {"FB": "META"}, counts, overrides={}).set_index("ticker")
    assert cm.loc["GOOGL", "company_id"] == cm.loc["GOOG", "company_id"] == "GOOG"   # most snapshots
    assert cm.loc["FB", "company_id"] == cm.loc["META", "company_id"] == "FB"
    assert cm.loc["BATRA", "company_id"] == "BATRA" and cm.loc["LMCA", "company_id"] == "LMCA"
    assert cm.loc["AAPL", "reason"] == "single ticker"
    assert "share class" in cm.loc["GOOGL", "reason"] and "renamed" in cm.loc["FB", "reason"]


def test_overrides_win():
    lp = pairs([("Liberty Media", "LMCA", 5), ("Liberty Media", "LMCK", 5)])
    cm = build_company_map(["LMCA", "LMCK"], lp, {}, {"LMCA": 5, "LMCK": 4},
                           overrides={"LMCK": "LMCK"}).set_index("ticker")
    assert cm.loc["LMCA", "company_id"] == "LMCA" and cm.loc["LMCK", "company_id"] == "LMCK"


def test_company_snapshots_dedupe_share_classes():
    snaps = pd.DataFrame({"snapshot_utc": [pd.Timestamp("2020-01-01", tz="UTC")] * 3,
                          "ticker": ["GOOG", "GOOGL", "AAPL"], "source_ref": "x", "status": "ok", "method": "table"})
    cm = pd.DataFrame({"ticker": ["GOOG", "GOOGL", "AAPL"], "company_id": ["GOOG", "GOOG", "AAPL"], "reason": ""})
    out = to_company_snapshots(snaps, cm)
    assert sorted(out["ticker"]) == ["AAPL", "GOOG"]


def test_ticker_names_most_used_first():
    tn = ticker_names(pairs([("Google", "GOOG", 10), ("Alphabet Inc.", "GOOG", 50)])).set_index("ticker")
    assert tn.loc["GOOG", "name"] == "Alphabet Inc." and tn.loc["GOOG", "all_names"] == "Alphabet Inc. | Google"
