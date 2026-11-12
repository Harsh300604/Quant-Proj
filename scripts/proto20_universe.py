"""Freeze (or check) the proto20 universe: the top-N companies by derived cap weight (D39).

    python scripts\\proto20_universe.py            # print the list and write reference\\proto20_universe.csv
    python scripts\\proto20_universe.py --check    # OK if the live rule still gives the frozen list

The rule (N, chosen date) comes from the config (default configs\\proto20.yaml). It also prints
a short summary of the custom benchmark (the same companies at market weight) per year, with
QQQ as a reference row.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from quantagents.config import CONFIG_DIR, load_config  # noqa: E402
from quantagents.data import calendar as cal  # noqa: E402
from quantagents.data.gateway import Gateway  # noqa: E402
from quantagents.data.universe import resolve_universe  # noqa: E402
from quantagents.eval.benchmarks import custom_cap_index  # noqa: E402
from quantagents.paths import Paths  # noqa: E402

FROZEN = REPO / "reference" / "proto20_universe.csv"
COLUMNS = ["rank", "company_id", "name", "sector", "weight_in_index", "weight_in_universe", "chosen_at"]


def live_table(cfg, gw: Gateway) -> pd.DataFrame:
    t = resolve_universe(cfg, gw).table.copy()
    t = t.rename(columns={"weight": "weight_in_index"})
    t["weight_in_universe"] = t["weight_in_index"] / t["weight_in_index"].sum()
    return t[COLUMNS]


def check(live: pd.DataFrame, frozen_file: Path, tol: float = 1e-9) -> list[str]:
    """Differences between the live rule and the frozen file (empty list = OK)."""
    if not frozen_file.exists():
        return [f"{frozen_file} does not exist; run without --check first"]
    frozen = pd.read_csv(frozen_file, comment="#", dtype={"chosen_at": str})
    problems = []
    if str(frozen["chosen_at"].iloc[0]) != str(live["chosen_at"].iloc[0]):
        problems.append(f"chosen_at differs: frozen {frozen['chosen_at'].iloc[0]}, live {live['chosen_at'].iloc[0]}")
    if frozen["company_id"].tolist() != live["company_id"].tolist():
        gone = sorted(set(frozen["company_id"]) - set(live["company_id"]))
        new = sorted(set(live["company_id"]) - set(frozen["company_id"]))
        problems.append(f"companies or order differ (only frozen: {gone or '-'}; only live: {new or '-'})")
    else:
        diff = (frozen["weight_in_index"] - live["weight_in_index"]).abs().max()
        if diff > tol:
            problems.append(f"weights differ by up to {diff:.2e}")
    return problems


def benchmark_summary(cfg, gw: Gateway, companies: list[str]) -> pd.DataFrame:
    ci = custom_cap_index(gw, companies, cfg.dates.start, cfg.dates.end)
    q = gw.get_benchmark("QQQ", cal.close_utc(cal.previous_trading_day(pd.Timestamp(cfg.dates.end) + pd.Timedelta(days=1))),
                         lookback_days=(cfg.dates.end - cfg.dates.start).days + 10)
    q = q.set_index(pd.DatetimeIndex(q["date"]))["ret"]
    q = q[(q.index >= pd.Timestamp(cfg.dates.start)) & (q.index <= pd.Timestamp(cfg.dates.end))]
    rows = []
    for y in sorted(set(ci.returns.index.year)):
        r = ci.returns[ci.returns.index.year == y]
        rq = q[q.index.year == y]
        rows.append({"year": y, "days": len(r), "universe_index": f"{(1 + r).prod() - 1:.2%}",
                     "QQQ (reference)": f"{(1 + rq).prod() - 1:.2%}" if len(rq) else "n/a",
                     "days_with_a_missing_weight": int(ci.missing[pd.DatetimeIndex(ci.missing["date"]).year == y]
                                                       ["date"].nunique()) if len(ci.missing) else 0})
    return pd.DataFrame(rows)


def leak_check(config_path: str, cfg) -> int:
    """Point-in-time proof on the real store: delete everything after the chosen close, rebuild,
    and re-run the rule. The list (and weights) must be identical."""
    from quantagents.data.etl import build
    from quantagents.data.universe import as_of_close, top_n_by_cap
    t = as_of_close(cfg.universe.chosen_at)
    paths = Paths.from_config(cfg)
    out = paths.tmp / "leak_check.duckdb"
    print(f"Rebuilding the store as if today were {t} (this takes a few minutes) ...")
    build(config_path, out=out, cutoff_utc=t)
    a, b = Gateway(paths.duckdb_file), Gateway(out)
    try:
        full, cut = top_n_by_cap(a, t, cfg.universe.top_n), top_n_by_cap(b, t, cfg.universe.top_n)
    finally:
        a.close()
        b.close()
        out.unlink(missing_ok=True)
    same = full["company_id"].tolist() == cut["company_id"].tolist()
    diff = float((full["weight"] - cut["weight"]).abs().max())
    print(f"same companies in the same order: {same}; largest weight difference: {diff:.1e}")
    ok = same and diff < 1e-12
    print("LEAK CHECK OK: nothing after the chosen close changes the list" if ok else "LEAK CHECK FAILED")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(CONFIG_DIR / "proto20.yaml"))
    ap.add_argument("--check", action="store_true", help="compare the live rule with the frozen file")
    ap.add_argument("--frozen", default=str(FROZEN), help="frozen file (default reference\\proto20_universe.csv)")
    ap.add_argument("--no-benchmark", action="store_true", help="skip the benchmark summary")
    ap.add_argument("--leak-check", action="store_true",
                    help="rebuild the store as if today were the chosen close and confirm the same list (a few minutes)")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if cfg.universe.mode != "top_n_by_cap":
        print(f"universe.mode is {cfg.universe.mode!r}; this script is for top_n_by_cap")
        return 2
    if args.leak_check:
        return leak_check(args.config, cfg)
    gw = Gateway(Paths.from_config(cfg).duckdb_file)
    pd.set_option("display.width", 200)
    try:
        live = live_table(cfg, gw)
        frozen = Path(args.frozen)
        print(f"Top {cfg.universe.top_n} by derived market cap at the close of {cfg.universe.chosen_at}:")
        show = live.assign(weight_in_index=live["weight_in_index"].map("{:.2%}".format),
                           weight_in_universe=live["weight_in_universe"].map("{:.2%}".format))
        print(show.drop(columns="chosen_at").to_string(index=False))
        print(f"\nShare of the whole index: {live['weight_in_index'].sum():.1%}")
        if args.check:
            problems = check(live, frozen)
            for p in problems:
                print(f"MISMATCH: {p}")
            print("OK: the live rule matches the frozen list" if not problems else "CHECK FAILED")
            if problems:
                return 1
        else:
            frozen.parent.mkdir(parents=True, exist_ok=True)
            with open(frozen, "w", encoding="utf-8", newline="") as fh:
                fh.write("# proto20 universe (D39), written by scripts/proto20_universe.py from the local store.\n"
                         "# Names and weights derived from public SEC filings and prices; no licensed data.\n")
                live.to_csv(fh, index=False)
            print(f"\nWritten: {frozen}")
        if not args.no_benchmark:
            print(f"\nBenchmark: these {len(live)} companies at market weight, {cfg.dates.start} to {cfg.dates.end}")
            print(benchmark_summary(cfg, gw, live["company_id"].tolist()).to_string(index=False))
    finally:
        gw.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
