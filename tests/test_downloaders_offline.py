"""Downloaders against mocked HTTP responses: files, manifest and resume behaviour."""
from datetime import date

import pandas as pd
import pytest
import responses

from quantagents.data.download import base
from quantagents.data.download.base import HttpClient, HttpError, Manifest, read_json_gz, read_jsonl_gz
from quantagents.data.download.edgar import FACTS_URL, SUBMISSIONS_URL, TICKERS_URL, SecEdgar
from quantagents.data.download.factors import (
    FRED_URL, FRENCH_BASE, FRENCH_FILES, FredRiskFree, FrenchFactors, parse_french_csv,
)
from quantagents.data.download.membership import API_URL, WikipediaMembership
from quantagents.data.download.news import NEWS_URL, AlpacaNews
from quantagents.data.download.prices import YFinancePrices, read_manual_prices
from tests.fixtures import samples as S


@pytest.fixture
def raw(store):
    d = store / "raw"
    d.mkdir(parents=True)
    return d


# ---------------------------------------------------------------- HTTP client
@responses.activate
def test_http_retries_then_succeeds():
    responses.add(responses.GET, "https://x.test/a", status=503)
    responses.add(responses.GET, "https://x.test/a", status=429, headers={"Retry-After": "1"})
    responses.add(responses.GET, "https://x.test/a", json={"ok": 1})
    assert HttpClient(100).get("https://x.test/a").json() == {"ok": 1}


@responses.activate
def test_http_error_hides_headers():
    responses.add(responses.GET, "https://x.test/b", status=403)
    c = HttpClient(100, headers={"APCA-API-SECRET-KEY": "SUPERSECRET"})
    with pytest.raises(HttpError) as e:
        c.get("https://x.test/b")
    assert "SUPERSECRET" not in str(e.value) and "403" in str(e.value)


# ---------------------------------------------------------------- membership
@responses.activate
def test_wikipedia_membership(raw):
    # 3 snapshots: two share revision 10, the third uses revision 11 (one member replaced)
    members = {10: S.BASE_MEMBERS + ["AAPL", "OLDCO"], 11: S.BASE_MEMBERS + ["AAPL", "NEWCO"]}
    responses.add_callback(responses.GET, API_URL, callback=S.wiki_api_callback(
        html_for_revid=lambda r: (S.wiki_table_html if r == 10 else S.wiki_list_html)(members[r]),
        wikitext_for_revid=lambda r: " ".join(members[r]),
        revid_for_time=lambda t: 10 if t < "2015-01-10" else 11))
    m = Manifest(raw)
    src = WikipediaMembership.create(raw, m, 100, [1, 15])
    src.download(date(2015, 1, 1), date(2015, 2, 10))   # snapshots 1 Jan, 15 Jan, 1 Feb
    snaps = src.snapshots()
    assert snaps["snapshot_utc"].nunique() == 3 and set(snaps["status"]) == {"ok"}
    last = snaps[snaps["snapshot_utc"] == snaps["snapshot_utc"].max()]
    assert "NEWCO" in set(last["ticker"]) and "OLDCO" not in set(last["ticker"])
    assert src.wikitext_file(10).exists() and src.wikitext_file(11).exists()

    # resume: second run makes no new HTTP calls
    calls = len(responses.calls)
    src.download(date(2015, 1, 1), date(2015, 2, 10))
    assert len(responses.calls) == calls


@responses.activate
def test_wikipedia_fetches_template_as_of_snapshot_time(raw):
    """When the article has no list, the members template is fetched as it was at time t."""
    import json
    from urllib.parse import parse_qs, urlparse
    members = S.BASE_MEMBERS + ["AAPL", "MSFT"]
    seen = []

    def cb(request):
        q = {k: v[0] for k, v in parse_qs(urlparse(request.url).query).items()}
        if q["action"] == "parse":
            return 200, {}, json.dumps(S.wiki_parse(20, S.wiki_navbox_html(["Palantir"])))
        if "revids" in q:
            return 200, {}, json.dumps({"query": {"pages": [{"revisions": [
                {"revid": 20, "slots": {"main": {"content": "{{NASDAQ-100}}"}}}]}]}})
        if q["titles"] == "Template:NASDAQ-100":
            seen.append(q["rvstart"])
            return 200, {}, json.dumps({"query": {"pages": [{"revisions": [
                {"revid": 900, "timestamp": "2016-06-01T00:00:00Z",
                 "slots": {"main": {"content": S.wiki_template_wikitext([f"Company {t}" for t in members])}}}]}]}})
        return 200, {}, json.dumps(S.wiki_query(20, q["rvstart"]))

    responses.add_callback(responses.GET, API_URL, callback=cb)
    src = WikipediaMembership.create(raw, Manifest(raw), 100, [15])
    src.download(date(2016, 6, 1), date(2016, 6, 30))
    assert seen == ["2016-06-15T00:00:00Z"]       # template asked for as of the snapshot time
    assert src.template_file("Template:NASDAQ-100", 900).exists()


