"""Run every downloader in order, resumably.

    python -m quantagents.data.download.run_all --pilot      # 5 stocks (configs/pilot.yaml)
    python -m quantagents.data.download.run_all --all        # every NASDAQ-100 member 2014-2023
    python -m quantagents.data.download.run_all --all --only prices,news

Everything is written under the storage root (D:\\CreatED-Quant\\qa_store\\raw\\).
Re-running skips files that are already complete, so a stopped download can just be restarted.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from quantagents.config import CONFIG_DIR, Config, load_config
from quantagents.data.companies import build_company_map, ticker_names, to_company_snapshots
from quantagents.data.download.base import Manifest
from quantagents.data.download.edgar import SecEdgar
from quantagents.data.download.factors import FredRiskFree, FrenchFactors
from quantagents.data.download.membership import (
    WikipediaMembership, build_spells, load_manual_changes, members_at, removed_members,
    save_spells, snapshot_counts,
)
from quantagents.data.download.news import AlpacaNews
from quantagents.data.download.prices import BENCHMARKS, YFinancePrices, load_aliases
from quantagents.env_secrets import load_secrets
from quantagents.logs import setup_logging
from quantagents.paths import Paths, configure_third_party_caches

log = logging.getLogger("quantagents.download")

SOURCES = ["membership", "prices", "edgar", "news", "factors", "riskfree"]
PRICE_BUFFER_DAYS = 100   # prices after the end date, to measure 3-month view outcomes
NEWS_LOOKBACK_DAYS = 45   # news before the start date, for the first memos


def price_window(cfg: Config) -> tuple[date, date]:
    return cfg.dates.warmup_start, min(cfg.dates.end + timedelta(days=PRICE_BUFFER_DAYS), date.today())


def news_window(cfg: Config) -> tuple[date, date]:
    return max(date(2015, 1, 1), cfg.dates.start - timedelta(days=NEWS_LOOKBACK_DAYS)), cfg.dates.end


def universe_tickers(cfg: Config, spells: pd.DataFrame | None) -> list[str]:
    """Pilot: the configured tickers. Full: every ticker that was a member at any point."""
    if cfg.universe.tickers:
        return list(cfg.universe.tickers)
    if spells is None or spells.empty:
        raise RuntimeError("membership is empty; run the membership download first")
    start = pd.Timestamp(cfg.dates.warmup_start, tz="UTC")
    end = pd.Timestamp(cfg.dates.end, tz="UTC")
    m = (spells["start_utc"] <= end) & (spells["end_utc"].isna() | (spells["end_utc"] > start))
    return sorted(spells.loc[m, "ticker"].unique())


def pick_removed_member(cfg: Config, spells: pd.DataFrame, prices: YFinancePrices,
                        exclude: list[str]) -> str | None:
    """First (alphabetical) member at the start that left before the end and has Yahoo data."""
    cands = removed_members(spells, pd.Timestamp(cfg.dates.start, tz="UTC"),
                            pd.Timestamp(date(2023, 12, 31), tz="UTC"))
    p0, p1 = price_window(cfg)
    for tk in cands:
        if tk in exclude:
            continue
        if prices.download([tk], p0, p1).get(tk) is not None:
            return tk
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pilot", action="store_true", help="download for the 5 pilot stocks")
    g.add_argument("--all", action="store_true", help="download for every historical member")
    ap.add_argument("--config", help="config file (default: pilot.yaml or base.yaml)")
    ap.add_argument("--only", help=f"comma-separated subset of {SOURCES}")
    args = ap.parse_args(argv)

    cfg = load_config(args.config or CONFIG_DIR / ("pilot.yaml" if args.pilot else "base.yaml"))
    if args.all and cfg.universe.tickers:
        print("--all needs a config without universe.tickers (e.g. configs/base.yaml)")
        return 2
    paths = Paths.from_config(cfg).ensure()
    configure_third_party_caches(paths)
    setup_logging(paths.logs, "download")
    secrets = load_secrets()
    manifest = Manifest(paths.raw)
    wanted = SOURCES if not args.only else [s.strip() for s in args.only.split(",")]
    unknown = set(wanted) - set(SOURCES)
    if unknown:
        print(f"unknown source(s): {sorted(unknown)}; choose from {SOURCES}")
        return 2

    status: dict[str, str] = {}
    print(f"Storage: {paths.raw}")

    # 1. membership (always needed to know which tickers to fetch)
    membership = WikipediaMembership.create(paths.raw, manifest, cfg.downloads.wikipedia_requests_per_second,
                                            cfg.downloads.membership_snapshot_days)
    spells = None
    names: dict[str, list[str]] = {}
    periods: dict[str, tuple[date, date]] = {}
    try:
        if "membership" in wanted:
            # full history so pilots can pick a removed member and the gateway has full coverage
            membership.download(cfg.dates.warmup_start, date(2023, 12, 31))
        snaps = membership.snapshots()
        if not snaps.empty:
            spells, warnings = build_spells(snaps, load_manual_changes())
            out = save_spells(spells, paths.derived)
            membership.unmatched.to_csv(paths.derived / "membership_unmatched_names.csv", index=False)
            # company level (decision D27): share classes and renames -> one company
            ok = snaps[(snaps["status"] == "ok") & snaps["ticker"].notna()]
            cmap = build_company_map(sorted(spells["ticker"].unique()), membership.link_pairs,
                                     load_aliases(), ok["ticker"].value_counts().to_dict())
            cmap.to_csv(paths.derived / "company_map.csv", index=False)
            cspells, _ = build_spells(to_company_snapshots(snaps, cmap), load_manual_changes())
            save_spells(cspells, paths.derived, "ndx_membership_companies.csv")
            merged = cmap[cmap["ticker"] != cmap["company_id"]]
            for d in (date(2015, 1, 2), date(2023, 12, 1)):
                print(f"  members (companies) on {d}: {len(members_at(cspells, pd.Timestamp(d, tz='UTC')))}")
            print(f"  companies: {cmap['company_id'].nunique()} (from {len(cmap)} tickers; "
                  f"{len(merged)} merged as share classes or renames -> derived\\company_map.csv)")
            # company names and membership periods, to find delisted companies in SEC EDGAR
            tn = ticker_names(membership.link_pairs)
            names = {r.ticker: r.all_names.split(" | ") for r in tn.itertuples()}
            tn.to_csv(paths.derived / "ticker_names.csv", index=False)
            for tk, g in spells.groupby("ticker"):
                end = g["end_utc"].max()
                periods[tk] = (g["start_utc"].min().date(),
                               date(2023, 12, 31) if g["end_utc"].isna().any() or pd.isna(end) else end.date())
            counts = snapshot_counts(snaps)
            bad = counts[counts["status"] != "ok"]
            counts.to_csv(paths.derived / "membership_snapshot_counts.csv", index=False)
            for w in warnings:
                log.warning(w)
            for d in (date(2015, 1, 2), date(2023, 12, 1)):
                n = len(members_at(spells, pd.Timestamp(d, tz="UTC")))
                print(f"  members (tickers) on {d}: {n}")
            print(f"  membership spells -> {out}  (snapshots needing review: {len(bad)})")
            status["membership"] = "OK" if bad.empty else f"OK, {len(bad)} snapshot(s) need review"
        elif "membership" in wanted:
            status["membership"] = "FAILED: no snapshots"
    except Exception as exc:
        log.exception("membership failed")
        status["membership"] = f"FAILED: {type(exc).__name__}: {exc}"

    prices = YFinancePrices(paths.raw, manifest)
    try:
        tickers = universe_tickers(cfg, spells)
    except RuntimeError as exc:
        print(f"Cannot choose tickers: {exc}")
        return 1
    if args.pilot and cfg.universe.add_removed_member and spells is not None:
        extra = pick_removed_member(cfg, spells, prices, tickers)
        if extra:
            tickers.append(extra)
            print(f"  pilot 5th stock (left the index later): {extra}")
        else:
            print("  WARNING: no removed member with Yahoo data found for the pilot")
    print(f"Tickers: {len(tickers)}")

    p0, p1 = price_window(cfg)
    n0, n1 = news_window(cfg)

    def run(name: str, fn, needs: tuple[str, ...] = ()) -> None:
        if name not in wanted:
            return
        missing = [s for s in needs if not secrets.has(s)]
        if missing:
            status[name] = f"SKIPPED: {', '.join(missing)} missing in .env"
            return
        try:
            fn()
            status[name] = "OK"
        except Exception as exc:
            log.exception("%s failed", name)
            status[name] = f"FAILED: {type(exc).__name__}: {exc}"

    def do_prices():
        res = prices.download(tickers + BENCHMARKS, p0, p1)
        miss = [t for t, p in res.items() if p is None]
        if miss:
            print(f"  prices: no Yahoo data for {len(miss)} ticker(s): {', '.join(miss[:15])}"
                  f"{' ...' if len(miss) > 15 else ''} (see raw/prices/missing.csv)")

    run("prices", do_prices)
    run("edgar", lambda: SecEdgar.create(paths.raw, manifest, secrets.get("SEC_USER_AGENT"),
                                         cfg.downloads.sec_requests_per_second).download(tickers, names, periods),
        needs=("SEC_USER_AGENT",))
    run("news", lambda: AlpacaNews.create(paths.raw, manifest, secrets.get("ALPACA_API_KEY"),
                                          secrets.get("ALPACA_SECRET_KEY"),
                                          cfg.downloads.alpaca_requests_per_minute).download(tickers, n0, n1),
        needs=("ALPACA_API_KEY", "ALPACA_SECRET_KEY"))
    run("factors", lambda: FrenchFactors.create(paths.raw, manifest).download())
    run("riskfree", lambda: FredRiskFree.create(paths.raw, manifest).download(p0, p1))

    summary = Manifest(paths.raw).summary().set_index("source")
    print("\nSummary")
    print(f"{'source':<12}{'files':>8}{'rows':>12}  status")
    for s in SOURCES:
        if s not in wanted and s not in summary.index:
            continue
        files = int(summary.loc[s, "files"]) if s in summary.index else 0
        rows = int(summary.loc[s, "rows"]) if s in summary.index else 0
        print(f"{s:<12}{files:>8}{rows:>12}  {status.get(s, 'not run')}")
    failed = [s for s, v in status.items() if v.startswith("FAILED")]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
