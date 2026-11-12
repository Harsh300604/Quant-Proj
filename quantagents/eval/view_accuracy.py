"""View accuracy (main plan Phase 7): how the committee's views turned out, after the fact.

For every decision of a run, each company's realised 3-month excess return over the benchmark
(same definition as the track record, D34). Then:
- by view (baseline: the multiplier; enhanced: the rating): count, average excess return, hit rate
  (an overweight/buy is right when the stock beat the benchmark; underweight/sell when it lagged);
- rank IC: for each decision date, the Spearman rank correlation between the view's strength and
  the realised excess return, averaged over dates (0 = no skill, 1 = perfect ranking).
No LLM calls. Data after the run's end are allowed here (this is evaluation, not a decision).

    python -m quantagents.eval.view_accuracy --run-id proto20_2021_base_dev
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from quantagents.agents.track_record import outcomes
from quantagents.config import CONFIG_DIR, load_config
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway
from quantagents.paths import Paths

ORDER = ["strong_sell", "sell", "hold", "buy", "strong_buy"]


def history_of(run_dir: Path) -> list[dict]:
    w = pd.read_csv(run_dir / "weights.csv")
    bench = {r: dict(zip(g["company_id"], g["benchmark"])) for r, g in w.groupby("rebalance")}
    out = []
    for f in sorted((run_dir / "decisions").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out.append({"rebalance": d["rebalance"], "views": d["views"], "labels": d.get("labels") or {},
                    "bench": bench.get(d["rebalance"], {})})
    return out


def score(row) -> float:
    """View strength for the rank IC: multiplier - 1 (baseline) or rating step x confidence (enhanced)."""
    if row["label"]:
        rating, conf = row["label"].split(" (")
        return (ORDER.index(rating) - 2) * float(conf.rstrip(")"))
    return row["multiplier"] - 1.0


def accuracy(df: pd.DataFrame) -> tuple[pd.DataFrame, float, int]:
    df = df.copy()
    enhanced = bool(df["label"].astype(bool).any())
    df["view"] = df["label"].str.split(" (", regex=False).str[0] if enhanced else df["multiplier"].map(lambda m: f"x{m:.2f}")
    df["score"] = df.apply(score, axis=1)
    df["hit"] = np.where(df["score"] > 0, df["excess"] > 0, np.where(df["score"] < 0, df["excess"] < 0, np.nan))
    g = df.groupby("view").agg(views=("excess", "size"), avg_excess=("excess", "mean"),
                               hit_rate=("hit", "mean"))
    order = ORDER if enhanced else sorted(g.index, key=lambda v: float(v[1:]))
    g = g.reindex([v for v in order if v in g.index])
    ics = []
    for _, d in df.groupby("made"):
        if d["score"].nunique() > 1 and len(d) > 2:
            ics.append(d["score"].rank().corr(d["excess"].rank()))
    return g, float(np.mean(ics)) if ics else float("nan"), len(ics)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--config", default=str(CONFIG_DIR / "base.yaml"))
    args = ap.parse_args(argv)
    paths = Paths.from_config(load_config(args.config))
    run_dir = paths.runs / args.run_id
    hist = history_of(run_dir)
    gw = Gateway(paths.duckdb_file)
    try:
        last = gw.con.execute("SELECT max(date) FROM prices").fetchone()[0]
        df = outcomes(gw, hist, cal.close_utc(cal.previous_trading_day(pd.Timestamp(last) + pd.Timedelta(days=1))),
                      3, include_neutral=True)
    finally:
        gw.close()
    if df.empty:
        print("no decision has a complete 3-month outcome yet")
        return 1
    table, ic, n = accuracy(df)
    lines = [f"View accuracy, run {args.run_id}: {len(df)} views with a complete 3-month outcome "
             f"({df['made'].nunique()} decisions)", "",
             "| view | views | average 3-month excess return | hit rate |", "|---|---:|---:|---:|"]
    lines += [f"| {v} | {int(r.views)} | {r.avg_excess:+.2%} | " + ("-" if pd.isna(r.hit_rate) else f"{r.hit_rate:.0%}") + " |"
              for v, r in table.iterrows()]
    lines += ["", f"Rank IC (Spearman, view strength vs realised excess return), average of {n} dates: {ic:+.3f}",
              "Hit rate: overweight/buy right if the stock beat the benchmark, underweight/sell right if it lagged."]
    text = "\n".join(lines)
    (run_dir / "view_accuracy.md").write_text(text + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