# ---------------------------------------------------------------- prices
def fake_history(symbol, start, end):
    if symbol in ("DEAD",):
        return pd.DataFrame()
    idx = pd.date_range("2015-01-02", periods=3, freq="B", tz="America/New_York")
    return pd.DataFrame({"Open": [1.0, 2, 3], "High": [1.0, 2, 3], "Low": [1.0, 2, 3],
                         "Close": [1.0, 2, 3], "Adj Close": [0.9, 1.9, 2.9], "Volume": [10, 20, 30],
                         "Dividends": [0.0, 0.1, 0.0], "Stock Splits": [0.0, 0.0, 2.0]}, index=idx)


def test_prices_download_and_missing(raw):
    m = Manifest(raw)
    calls = []
    def fetch(sym, s, e):
        calls.append(sym)
        return fake_history(sym, s, e)
    src = YFinancePrices(raw, m, fetch=fetch, aliases={"FB": "META"})
    res = src.download(["AAPL", "FB", "DEAD", "^NDX"], date(2014, 1, 1), date(2015, 1, 31))
    assert res["DEAD"] is None and res["AAPL"].exists()
    assert "META" in calls                              # alias used
    assert res["^NDX"].name == "_NDX.parquet"           # Windows-safe name
    df = pd.read_parquet(res["AAPL"])
    assert list(df.columns) == ["open", "high", "low", "close", "adj_close", "volume", "dividends", "splits"]
    assert df.index.tz is None and len(df) == 3
    missing = pd.read_csv(raw / "prices" / "missing.csv")
    assert list(missing["ticker"]) == ["DEAD"]
    # resume: nothing re-fetched except the missing ticker
    calls.clear()
    src.download(["AAPL", "FB", "DEAD"], date(2014, 1, 1), date(2015, 1, 31))
    assert calls == ["DEAD"]


def test_manual_prices(store):
    d = store / "manual_prices"
    d.mkdir(parents=True)
    (d / "DEAD.csv").write_text("Date,Open,High,Low,Close,Adj Close,Volume\n2015-01-02,1,1,1,1,1,100\n")
    df = read_manual_prices(d, "DEAD")
    assert df.loc["2015-01-02", "adj_close"] == 1 and df["dividends"].iloc[0] == 0
    assert read_manual_prices(d, "NONE") is None


# ---------------------------------------------------------------- news
@responses.activate
def test_alpaca_news_paginates_and_resumes(raw):
    responses.add(responses.GET, NEWS_URL, json=S.alpaca_page("AAPL", [1, 2], "tok1"),
                  match=[responses.matchers.query_param_matcher({"symbols": "AAPL"}, strict_match=False)])
    responses.add(responses.GET, NEWS_URL, json=S.alpaca_page("AAPL", [3], None),
                  match=[responses.matchers.query_param_matcher({"symbols": "AAPL", "page_token": "tok1"}, strict_match=False)])
    m = Manifest(raw)
    src = AlpacaNews.create(raw, m, "KEYID", "SECRET", 6000)
    out = src.download(["AAPL"], date(2015, 1, 1), date(2015, 12, 31))
    rows = read_jsonl_gz(out["AAPL"][0])
    assert [r["id"] for r in rows] == [1, 2, 3]
    assert set(rows[0]) == {"id", "headline", "summary", "author", "created_at", "updated_at",
                            "url", "symbols", "source"}
    req = responses.calls[0].request
    assert req.headers["APCA-API-KEY-ID"] == "KEYID"
    n = len(responses.calls)
    src.download(["AAPL"], date(2015, 1, 1), date(2015, 12, 31))
    assert len(responses.calls) == n  # resumed, no new calls


