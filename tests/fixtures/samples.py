"""Small recorded-style sample responses for offline tests (shapes follow each real API)."""
from __future__ import annotations

import io
import zipfile

BASE_MEMBERS = [f"T{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(98)]  # TAA, TAB, ...


def wiki_table_html(tickers: list[str]) -> str:
    rows = "".join(f"<tr><td>Company {t}</td><td>{t}</td><td>Tech</td></tr>" for t in tickers)
    return ("<div><p>Intro</p><table class='wikitable'><tr><th>Company</th><th>Ticker</th>"
            f"<th>Sector</th></tr>{rows}</table>"
            "<table><tr><th>Year</th><th>Note</th></tr><tr><td>2014</td><td>x</td></tr></table></div>")


def wiki_list_html(tickers: list[str]) -> str:
    items = "".join(f"<li><a href='#'>Company {t}</a> (<a href='#'>{t}</a>)</li>" for t in tickers)
    return f"<div><h2>Components</h2><ul>{items}</ul><ul><li>See also (NOT A TICKER LIST)</li></ul></div>"


def wiki_query(revid: int, ts: str) -> dict:
    return {"batchcomplete": True, "query": {"pages": [
        {"pageid": 1, "ns": 0, "title": "Nasdaq-100",
         "revisions": [{"revid": revid, "parentid": revid - 1, "timestamp": ts}]}]}}


def wiki_parse(revid: int, html: str) -> dict:
    return {"parse": {"title": "Nasdaq-100", "pageid": 1, "revid": revid, "text": html}}


def alpaca_page(ticker: str, ids: list[int], token: str | None) -> dict:
    return {"news": [{"id": i, "headline": f"{ticker} news {i}", "summary": "s", "author": "a",
                      "created_at": "2015-01-05T21:30:00Z", "updated_at": "2015-01-05T21:30:00Z",
                      "url": "https://example.com", "symbols": [ticker], "source": "benzinga",
                      "content": "", "images": []} for i in ids],
            "next_page_token": token}


SEC_TICKERS = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
               "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"}}


def sec_submissions(cik: int, with_page: bool = False) -> dict:
    return {"cik": str(cik), "name": "X", "sic": "3571", "sicDescription": "Electronic Computers",
            "tickers": ["AAPL"], "addresses": {"business": {"stateOrCountry": "CA"}},
            "filings": {"recent": {"accessionNumber": ["0000320193-15-000001"],
                                   "acceptanceDateTime": ["2015-01-28T16:31:00.000Z"],
                                   "form": ["10-Q"], "filingDate": ["2015-01-28"]},
                        "files": ([{"name": f"CIK{cik:010d}-submissions-001.json", "filingCount": 1}]
                                  if with_page else [])}}


def sec_submissions_page() -> dict:
    return {"accessionNumber": ["0000320193-09-000001"], "acceptanceDateTime": ["2009-01-01T00:00:00.000Z"],
            "form": ["10-K"], "filingDate": ["2009-01-01"]}


def sec_facts(cik: int) -> dict:
    return {"cik": cik, "entityName": "X", "facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"end": "2014-12-27", "val": 74599000000, "accn": "0000320193-15-000001", "fy": 2015,
         "fp": "Q1", "form": "10-Q", "filed": "2015-01-28"}]}}}}}


def french_zip(daily: bool) -> bytes:
    if daily:
        body = ("This file was created by CMPT_ME_BEME_RETS_DAILY\n\n"
                ",Mkt-RF,SMB,HML,RF\n20150102,  -0.12,  -0.55,   0.05,   0.00\n"
                "20150105,  -1.84,   0.30,  -0.61,   0.00\n\n Copyright 2024\n")
    else:
        body = ("This file was created by CMPT_ME_BEME_RETS\n\n"
                ",Mkt-RF,SMB,HML,RF\n201501,  -3.11,  -0.58,  -3.47,   0.00\n"
                "201502,   6.13,   0.42,  -1.79,   0.00\n\n Annual Factors: January-December\n"
                ",Mkt-RF,SMB,HML,RF\n2015,  0.06, -3.89, -9.65, 0.02\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.CSV", body)
    return buf.getvalue()


FRED_CSV = "observation_date,DTB3\n2015-01-02,0.03\n2015-01-05,0.03\n2015-01-06,\n"


