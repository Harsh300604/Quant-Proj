"""Quick coverage check: how many index members on each rebalance date have no price data.

    python scripts\\coverage_quick.py

Uses the membership spells and raw/prices/missing.csv. Counts members, not index weight
(weights need shares outstanding, which come in Phase 2).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from quantagents.config import CONFIG_DIR, load_config  # noqa: E402
from quantagents.data.download.membership import members_at  # noqa: E402
from quantagents.paths import Paths  # noqa: E402


def coverage(spells: pd.DataFrame, missing: set[str], start: date, end: date) -> pd.DataFrame:
    rows = []
    for d in pd.date_range(start, end, freq="MS"):
        mem = members_at(spells, pd.Timestamp(d, tz="UTC"))
        miss = sorted(set(mem) & missing)
        rows.append({"month": d.date(), "members": len(mem), "no_prices": len(miss),
                     "pct": round(100 * len(miss) / max(len(mem), 1), 1), "tickers": ", ".join(miss)})
    return pd.DataFrame(rows)


def main() -> int:
    paths = Paths.from_config(load_config(CONFIG_DIR / "base.yaml"))
    spells = pd.read_csv(paths.derived / "ndx_membership.csv")
    for c in ("start_utc", "end_utc"):
        spells[c] = pd.to_datetime(spells[c], utc=True)
    mf = paths.raw / "prices" / "missing.csv"
    missing = set(pd.read_csv(mf)["ticker"]) if mf.exists() else set()
    cov = coverage(spells, missing, date(2015, 1, 1), date(2023, 12, 1))
    jan = cov[[m.month == 1 for m in cov["month"]]]
    print("Members with NO price data, on the first rebalance of each year:")
    for r in jan.itertuples():
        print(f"  {r.month}: {r.no_prices:>3} of {r.members} ({r.pct:>4}%)  {r.tickers}")
    worst = cov.loc[cov["pct"].idxmax()]
    print(f"\nWorst month: {worst['month']}  {worst['no_prices']} of {worst['members']} ({worst['pct']}%)")
    print(f"Average over 2015-2023: {cov['pct'].mean():.1f}% of members")
    return 0


if __name__ == "__main__":
    sys.exit(main())