def test_alpaca_symbols_for_renamed():
    src = AlpacaNews(raw_dir=None, manifest=None, http=None, aliases={"FB": "META"})
    assert src.symbols_for("FB") == "FB,META" and src.symbols_for("AAPL") == "AAPL"


# ---------------------------------------------------------------- SEC EDGAR
@responses.activate
def test_edgar(raw):
    responses.add(responses.GET, TICKERS_URL, json=S.SEC_TICKERS)
    responses.add(responses.GET, SUBMISSIONS_URL.format(name="CIK0000320193.json"), json=S.sec_submissions(320193, True))
    responses.add(responses.GET, SUBMISSIONS_URL.format(name="CIK0000320193-submissions-001.json"), json=S.sec_submissions_page())
    responses.add(responses.GET, FACTS_URL.format(cik="0000320193"), json=S.sec_facts(320193))
    m = Manifest(raw)
    src = SecEdgar.create(raw, m, "QuantAgents research test@example.com", 1000)
    out = src.download(["AAPL", "GONE"])
    assert len(out["AAPL"]) == 3 and out["GONE"] == []
    assert responses.calls[0].request.headers["User-Agent"].endswith("test@example.com")
    sub = read_json_gz(out["AAPL"][0])
    assert sub["filings"]["recent"]["acceptanceDateTime"][0].startswith("2015-01-28T16:31")
    missing = pd.read_csv(raw / "edgar" / "missing.csv")
    assert list(missing["ticker"]) == ["GONE"]


def test_edgar_requires_email(raw):
    with pytest.raises(ValueError, match="contact email"):
        SecEdgar.create(raw, Manifest(raw), "no email here", 5)


# ---------------------------------------------------------------- factors / risk-free
@responses.activate
def test_french_and_fred(raw):
    for key, fname in FRENCH_FILES.items():
        responses.add(responses.GET, FRENCH_BASE + fname, body=S.french_zip("daily" in key))
    responses.add(responses.GET, FRED_URL, body=S.FRED_CSV)
    m = Manifest(raw)
    files = FrenchFactors.create(raw, m).download()
    assert len(files) == 4
    daily = parse_french_csv(files[0].read_bytes())
    assert list(daily.columns) == ["Mkt-RF", "SMB", "HML", "RF"] and len(daily) == 2
    monthly = parse_french_csv(S.french_zip(False))
    assert len(monthly) == 2 and monthly.index[0] == pd.Timestamp("2015-01-31")  # annual block excluded
    p = FredRiskFree.create(raw, m).download(date(2014, 1, 1), date(2015, 1, 31))
    assert p.exists() and m.summary().set_index("source").loc["riskfree", "rows"] == 3


def test_manifest_detects_changed_file(raw):
    m = Manifest(raw)
    f = raw / "x.txt"
    f.write_text("a")
    m.record("t", f, 1)
    assert Manifest(raw).is_complete(f)       # reloaded from disk
    f.write_text("b")
    assert not Manifest(raw).is_complete(f)   # checksum mismatch -> re-download


# ---------------------------------------------------------------- SEC: delisted companies by name
def test_normalize_company_names():
    from quantagents.data.download.edgar import normalize_company
    assert normalize_company("Activision Blizzard, Inc.") == normalize_company("ACTIVISION BLIZZARD INC") == "ACTIVISION BLIZZARD"
    assert normalize_company("ALTERA CORP /DE/") == "ALTERA"
    assert normalize_company("Yahoo!") == "YAHOO"
    assert normalize_company("Shire (pharmaceutical company)") == "SHIRE"
    assert normalize_company("The Kraft Heinz Company") == "KRAFT HEINZ"


