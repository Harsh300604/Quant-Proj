"""Anonymizer: names, short names, brands and tickers are replaced; aliases are stable; scan finds leaks."""
import json

from quantagents.agents.anonymize import Anonymizer, name_forms

COMPANIES = {"AAPL": {"name": "Apple Inc.", "tickers": ["AAPL"]},
             "GOOGL": {"name": "Alphabet Inc.", "tickers": ["GOOG", "GOOGL"]},
             "FB": {"name": "Facebook, Inc.", "tickers": ["FB", "META"]},
             "AMZN": {"name": "Amazon.com", "tickers": ["AMZN"]},
             "TMUS": {"name": "T-Mobile US", "tickers": ["TMUS"]},
             "COST": {"name": "Costco", "tickers": ["COST"]},
             "INTC": {"name": "Intel Corporation", "tickers": ["INTC"]}}
EXTRAS = {"GOOGL": ["Google", "YouTube"], "FB": ["Meta", "Instagram"], "AAPL": ["iPhone", "Tim Cook"]}


def test_name_forms():
    assert name_forms("Apple Inc.") == {"Apple Inc.", "Apple"}
    assert "Facebook" in name_forms("Facebook, Inc.") and "Amazon" in name_forms("Amazon.com")
    assert "T-Mobile" in name_forms("T-Mobile US") and "Intel" in name_forms("Intel Corporation")


def test_scrub_replaces_everything_and_maps_back():
    an = Anonymizer(COMPANIES, extras=EXTRAS)
    text = ("Company: Apple Inc. (ticker AAPL). Apple's iPhone sales; Tim Cook said. GOOG and GOOGL rose as Google "
            "and YouTube grew; Alphabet Inc. filed. Facebook rebrands as Meta (META); Instagram. AMZN: Amazon.com and "
            "Amazon. T-Mobile US (TMUS) vs T-Mobile. Intel Corporation, Intel. Costco (COST) cut cost; costs rose.")
    out = an.scrub(text)
    assert an.leaks(out) == [], an.leaks(out)
    assert "cut cost; costs rose" in out                         # lower-case words are not tickers
    assert f"Company {an.aliases['AAPL']}'s" in out and f"(ticker {an.aliases['AAPL']})" in out
    assert an.real_id(an.aliases["GOOGL"]) == "GOOGL" and an.real_id(f"Company {an.aliases['FB']}") == "FB"
    assert an.real_id("XYZ") == "XYZ"


def test_aliases_are_stable_and_extendable():
    a = Anonymizer(COMPANIES, extras={})
    b = Anonymizer(dict(reversed(list(COMPANIES.items()))), extras={})
    assert a.aliases == b.aliases                                 # numbered in company-id order
    more = {**COMPANIES, "AAA": {"name": "Aaa Corp.", "tickers": ["AAA"]}}
    c = Anonymizer(more, a.aliases, extras={})                    # a later newcomer gets the next number
    assert {k: c.aliases[k] for k in a.aliases} == a.aliases and c.aliases["AAA"] == f"X{len(COMPANIES) + 1:03d}"
    json.dumps(c.aliases)


def test_leak_scan_finds_real_names():
    an = Anonymizer(COMPANIES, extras=EXTRAS)
    assert set(an.leaks("Google beat estimates; AAPL fell")) == {"Google", "AAPL"}
