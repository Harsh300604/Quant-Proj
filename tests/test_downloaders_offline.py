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
    members_a = S.BASE_MEMBERS + ["AAPL", "OLDCO"]
    members_b = S.BASE_MEMBERS + ["AAPL", "NEWCO"]
    for rev, ts in [(10, "2014-12-20T00:00:00Z"), (10, "2014-12-20T00:00:00Z"), (11, "2015-01-10T00:00:00Z")]:
        responses.add(responses.GET, API_URL, json=S.wiki_query(rev, ts),
                      match=[responses.matchers.query_param_matcher({"action": "query"}, strict_match=False)])
    responses.add(responses.GET, API_URL, json=S.wiki_parse(10, S.wiki_table_html(members_a)),
                  match=[responses.matchers.query_param_matcher({"action": "parse", "oldid": "10"}, strict_match=False)])
    responses.add(responses.GET, API_URL, json=S.wiki_parse(11, S.wiki_list_html(members_b)),
                  match=[responses.matchers.query_param_matcher({"action": "parse", "oldid": "11"}, strict_match=False)])
    m = Manifest(raw)
    src = WikipediaMembership.create(raw, m, 100, [1, 15])
    src.download(date(2015, 1, 1), date(2015, 2, 10))   # snapshots 1 Jan, 15 Jan, 1 Feb
    snaps = src.snapshots()
    assert snaps["snapshot_utc"].nunique() == 3
    last = snaps[snaps["snapshot_utc"] == snaps["snapshot_utc"].max()]
    assert "NEWCO" in set(last["ticker"]) and "OLDCO" not in set(last["ticker"])
    assert len(m.entries("membership")) == 3  # 2 revisions + index

    # resume: second run makes no new HTTP calls for already-downloaded revisions
    calls = len(responses.calls)
    src.download(date(2015, 1, 1), date(2015, 2, 10))
    assert len(responses.calls) == calls


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