@responses.activate
def test_edgar_finds_delisted_company_by_name(raw):
    """Old 'Broadcom Corp' vs new Broadcom: pick the filer active while BRCM was in the index;
    skip CIKs already used by current tickers."""
    from quantagents.data.download.edgar import CIK_LOOKUP_URL
    responses.add(responses.GET, TICKERS_URL, json={"0": {"cik_str": 1730168, "ticker": "AVGO", "title": "Broadcom Inc."}})
    responses.add(responses.GET, CIK_LOOKUP_URL, body=(
        "BROADCOM CORP:0001054374:\nBROADCOM INC.:0001730168:\nBROADCOM LTD:0001649338:\nXILINX INC:0000743988:\n"))
    names = {1054374: "BROADCOM CORP", 1649338: "BROADCOM LTD", 1730168: "BROADCOM INC.", 743988: "XILINX INC"}
    def subs(cik, years):
        return {"cik": cik, "name": names[cik], "filings": {"recent": {
            "form": ["10-K"] * len(years), "filingDate": [f"{y}-02-01" for y in years],
            "accessionNumber": [f"a{y}" for y in years], "acceptanceDateTime": [f"{y}-02-01T00:00:00.000Z" for y in years]},
            "files": []}}
    responses.add(responses.GET, SUBMISSIONS_URL.format(name="CIK0001054374.json"), json=subs(1054374, [2014, 2015, 2016]))
    responses.add(responses.GET, SUBMISSIONS_URL.format(name="CIK0001649338.json"), json=subs(1649338, [2017, 2018]))
    responses.add(responses.GET, SUBMISSIONS_URL.format(name="CIK0001730168.json"), json=subs(1730168, [2019]))
    responses.add(responses.GET, SUBMISSIONS_URL.format(name="CIK0000743988.json"), json=subs(743988, [2014, 2020]))
    for c in ("0001054374", "0001730168", "0000743988"):
        responses.add(responses.GET, FACTS_URL.format(cik=c), json=S.sec_facts(int(c)))
    src = SecEdgar.create(raw, Manifest(raw), "QuantAgents research test@example.com", 1000)
    from datetime import date as d
    out = src.download(["AVGO", "BRCM", "XLNX", "NONAME"],
                       names={"BRCM": ["Broadcom Corporation"], "XLNX": ["Xilinx"]},
                       periods={"BRCM": (d(2014, 1, 1), d(2016, 2, 1)), "XLNX": (d(2014, 1, 1), d(2022, 2, 1))})
    m = pd.read_csv(raw / "edgar" / "cik_matches.csv", dtype=str).set_index("ticker")
    assert m.loc["BRCM", "cik"] == "0001054374" and m.loc["BRCM", "confidence"] == "high"
    assert m.loc["XLNX", "cik"] == "0000743988"
    assert m.loc["NONAME", "confidence"].startswith("none")
    assert len(out["BRCM"]) == 2 and out["NONAME"] == []



def test_name_used_during_handles_names_that_moved_between_filers():
    """'VIACOM INC' was the CBS/Paramount filer until 2005 and the new Viacom from 2006."""
    from datetime import date as d
    from quantagents.data.download.edgar import name_used_during
    cbs = {"name": "PARAMOUNT GLOBAL", "formerNames": [
        {"name": "VIACOM INC", "from": "1995-01-01T00:00:00.000Z", "to": "2005-12-31T00:00:00.000Z"},
        {"name": "CBS CORP", "from": "2005-12-31T00:00:00.000Z", "to": "2019-12-04T00:00:00.000Z"},
        {"name": "VIACOMCBS INC.", "from": "2019-12-04T00:00:00.000Z", "to": "2022-02-16T00:00:00.000Z"}]}
    viacom = {"name": "VIACOM INC", "formerNames": [
        {"name": "New Viacom Corp.", "from": "2005-08-01T00:00:00.000Z", "to": "2005-12-20T00:00:00.000Z"}]}
    period = (d(2014, 1, 1), d(2019, 12, 31))
    assert not name_used_during(cbs, ["Viacom"], *period)
    assert name_used_during(viacom, ["Viacom"], *period)
    assert name_used_during(cbs, ["CBS Corporation"], *period)


