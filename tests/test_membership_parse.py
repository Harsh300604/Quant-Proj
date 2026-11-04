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
    assert method == "paren" and len(tickers) == 99


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


def test_parse_old_two_column_link_layout():
    from tests.fixtures.samples import wiki_old_columns_html
    members = BASE_MEMBERS + ["AAPL", "BRK.B"]
    history = [f"H{chr(65 + i)}X" for i in range(20)]
    tickers, method = parse_members(wiki_old_columns_html(members, history))
    assert method == "link"
    assert len(tickers) == 100 and "BRK-B" in tickers
    assert not set(history) & set(tickers)      # past-changes list is kept out


def test_parse_paren_inside_table_cells():
    from tests.fixtures.samples import wiki_paren_cells_html
    history = [f"H{chr(65 + i)}X" for i in range(20)]
    tickers, method = parse_members(wiki_paren_cells_html(BASE_MEMBERS + ["AAPL", "MSFT"], history))
    assert method == "paren" and len(tickers) == 100 and not set(history) & set(tickers)


def test_diagnose_describes_layout():
    from quantagents.data.download.membership import diagnose
    out = diagnose(wiki_table_html(BASE_MEMBERS[:10] + ["AAPL"]).replace("Company AAPL", "Apple Inc."))
    assert "tables:" in out and "Apple" in out


# ---------------------------------------------------------------- point-in-time rules
def test_verify_in_wikitext_drops_tickers_not_saved_that_day():
    from quantagents.data.download.membership import verify_in_wikitext
    kept, dropped = verify_in_wikitext(["AAPL", "BRK-B", "PLTR"], "| [[Apple Inc.]] || AAPL\n| BRK.B")
    assert kept == ["AAPL", "BRK-B"] and dropped == ["PLTR"]


def test_template_name_and_wikitext_links():
    from quantagents.data.download.membership import navbox_template_name, wikitext_link_titles
    from tests.fixtures.samples import wiki_navbox_html
    assert navbox_template_name(wiki_navbox_html(["Apple Inc."])) == "Template:NASDAQ-100"
    wt = "{{Navbox|title=[[Nasdaq-100|List of NASDAQ-100 companies]]|list1=[[Apple Inc.|Apple]] · [[amazon (company)]] · [[File:x.png]] · [[Apple Inc.]]}}"
    assert wikitext_link_titles(wt) == ["Apple Inc.", "Amazon (company)"]


def test_learn_titles_and_parse_template():
    from quantagents.data.download.membership import learn_link_tickers, parse_template
    from tests.fixtures.samples import wiki_linked_paren_html, wiki_template_wikitext
    members = BASE_MEMBERS + ["AAPL", "MSFT"]
    title_map = learn_link_tickers(wiki_linked_paren_html(members), members)
    assert title_map["Company AAPL"] == "AAPL" and len(title_map) == 100
    titles = [f"Company {t}" for t in members if t != "MSFT"] + ["Brand New Corp"]
    tickers, unmatched = parse_template(wiki_template_wikitext(titles), title_map)
    assert len(tickers) == 99 and "MSFT" not in tickers
    assert unmatched == ["Brand New Corp"]       # reported, never guessed


