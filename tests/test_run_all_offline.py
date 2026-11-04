"""End-to-end `run_all --pilot` with every external service mocked."""
import re

import pandas as pd
import responses

from quantagents.data.download import prices as prices_mod
from quantagents.data.download import run_all
from quantagents.data.download.factors import FRED_URL, FRENCH_BASE, FRENCH_FILES
from quantagents.data.download.membership import API_URL
from quantagents.env_secrets import Secrets
from tests.fixtures import samples as S
from tests.test_downloaders_offline import fake_history

BEFORE = S.BASE_MEMBERS[:-4] + ["AAPL", "MSFT", "NVDA", "AMZN", "OLDCO", "OLDTW"]
AFTER = S.BASE_MEMBERS[:-4] + ["AAPL", "MSFT", "NVDA", "AMZN", "NEWCO", "NEWTW"]


wiki_callback = S.wiki_api_callback(
    html_for_revid=lambda r: S.wiki_table_html(BEFORE if r == 10 else AFTER),
    wikitext_for_revid=lambda r: " ".join(BEFORE if r == 10 else AFTER),
    revid_for_time=lambda t: 10 if t < "2018-01-01" else 11)


@responses.activate
def test_pilot_end_to_end(store, monkeypatch, capsys):
    responses.add_callback(responses.GET, API_URL, callback=wiki_callback)
    for key, fname in FRENCH_FILES.items():
        responses.add(responses.GET, FRENCH_BASE + fname, body=S.french_zip("daily" in key))
    responses.add(responses.GET, FRED_URL, body=S.FRED_CSV)

    def fetch(sym, s, e):  # OLDCO has no Yahoo data, so OLDTW should be picked
        return pd.DataFrame() if sym == "OLDCO" else fake_history(sym, s, e)
    monkeypatch.setattr(prices_mod, "_yf_fetch", fetch)
    monkeypatch.setattr(run_all, "load_secrets", lambda: Secrets({}))

    code = run_all.main(["--pilot"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "pilot 5th stock (left the index later): OLDTW" in out
    assert re.search(r"members on 2015-01-02: 100", out)
    assert "SKIPPED: ALPACA_API_KEY, ALPACA_SECRET_KEY missing" in out
    assert "SKIPPED: SEC_USER_AGENT missing" in out
    spells = pd.read_csv(store / "derived" / "ndx_membership.csv")
    assert set(spells["ticker"]) >= {"OLDCO", "NEWCO"}
    for t in ["AAPL", "MSFT", "NVDA", "AMZN", "OLDTW", "QQQ", "_NDX"]:
        assert (store / "raw" / "prices" / "yfinance" / f"{t}.parquet").exists()

    # second run resumes: no new Wikipedia parse calls
    parse_calls = sum("action=parse" in c.request.url for c in responses.calls)
    assert run_all.main(["--pilot"]) == 0
    assert sum("action=parse" in c.request.url for c in responses.calls) == parse_calls