@responses.activate
def test_edgar_shares_cik_within_a_company(raw):
    """Liberty Interactive (QVCA) was renamed Qurate Retail (QRTEA): one company, one CIK."""
    from datetime import date as d
    from quantagents.data.download.edgar import CIK_LOOKUP_URL
    responses.add(responses.GET, TICKERS_URL, json={})
    responses.add(responses.GET, CIK_LOOKUP_URL, body="QURATE RETAIL, INC.:0001355096:\nLIBERTY INTERACTIVE CORP:0001355096:\n")
    responses.add(responses.GET, SUBMISSIONS_URL.format(name="CIK0001355096.json"), json={
        "cik": 1355096, "name": "QURATE RETAIL, INC.", "formerNames": [
            {"name": "LIBERTY INTERACTIVE CORP", "from": "2011-01-01T00:00:00.000Z", "to": "2018-04-10T00:00:00.000Z"}],
        "filings": {"recent": {"form": ["10-K"] * 6, "filingDate": [f"{y}-02-01" for y in range(2014, 2020)],
                               "accessionNumber": list("abcdef"), "acceptanceDateTime": [""] * 6}, "files": []}})
    responses.add(responses.GET, FACTS_URL.format(cik="0001355096"), json=S.sec_facts(1355096))
    src = SecEdgar.create(raw, Manifest(raw), "QuantAgents research test@example.com", 1000)
    out = src.download(["QVCA", "QRTEA"], names={"QVCA": ["Liberty Interactive"], "QRTEA": ["Qurate Retail"]},
                       periods={"QVCA": (d(2014, 1, 1), d(2018, 4, 1)), "QRTEA": (d(2018, 4, 1), d(2019, 12, 1))},
                       company_of={"QVCA": "QVCA", "QRTEA": "QVCA"})
    assert out["QVCA"] and out["QRTEA"] and out["QVCA"] == out["QRTEA"]
    m = pd.read_csv(raw / "edgar" / "cik_matches.csv", dtype=str)
    assert list(m["ticker"]) == ["QVCA+QRTEA"] and m["cik"].iloc[0] == "0001355096"
    tc = pd.read_csv(raw / "edgar" / "ticker_ciks.csv", dtype=str).set_index("ticker")
    assert tc.loc["QRTEA", "cik"] == tc.loc["QVCA", "cik"] == "0001355096"


def test_cik_override_same_as_other_ticker(tmp_path):
    from quantagents.data.download.edgar import load_cik_overrides
    f = tmp_path / "o.csv"
    f.write_text("ticker,cik,note\nDISCA,=WBD,same filer\nABC,123,x\n", encoding="utf-8")
    assert load_cik_overrides(f) == {"DISCA": "=WBD", "ABC": "0000000123"}



@responses.activate
def test_edgar_rejects_reused_current_ticker(raw):
    """SNDK in SEC's current list is the 2025 Sandisk spin-off; the index member (2014-2016) was
    the old SanDisk Corp - the current-list match must be rejected and the name lookup used."""
    from datetime import date as d
    from quantagents.data.download.edgar import CIK_LOOKUP_URL
    responses.add(responses.GET, TICKERS_URL, json={"0": {"cik_str": 2023554, "ticker": "SNDK", "title": "Sandisk Corp"}})
    responses.add(responses.GET, CIK_LOOKUP_URL, body="SANDISK CORP:0001000180:\nSANDISK CORP:0002023554:\n")
    def subs(cik, years, name):
        return {"cik": cik, "name": name, "filings": {"recent": {"form": ["10-K"] * len(years),
                "filingDate": [f"{y}-02-01" for y in years], "accessionNumber": [str(y) for y in years],
                "acceptanceDateTime": [""] * len(years)}, "files": []}}
    responses.add(responses.GET, SUBMISSIONS_URL.format(name="CIK0002023554.json"), json=subs(2023554, [2025, 2026], "Sandisk Corp"))
    responses.add(responses.GET, SUBMISSIONS_URL.format(name="CIK0001000180.json"), json=subs(1000180, [2014, 2015, 2016], "SANDISK CORP"))
    responses.add(responses.GET, FACTS_URL.format(cik="0001000180"), json=S.sec_facts(1000180))
    src = SecEdgar.create(raw, Manifest(raw), "QuantAgents research test@example.com", 1000)
    src.download(["SNDK"], names={"SNDK": ["SanDisk"]}, periods={"SNDK": (d(2014, 1, 1), d(2016, 5, 15))})
    tc = pd.read_csv(raw / "edgar" / "ticker_ciks.csv", dtype=str).set_index("ticker")
    assert tc.loc["SNDK", "cik"] == "0001000180"
    assert "rejected" in tc.loc["SNDK", "source"]