def test_snapshots_are_point_in_time(store):
    """Rendered HTML shows a 2026 member (PLTR / 'Palantir'); neither may leak into 2015-16."""
    from datetime import datetime, timezone
    from quantagents.data.download.base import Manifest, write_json_gz, write_text_gz
    from quantagents.data.download.membership import WikipediaMembership
    from tests.fixtures.samples import wiki_linked_paren_html, wiki_navbox_html, wiki_template_wikitext
    raw = store / "raw"
    src = WikipediaMembership(raw, Manifest(raw))
    members = BASE_MEMBERS + ["AAPL", "MSFT"]
    # rev 1 (2015): article list; its HTML also shows PLTR (rendered from a current template)
    write_text_gz(src.html_file(1), wiki_linked_paren_html(members + ["PLTR"]))
    write_text_gz(src.wikitext_file(1), "\n".join(f"* [[Company {t}]] ({t})" for t in members))
    # rev 2 (2016): list only in the members box; rendered box = today's members
    write_text_gz(src.html_file(2), wiki_navbox_html(["Palantir"] + [f"Company {t}" for t in members]))
    write_text_gz(src.wikitext_file(2), "Article text. {{NASDAQ-100}}")
    write_text_gz(src.template_file("Template:NASDAQ-100", 900),
                  wiki_template_wikitext([f"Company {t}" for t in members] + ["Brand New Corp"]))
    t1 = datetime(2015, 1, 1, tzinfo=timezone.utc).isoformat()
    t2 = datetime(2016, 6, 15, tzinfo=timezone.utc).isoformat()
    write_json_gz(src.folder / "snapshots.json.gz", {
        t1: {"revid": 1, "rev_timestamp": "", "template": None},
        t2: {"revid": 2, "rev_timestamp": "", "template": {"title": "Template:NASDAQ-100", "revid": 900, "timestamp": ""}}})
    snaps = src.snapshots()
    early = snaps[snaps["source_ref"] == "wiki:1"]
    late = snaps[snaps["source_ref"] == "wiki:2+tpl:900"]
    assert "PLTR" not in set(snaps["ticker"])                       # look-ahead blocked
    assert list(src.dropped["ticker"]) == ["PLTR"]
    assert set(early["status"]) == {"ok"} and len(early) == 100
    assert set(late["method"]) == {"template"} and len(late) == 100
    assert list(src.unmatched["title"]) == ["Brand New Corp"]


def test_unverified_revision_needs_review(store):
    from datetime import datetime, timezone
    from quantagents.data.download.base import Manifest, write_json_gz, write_text_gz
    from quantagents.data.download.membership import WikipediaMembership
    raw = store / "raw"
    src = WikipediaMembership(raw, Manifest(raw))
    write_text_gz(src.html_file(1), wiki_table_html(BASE_MEMBERS + ["AAPL", "MSFT"]))  # no wikitext saved
    write_json_gz(src.folder / "snapshots.json.gz",
                  {datetime(2015, 1, 1, tzinfo=timezone.utc).isoformat(): {"revid": 1, "template": None}})
    snaps = src.snapshots()
    assert set(snaps["status"]) == {"needs_review"} and set(snaps["method"]) == {"table-unverified"}


def test_manual_title_map_file(tmp_path):
    from quantagents.data.download.membership import load_title_tickers
    f = tmp_path / "w.csv"
    f.write_text("# comment\ntitle,ticker\nBrand New Corp,bnew\n", encoding="utf-8")
    assert load_title_tickers(f) == {"Brand New Corp": "BNEW"}


# ---------------------------------------------------------------- historical sections and jumps
def test_historical_components_list_is_ignored():
    from tests.fixtures.samples import wiki_with_historical_section
    old = [f"O{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(98)]   # 98 past members, tighter list
    tickers, method = parse_members(wiki_with_historical_section(BASE_MEMBERS + ["AAPL", "MSFT"], old))
    assert method == "paren" and "AAPL" in tickers and not set(old) & set(tickers)


def test_only_historical_list_fails():
    from tests.fixtures.samples import wiki_with_historical_section
    tickers, method = parse_members(wiki_with_historical_section([], BASE_MEMBERS + ["AAPL", "MSFT"]))
    assert tickers == [] and method == "failed"


def test_snapshot_jumps_flags_bad_parse():
    from quantagents.data.download.membership import MAX_JUMP, snapshot_jumps
    good = BASE_MEMBERS + ["AAPL", "MSFT"]
    garbage = [f"O{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(60)] + good[:40]
    snaps = snaps_from({"2017-05-01": good, "2017-05-15": good[:-1] + ["NEWX"], "2017-06-01": garbage})
    j = snapshot_jumps(snaps)
    assert list(j["change"]) == [2, 120] and (j["change"] > MAX_JUMP).sum() == 1


def test_coverage_quick_counts_missing_members():
    import importlib.util
    from quantagents.config import REPO_ROOT
    spec = importlib.util.spec_from_file_location("cq", REPO_ROOT / "scripts" / "coverage_quick.py")
    cq = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cq)
    spells, _ = build_spells(snaps_from({"2014-12-15": ["AAA", "DEAD", "CCC"], "2015-03-15": ["AAA", "CCC", "NEW"]}))
    cov = cq.coverage(spells, {"DEAD"}, date(2015, 1, 1), date(2015, 4, 1))
    assert list(cov["no_prices"]) == [1, 1, 1, 0] and cov["pct"].iloc[0] == 33.3
