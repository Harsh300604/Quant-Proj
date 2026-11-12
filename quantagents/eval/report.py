"""One command for the results of several stored runs (main plan Phase 6). NO LLM calls, no network.

    python -m quantagents.eval.report --runs proto20_2021_base_dev proto20_2021_enh_dev --name proto20_2021

Writes to <storage>/reports/<name>/:
- results.md / results.csv: one row per run plus the runs' benchmark (same companies at market weight),
  QQQ and ^NDX (reference only): returns, risk, Sharpe/Sortino/Calmar, active metrics, turnover,
  costs, ENT/ENB, Carhart alpha (Newey-West t-stat), bootstrap 90% intervals;
- growth_of_1.html: growth of $1 for every line;
- the view-accuracy table of each agents run;
- the honesty notes every report must print (implementation_plan_20.md, P6).
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
from pathlib import Path

import pandas as pd

from quantagents.config import CONFIG_DIR, load_config
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway
from quantagents.eval.factors import carhart, load_factors
from quantagents.eval.metrics import confidence_intervals, diversification, performance
from quantagents.eval.quick_report import svg_chart
from quantagents.eval.red_flags import riskfree_daily
from quantagents.paths import Paths

PALETTE = ["#2f6fb3", "#c4682b", "#7a4fb0", "#2e8b57", "#8c8c8c", "#b5a642", "#444444"]
NOTES = [
    "This is a 20-stock prototype: the universe is the 20 largest NASDAQ-100 companies on 4 Jan 2021, chosen "
    "with that day's data only. It does not show that anything beats the NASDAQ-100.",
    "The benchmark is the same companies at market weight; QQQ and ^NDX are shown for reference only.",
    "A short sample (36 months or less) gives alpha t-statistics little power: do not read significance into "
    "them unless the numbers support it. The 90% bootstrap intervals show how wide the uncertainty is.",
    "Names-hidden runs are a weak control for mega-caps: sector, size and figures still identify them (D44).",
    "The Carhart alpha of every line, the benchmark included, measures the 20 companies against the whole US "
    "market; it reflects which companies were chosen, not the committee's skill. The committee's skill is the "
    "ACTIVE alpha (portfolio minus benchmark).",
]


def label(run_id: str, summary: dict) -> str:
    v = summary.get("variant") or summary.get("strategy")
    return f"{run_id} ({v})"


def fmt(v, kind: str) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    if kind == "pct":
        return f"{v:+.2%}"
    if kind == "pct0":
        return f"{v:.2%}"
    if kind == "ci":
        return "-" if any(math.isnan(x) for x in v) else f"[{v[0]:+.2f}, {v[1]:+.2f}]"
    if kind == "cip":
        return "-" if any(math.isnan(x) for x in v) else f"[{v[0]:+.1%}, {v[1]:+.1%}]"
    return f"{v:.2f}"


def build(runs: list[str], name: str, cfg_path=None) -> Path:
    cfg = load_config(cfg_path or CONFIG_DIR / "base.yaml")
    paths = Paths.from_config(cfg)
    out = paths.root / "reports" / name
    out.mkdir(parents=True, exist_ok=True)
    navs, summaries, weights = {}, {}, {}
    for r in runs:
        d = paths.runs / r
        navs[r] = pd.read_csv(d / "nav.csv", index_col="date", parse_dates=True)
        summaries[r] = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        weights[r] = pd.read_csv(d / "weights.csv")
    first = navs[runs[0]]
    start, end = first.index[0], first.index[-1]
    if any(n.index[0] != start or n.index[-1] != end for n in navs.values()):
        raise ValueError("the runs cover different periods; compare runs of the same period only")

    gw = Gateway(paths.duckdb_file)
    try:
        t_end = cal.close_utc(end)
        rf = riskfree_daily(gw, t_end)
        lookback = (end - start).days + 10
        refs = {}
        for tk in ("QQQ", "^NDX"):
            q = gw.get_benchmark(tk, t_end, lookback_days=lookback)
            qr = pd.Series(q["ret"].to_numpy(), index=pd.DatetimeIndex(q["date"])).reindex(first.index).fillna(0.0)
            qr.iloc[0] = 0.0
            refs[f"{tk} (reference)"] = (1 + qr).cumprod()
        factors = load_factors(gw.con, start, end)
        ids = sorted({c for w in weights.values() for c in w["company_id"]})
        p = gw.get_prices(ids, t_end, lookback_days=(end - start).days + 400)
        rets = p.pivot_table(index="date", columns="company_id", values="ret")
        rets.index = pd.DatetimeIndex(rets.index)
    finally:
        gw.close()

    bench = first["benchmark_nav"]
    lines = {label(r, summaries[r]): navs[r]["nav"] for r in runs}
    lines["Benchmark (same companies, market weight)"] = bench
    lines.update(refs)
    rows = []
    for nm, nav in lines.items():
        run = next((r for r in runs if label(r, summaries[r]) == nm), None)
        perf = performance(nav, rf, bench if run else None)
        fac = carhart(nav.pct_change().dropna(), factors)
        row = {"series": nm, **perf, "alpha_annual": fac.get("alpha_annual"), "alpha_t": fac.get("alpha_t"),
               "beta_mkt": fac.get("beta_mkt_rf")}
        if run:
            s = summaries[run]
            act = carhart((nav.pct_change() - bench.pct_change()).dropna(), factors, active=True)
            ci = confidence_intervals(nav, bench, rf)
            row.update(avg_turnover=s.get("avg_turnover"), total_cost=s.get("total_cost"),
                       red_flags=len(s.get("red_flags", [])), active_alpha=act.get("alpha_annual"),
                       active_alpha_t=act.get("alpha_t"), **ci, **diversification(weights[run], rets))
        elif nm.startswith("Benchmark"):
            row.update({k: v for k, v in diversification(weights[runs[0]], rets).items() if k.startswith("benchmark")})
        rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(out / "results.csv", index=False)

    years = sorted({int(c.split("_")[1]) for c in table.columns if c.startswith("return_")})
    md = [f"# Results: {name}", "", f"Period {start.date()} to {end.date()}; runs: {', '.join(runs)}. "
          "No LLM calls were made to produce this report.", "",
          "| series | total | CAGR | " + " | ".join(str(y) for y in years) + " | vol | Sharpe | Sortino | max DD | Calmar |",
          "|---|---:|---:|" + "---:|" * len(years) + "---:|---:|---:|---:|---:|"]
    for _, r in table.iterrows():
        md.append(f"| {r.series} | {fmt(r.total_return, 'pct')} | {fmt(r.cagr, 'pct')} | "
                  + " | ".join(fmt(r.get(f'return_{y}'), 'pct') for y in years)
                  + f" | {fmt(r.volatility, 'pct0')} | {fmt(r.sharpe, 'num')} | {fmt(r.sortino, 'num')} | "
                    f"{fmt(r.max_drawdown, 'pct')} | {fmt(r.calmar, 'num')} |")
    md += ["", "**Against the benchmark** (runs only)", "",
           "| run | active return | tracking error | information ratio (90% CI) | Sharpe 90% CI | active return 90% CI | "
           "turnover / month | costs | red flags |", "|---|---:|---:|---|---|---|---:|---:|---:|"]
    for _, r in table[table["series"].isin([label(x, summaries[x]) for x in runs])].iterrows():
        md.append(f"| {r.series} | {fmt(r.active_return, 'pct')} | {fmt(r.tracking_error, 'pct0')} | "
                  f"{fmt(r.information_ratio, 'num')} {fmt(r.information_ratio_ci, 'ci')} | {fmt(r.sharpe_ci, 'ci')} | "
                  f"{fmt(r.active_return_ci, 'cip')} | {fmt(r.avg_turnover, 'pct0')} | {fmt(r.total_cost, 'pct0')} | "
                  f"{int(r.red_flags)} |")
    md += ["", "**Carhart 4-factor regression** (daily; alpha per year; Newey-West t-statistic)", "",
           "| series | alpha | t | market beta | active alpha vs benchmark | t |", "|---|---:|---:|---:|---:|---:|"]
    for _, r in table.iterrows():
        md.append(f"| {r.series} | {fmt(r.alpha_annual, 'pct')} | {fmt(r.alpha_t, 'num')} | {fmt(r.beta_mkt, 'num')} | "
                  f"{fmt(r.get('active_alpha'), 'pct')} | {fmt(r.get('active_alpha_t'), 'num')} |")
    md += ["", "**Diversification** (average over rebalances; ENT = entropy of weights, ENB = effective number of bets)", "",
           "| series | ENT | ENB |", "|---|---:|---:|"]
    for _, r in table.iterrows():
        e, b = (r.get("ent"), r.get("enb")) if not r.series.startswith("Benchmark") else \
            (r.get("benchmark_ent"), r.get("benchmark_enb"))
        if e is not None and not (isinstance(e, float) and math.isnan(e)):
            md.append(f"| {r.series} | {fmt(e, 'num')} | {fmt(b, 'num')} |")
    for r in runs:
        va = paths.runs / r / "view_accuracy.md"
        if va.exists():
            md += ["", f"**View accuracy: {r}**", ""] + va.read_text(encoding="utf-8").splitlines()[2:]
    md += ["", "**Read with care**", ""] + [f"- {n}" for n in NOTES]
    (out / "results.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    colors = {k: PALETTE[i % len(PALETTE)] for i, k in enumerate(lines)}
    legend = "".join(f'<span><i style="background:{colors[k]}"></i>{html.escape(k)}</span>' for k in lines)
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width, initial-scale=1'><title>{html.escape(name)} growth</title><style>"
            "body{font:14px system-ui,sans-serif;margin:24px 16px;background:#fbfaf7;color:#1f2328}"
            "@media (prefers-color-scheme: dark){body{background:#16181b;color:#e8e6e1}}"
            "main{max-width:800px;margin:auto}svg{width:100%;height:auto}svg text{fill:#7a828a;font-size:11px}"
            ".grid{stroke:#d9dcd5}.legend span{margin-right:14px;font-size:12px;display:inline-block}"
            ".legend i{display:inline-block;width:12px;height:3px;margin-right:6px;vertical-align:middle}"
            f"</style></head><body><main><h1>Growth of $1: {html.escape(name)}</h1><div class='legend'>{legend}</div>"
            f"{svg_chart(lines, colors=colors)}</main></body></html>")
    (out / "growth_of_1.html").write_text(page, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--name", required=True, help="report folder name under <storage>/reports/")
    ap.add_argument("--config", help="any config with the right storage root (default base.yaml)")
    args = ap.parse_args(argv)
    out = build(args.runs, args.name, args.config)
    sys.stdout.reconfigure(encoding="utf-8")
    print((out / "results.md").read_text(encoding="utf-8"))
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
