from datetime import date

import pandas as pd
import pytest

from quantagents.data.download.membership import (
    build_spells, clean_ticker, members_at, parse_members, removed_members, snapshot_times,
)
from tests.fixtures.samples import BASE_MEMBERS, wiki_list_html, wiki_table_html


def test_parse_table():
    tickers, method = parse_members(wiki_table_html(BASE_MEMBERS + ["AAPL", "GOOGL"]))
    assert method == "table" and len(tickers) == 100 and "GOOGL" in tickers


def test_parse_list_fallback():
    tickers, method = parse_members(wiki_list_html(BASE_MEMBERS + ["AAPL"]))
    assert method == "list" and len(tickers) == 99


def test_parse_implausible_count_fails():
    tickers, method = parse_members(wiki_table_html(["AAPL", "MSFT"]))
    assert tickers == [] and method == "failed"


@pytest.mark.parametrize("raw, out", [("AAPL", "AAPL"), (" msft[3] ", "MSFT"), ("BRK.B", "BRK-B"),
                                      ("NASDAQ: CSCO", "CSCO"), ("not a ticker", None), ("123", None)])
def test_clean_ticker(raw, out):
    assert clean_ticker(raw) == out


def test_snapshot_times():
    ts = snapshot_times(date(2015, 1, 1), date(2015, 3, 10), [1, 15])
    assert [t.date().isoformat() for t in ts] == ["2015-01-01", "2015-01-15", "2015-02-01",
                                                  "2015-02-15", "2015-03-01"]
    assert all(t.tzinfo is not None for t in ts)


def snaps_from(spec: dict[str, list[str]]) -> pd.DataFrame:
    rows = [{"snapshot_utc": pd.Timestamp(d, tz="UTC"), "ticker": t, "source_ref": "wiki:1",
             "status": "ok", "method": "table"} for d, ts in spec.items() for t in ts]
    return pd.DataFrame(rows)


def test_spells_replay_changes():
    # OLD leaves and NEW joins between 15 Dec and 1 Jan
    snaps = snaps_from({"2014-12-01": ["AAA", "OLD"], "2014-12-15": ["AAA", "OLD"],
                        "2015-01-01": ["AAA", "NEW"], "2015-01-15": ["AAA", "NEW"]})
    spells, warnings = build_spells(snaps)
    assert not warnings
    assert members_at(spells, pd.Timestamp("2014-12-20", tz="UTC")) == ["AAA", "OLD"]
    assert members_at(spells, pd.Timestamp("2015-01-10", tz="UTC")) == ["AAA", "NEW"]
    assert removed_members(spells, pd.Timestamp("2014-12-05", tz="UTC"),
                           pd.Timestamp("2015-01-20", tz="UTC")) == ["OLD"]


def test_manual_change_moves_boundary_to_exact_date():
    snaps = snaps_from({"2014-12-15": ["AAA", "OLD"], "2015-01-01": ["AAA", "NEW"]})
    manual = pd.DataFrame([
        {"effective_date": pd.Timestamp("2014-12-22", tz="UTC"), "ticker": "OLD", "action": "remove", "source": "nasdaq"},
        {"effective_date": pd.Timestamp("2014-12-22", tz="UTC"), "ticker": "NEW", "action": "add", "source": "nasdaq"},
        {"effective_date": pd.Timestamp("2010-01-01", tz="UTC"), "ticker": "ZZZ", "action": "add", "source": "nasdaq"},
    ])
    spells, warnings = build_spells(snaps, manual)
    assert members_at(spells, pd.Timestamp("2014-12-21", tz="UTC")) == ["AAA", "OLD"]
    assert members_at(spells, pd.Timestamp("2014-12-22", tz="UTC")) == ["AAA", "NEW"]
    assert len(warnings) == 1 and "ZZZ" in warnings[0]


def test_needs_review_snapshots_ignored():
    snaps = snaps_from({"2015-01-01": ["AAA", "BBB"], "2015-02-01": ["AAA", "BBB"]})
    bad = pd.DataFrame([{"snapshot_utc": pd.Timestamp("2015-01-15", tz="UTC"), "ticker": None,
                         "source_ref": "wiki:2", "status": "needs_review", "method": "failed"}])
    spells, _ = build_spells(pd.concat([snaps, bad]))
    assert members_at(spells, pd.Timestamp("2015-01-20", tz="UTC")) == ["AAA", "BBB"]


def test_changes_between():
    from quantagents.data.download.membership import changes_between
    snaps = snaps_from({"2014-12-15": ["AAA", "OLD"], "2015-01-01": ["AAA", "NEW"]})
    spells, _ = build_spells(snaps)
    ch = changes_between(spells, date(2015, 1, 1), date(2015, 12, 31))
    assert list(zip(ch["ticker"], ch["change"])) == [("NEW", "added"), ("OLD", "removed")]