@responses.activate
def test_edgar_keeps_old_large_filer_whose_recent_section_is_short(raw):
    """A big company that left the index in 2016 has only 2023-2026 in its 'recent' section
    (Form 4s fill it); its 2014-2016 reports are in an archive page. It must NOT be rejected."""
    from datetime import date as d
    responses.add(responses.GET, TICKERS_URL, json={"0": {"cik_str": 320193, "ticker": "OLDX", "title": "Old X"}})
    responses.add(responses.GET, SUBMISSIONS_URL.format(name="CIK0000320193.json"), json={
        "cik": 320193, "name": "OLD X INC", "filings": {
            "recent": {"form": ["4"] * 3, "filingDate": ["2023-05-01", "2024-05-01", "2026-05-01"],
                       "accessionNumber": ["a", "b", "c"], "acceptanceDateTime": [""] * 3},
            "files": [{"name": "CIK0000320193-submissions-001.json", "filingCount": 900,
                       "filingFrom": "1994-01-26", "filingTo": "2023-04-30"}]}})
    responses.add(responses.GET, SUBMISSIONS_URL.format(name="CIK0000320193-submissions-001.json"), json={
        "accessionNumber": ["p1", "p2", "p3"], "acceptanceDateTime": [""] * 3,
        "form": ["10-K", "10-Q", "10-K"], "filingDate": ["2014-10-27", "2015-04-28", "2015-10-28"]})
    responses.add(responses.GET, FACTS_URL.format(cik="0000320193"), json=S.sec_facts(320193))
    src = SecEdgar.create(raw, Manifest(raw), "QuantAgents research test@example.com", 1000)
    out = src.download(["OLDX"], names={"OLDX": ["Old X"]}, periods={"OLDX": (d(2014, 1, 1), d(2016, 6, 1))})
    tc = pd.read_csv(raw / "edgar" / "ticker_ciks.csv", dtype=str).set_index("ticker")
    assert tc.loc["OLDX", "source"] == "sec_current_list" and out["OLDX"]


def test_earliest_filing_uses_archive_pages():
    from quantagents.data.download.edgar import earliest_filing
    sub = {"filings": {"recent": {"filingDate": ["2024-01-01"]}, "files": [{"filingFrom": "1999-03-02"}]}}
    assert earliest_filing(sub) == "1999-03-02"
    assert earliest_filing({"filings": {"recent": {"filingDate": ["2025-06-01"]}, "files": []}}) == "2025-06-01"



@responses.activate
def test_edgar_rejects_private_company_with_old_form_d_filings(raw):
    """Via Transportation filed Form D (private fundraising) for years before listing in 2025;
    that must not make it look like the 2014-2019 index member VIA (Viacom)."""
    from datetime import date as d
    from quantagents.data.download.edgar import CIK_LOOKUP_URL
    responses.add(responses.GET, TICKERS_URL, json={"0": {"cik_str": 1603015, "ticker": "VIA", "title": "Via Transportation"}})
    responses.add(responses.GET, CIK_LOOKUP_URL, body="VIACOM INC.:0001339947:\n")
    responses.add(responses.GET, SUBMISSIONS_URL.format(name="CIK0001603015.json"), json={
        "cik": 1603015, "name": "Via Transportation, Inc.", "filings": {"recent": {
            "form": ["D", "D", "S-1", "10-Q"], "filingDate": ["2014-03-01", "2017-05-01", "2025-08-01", "2025-11-01"],
            "accessionNumber": list("abcd"), "acceptanceDateTime": [""] * 4}, "files": []}})
    responses.add(responses.GET, SUBMISSIONS_URL.format(name="CIK0001339947.json"), json={
        "cik": 1339947, "name": "VIACOM INC.", "filings": {"recent": {
            "form": ["10-K"] * 5, "filingDate": [f"{y}-11-15" for y in range(2014, 2019)],
            "accessionNumber": list("vwxyz"), "acceptanceDateTime": [""] * 5}, "files": []}})
    responses.add(responses.GET, FACTS_URL.format(cik="0001339947"), json=S.sec_facts(1339947))
    src = SecEdgar.create(raw, Manifest(raw), "QuantAgents research test@example.com", 1000)
    src.download(["VIA", "VIAB"], names={"VIA": ["Viacom"], "VIAB": ["Viacom"]},
                 periods={"VIA": (d(2014, 1, 1), d(2019, 12, 1)), "VIAB": (d(2014, 1, 1), d(2019, 12, 1))},
                 company_of={"VIA": "VIA", "VIAB": "VIA"})
    tc = pd.read_csv(raw / "edgar" / "ticker_ciks.csv", dtype=str).set_index("ticker")
    assert tc.loc["VIA", "cik"] == tc.loc["VIAB", "cik"] == "0001339947"
    assert "rejected" in tc.loc["VIA", "source"]