def wiki_old_columns_html(tickers: list[str], history: list[str]) -> str:
    """Older layout: two-column list, 'Company (NASDAQ: XXX)' with nasdaq.com links,
    followed by a list of past changes that also mentions tickers."""
    half = len(tickers) // 2
    def ul(ts):
        return "<ul>" + "".join(
            f"<li><a href='/wiki/{t}'>Company {t}</a> (NASDAQ: "
            f"<a class='external text' href='http://www.nasdaq.com/symbol/{t.lower()}'>{t}</a>)</li>"
            for t in ts) + "</ul>"
    hist = "<ul>" + "".join(f"<li>Removed Old {t} ({t})</li>" for t in history) + "</ul>"
    return (f"<div><h2>Components</h2><div class='div-col columns column-width'>{ul(tickers[:half])}"
            f"{ul(tickers[half:])}</div><h2>Changes</h2>{hist}</div>")


def wiki_paren_cells_html(tickers: list[str], history: list[str]) -> str:
    """Layout with tickers only inside the company cell, no ticker column."""
    rows = "".join(f"<tr><td>Company {t} ({t})</td><td>Tech</td></tr>" for t in tickers)
    hist = "<p>" + " ".join(f"Former member ({t})." for t in history) + "</p>"
    return f"<div><table><tr><th>Company</th><th>Sector</th></tr>{rows}</table>{hist}</div>"


def wiki_linked_paren_html(tickers: list[str]) -> str:
    """'Company (TICKER)' list where each company links to its Wikipedia article."""
    items = "".join(f"<li><a href='/wiki/Company_{t}'>Company {t}</a> ({t})</li>" for t in tickers)
    return f"<div><h2>Components</h2><ul>{items}</ul></div>"


def wiki_navbox_html(titles: list[str]) -> str:
    """2016-2018 layout: members only as names in the navigation box (no tickers)."""
    links = " · ".join(f"<li><a href='/wiki/{t.replace(' ', '_')}'>{t}</a></li>" for t in titles)
    return ("<div><p>As of March 2016, 459 companies have been components. Apple (AAPL) ...</p>"
            "<style data-mw-deduplicate='x'>.mw-parser-output .navbar{display:inline;font-size:88%}"
            ".mw-parser-output .hlist dl,.mw-parser-output .hlist ol{margin:0}</style>"
            "<div role='navigation' class='navbox'><style>" + ".mw-parser-output .navbox{border:1px solid #a2a9b1}" * 12 + "</style>"
            "<table class='nowraplinks navbox-inner'>"
            "<tr><th><style>" + ".mw-parser-output .navbar{display:inline;font-size:88%}" * 12 + "</style>"
            "<a href='/wiki/Template:NASDAQ-100'>v</a> List of NASDAQ-100 companies</th></tr>"
            f"<tr><td><ul>{links}</ul></td></tr></table></div>"
            "<div class='navbox'><table><tr><th>Nasdaq, Inc.</th></tr><tr><td>"
            "<a href='/wiki/Nasdaq_Stock_Market'>Nasdaq</a></td></tr></table></div></div>")


def wiki_template_wikitext(titles: list[str]) -> str:
    """Members template source as saved on some date."""
    links = " · ".join(f"[[{t}]]" for t in titles)
    return ("{{Navbox\n| name = NASDAQ-100\n| title = [[Nasdaq-100|List of NASDAQ-100 companies]]\n"
            f"| list1 = {links}\n}}}}")


def wiki_api_callback(html_for_revid, wikitext_for_revid, revid_for_time):
    """`responses` callback emulating the MediaWiki API (query by time, query by revids, parse)."""
    import json
    from urllib.parse import parse_qs, urlparse

    def cb(request):
        q = {k: v[0] for k, v in parse_qs(urlparse(request.url).query).items()}
        if q["action"] == "parse":
            rid = int(q["oldid"])
            return 200, {}, json.dumps(wiki_parse(rid, html_for_revid(rid)))
        if "revids" in q:
            revs = [{"revid": int(r), "slots": {"main": {"content": wikitext_for_revid(int(r))}}}
                    for r in q["revids"].split("|")]
            return 200, {}, json.dumps({"query": {"pages": [{"pageid": 1, "revisions": revs}]}})
        rid = revid_for_time(q["rvstart"])
        return 200, {}, json.dumps(wiki_query(rid, q["rvstart"]))
    return cb


def wiki_with_historical_section(current: list[str], historical: list[str]) -> str:
    """Current list under 'Components', a longer bracket list under 'Historical components'."""
    def ul(ts):
        return "<ul>" + "".join(f"<li><a href='/wiki/Company_{t}'>Company {t}</a> ({t})</li>" for t in ts) + "</ul>"
    return (f"<div><div class='mw-heading mw-heading2'><h2 id='Components'>Components</h2></div>{ul(current)}"
            f"<h2><span class='mw-headline' id='Historical_components'>Historical components</span></h2>"
            f"<p>As of March 2016, 459 companies have been components.</p>{ul(historical)}</div>")
