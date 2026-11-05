"""Data-quality report on the built DuckDB store (Phase 2 manual check).

    python scripts\\data_report.py

Prints a summary and writes CSVs to D:\\CreatED-Quant\\qa_store\\reports\\data_report\\ :
coverage per rebalance month, ticker-reuse problems, foreign filers missing an ADR ratio, and
our derived index vs QQQ per year.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402

from quantagents.config import CONFIG_DIR, load_config  # noqa: E402
from quantagents.data import quality  # noqa: E402
from quantagents.paths import Paths  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(CONFIG_DIR / "base.yaml"))
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2023-12-31")
    args = ap.parse_args(argv)
    paths = Paths.from_config(load_config(args.config))
    out = paths.reports / "data_report"
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(paths.duckdb_file), read_only=True)
    pd.set_option("display.width", 220)

    cov = quality.coverage_by_month(con, args.start, args.end)
    cov.to_csv(out / "coverage_by_month.csv", index=False)
    jan = cov[[d.month == 1 for d in cov["rebalance"]]]
    print("1. Coverage on the first rebalance of each year (companies):")
    print(jan[["rebalance", "members", "with_prices", "with_mcap", "with_fundamentals", "pct_missing_prices"]]
          .to_string(index=False))
    worst = cov.loc[cov["pct_missing_prices"].idxmax()]
    flag = worst["pct_missing_prices"] > 100 * quality.MISSING_RED_FLAG
    print(f"   Max % of members missing prices on any rebalance: {worst['pct_missing_prices']}% "
          f"({worst['rebalance']}){'  <-- RED FLAG (> 2%)' if flag else ''}")

    reuse = quality.ticker_reuse(con)
    reuse.to_csv(out / "ticker_reuse.csv", index=False)
    print(f"\n2. Price series that do not cover the index period ({len(reuse)}):")
    print(reuse.to_string(index=False) if len(reuse) else "   none")

    ff = quality.foreign_filers(con)
    ff.to_csv(out / "foreign_filers.csv", index=False)
    missing_ratio = ff[ff["ordinary_per_ads"].isna()]
    print(f"\n3. Foreign filers (20-F/40-F): {len(ff)}; without an ADR ratio in reference\\adr_ratios.csv: "
          f"{len(missing_ratio)}")
    if len(missing_ratio):
        print("   " + ", ".join(missing_ratio["company_id"]))

    iv = quality.index_vs_benchmark(con, "QQQ")
    iv.to_csv(out / "index_vs_qqq.csv", index=False)
    print("\n4. Our derived index vs QQQ (total return):")
    if len(iv):
        show = iv.copy()
        for c in ("index_return", "benchmark_return", "difference", "tracking_error"):
            show[c] = (100 * show[c]).round(2).astype(str) + "%"
        print(show.to_string(index=False))
        print(f"   Average yearly tracking error: {100 * iv['tracking_error'].mean():.2f}%")
    else:
        print("   no data")
    print(f"\nCSV files: {out}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
