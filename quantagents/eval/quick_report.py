"""First tearsheet for one run: a self-contained HTML page (no LLM calls, no network, no extra
libraries). Growth of $1 for the portfolio, its benchmark and QQQ (reference), and a table of
basic statistics. The full evaluation (Carhart regression, bootstrap, ENT/ENB) comes in P6.

    python -m quantagents.eval.quick_report --run-id pilot_base_dev [--open]

Writes runs/<run_id>/quick_report.html.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
import webbrowser

import numpy as np
import pandas as pd

from quantagents.config import CONFIG_DIR, load_config
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway
from quantagents.eval.red_flags import riskfree_daily
from quantagents.paths import Paths

COLORS = {"Portfolio": "var(--c1)", "Benchmark": "var(--c2)", "QQQ (reference)": "var(--c3)"}


def stats(nav: pd.Series, rf: pd.Series | None, bench: pd.Series | None = None) -> dict:
    r = nav.pct_change().dropna()
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    rfa = rf.reindex(r.index).ffill().fillna(0.0) if rf is not None and len(rf) else 0.0
    ex = r - rfa
    dd = nav / nav.cummax() - 1
    out = {"Total return": nav.iloc[-1] / nav.iloc[0] - 1,
           "CAGR": (nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1 if years > 0 else float("nan"),
           "Volatility (a year)": r.std() * math.sqrt(252),
           "Sharpe (vs T-bills)": ex.mean() / ex.std() * math.sqrt(252) if ex.std() > 0 else float("nan"),
           "Max drawdown": dd.min()}
    if bench is not None:
        a = (r - bench.pct_change().reindex(r.index)).dropna()
        out["Tracking error"] = a.std() * math.sqrt(252)
        out["Information ratio"] = a.mean() / a.std() * math.sqrt(252) if a.std() > 0 else float("nan")
    return out


def svg_chart(lines: dict[str, pd.Series], width: int = 760, height: int = 320, colors: dict | None = None) -> str:
    colors = colors or COLORS
    pad_l, pad_r, pad_t, pad_b = 48, 12, 12, 28
    allv = pd.concat(lines.values())
    lo, hi = float(allv.min()), float(allv.max())
    span = (hi - lo) or 1.0
    t0, t1 = min(s.index[0] for s in lines.values()), max(s.index[-1] for s in lines.values())
    tspan = (t1 - t0).days or 1
    x = lambda d: pad_l + (d - t0).days / tspan * (width - pad_l - pad_r)  # noqa: E731
    y = lambda v: pad_t + (hi - v) / span * (height - pad_t - pad_b)  # noqa: E731
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Growth of $1">']
    for v in np.linspace(lo, hi, 5):
        parts.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                     f'<text x="{pad_l - 6}" y="{y(v) + 4:.1f}" text-anchor="end">${v:.2f}</text>')
    for yr in range(t0.year, t1.year + 2):
        d = pd.Timestamp(yr, 1, 1)
        if t0 <= d <= t1:
            parts.append(f'<text x="{x(d):.1f}" y="{height - 8}" text-anchor="middle">{yr}</text>')
    for name, s in lines.items():
        pts = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in s.items())
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{colors.get(name, "gray")}" stroke-width="2"/>')
    parts.append("</svg>")
    return "".join(parts)


def build(run_id: str, cfg_path=None) -> str:
    cfg = load_config(cfg_path or CONFIG_DIR / "base.yaml")
    run_dir = Paths.from_config(cfg).runs / run_id
    nav = pd.read_csv(run_dir / "nav.csv", index_col="date", parse_dates=True)
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    gw = Gateway(Paths.from_config(cfg).duckdb_file)
    try:
        end = cal.close_utc(nav.index[-1])
        q = gw.get_benchmark("QQQ", end, lookback_days=(nav.index[-1] - nav.index[0]).days + 10)
        rf = riskfree_daily(gw, end)
    finally:
        gw.close()
    qr = pd.Series(q["ret"].to_numpy(), index=pd.DatetimeIndex(q["date"])).reindex(nav.index).fillna(0.0)
    qr.iloc[0] = 0.0
    lines = {"Portfolio": nav["nav"], "Benchmark": nav["benchmark_nav"], "QQQ (reference)": (1 + qr).cumprod()}
    rows = {"Portfolio": stats(nav["nav"], rf, nav["benchmark_nav"]), "Benchmark": stats(nav["benchmark_nav"], rf),
            "QQQ (reference)": stats(lines["QQQ (reference)"], rf)}
    keys = list(rows["Portfolio"])
    fmt = lambda k, v: "–" if v is None or (isinstance(v, float) and math.isnan(v)) else (  # noqa: E731
        f"{v:.2f}" if k in ("Sharpe (vs T-bills)", "Information ratio") else f"{v:+.2%}" if k in ("Total return", "CAGR", "Max drawdown") else f"{v:.2%}")
    table = "<tr><th></th>" + "".join(f"<th>{html.escape(n)}</th>" for n in rows) + "</tr>" + "".join(
        "<tr><td>" + html.escape(k) + "</td>" + "".join(f"<td>{fmt(k, rows[n].get(k))}</td>" for n in rows) + "</tr>"
        for k in keys)
    legend = "".join(f'<span><i style="background:{COLORS[n]}"></i>{html.escape(n)}</span>' for n in lines)
    flags = summary.get("red_flags", [])
    flag_txt = "0 hits" if not flags else "<br>".join(html.escape(f"{f['flag']}: {f['detail']}") for f in flags[:20])
    title = f"{run_id}: {summary.get('strategy')}"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(run_id)} report</title>
<style>
:root {{ --bg:#fbfaf7; --fg:#1f2328; --muted:#5d6670; --line:#d9dcd5; --c1:#2f6fb3; --c2:#c4682b; --c3:#6c8a3c; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16181b; --fg:#e8e6e1; --muted:#9aa3ab; --line:#33373c;
  --c1:#6ea8e6; --c2:#e39a62; --c3:#9dbb6a; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; margin:0; padding:24px 16px; }}
main {{ max-width:800px; margin:0 auto; }} h1 {{ font-size:22px; margin:0 0 4px; }} p {{ color:var(--muted); margin:4px 0 16px; }}
svg {{ width:100%; height:auto; }} svg text {{ fill:var(--muted); font-size:11px; }} .grid {{ stroke:var(--line); }}
.legend span {{ margin-right:16px; font-size:13px; }} .legend i {{ display:inline-block; width:12px; height:3px; margin-right:6px; vertical-align:middle; }}
table {{ border-collapse:collapse; width:100%; margin-top:16px; font-variant-numeric:tabular-nums; }}
td, th {{ padding:6px 8px; border-bottom:1px solid var(--line); text-align:right; }} td:first-child, th:first-child {{ text-align:left; }}
.box {{ overflow-x:auto; }}
</style></head><body><main>
<h1>{html.escape(title)}</h1>
<p>{summary.get('start')} to {summary.get('end')}, {summary.get('rebalances')} rebalances; benchmark: {html.escape(str(summary.get('benchmark_mode')))};
average turnover {summary.get('avg_turnover', 0):.1%} a month; trading costs {summary.get('total_cost', 0):.2%} of the starting value.
A short sample: these numbers are not evidence of skill on their own.</p>
<div class="legend">{legend}</div>{svg_chart(lines)}
<div class="box"><table>{table}</table></div>
<p>Red flags: {flag_txt}</p>
<p>LLM: {html.escape(str(summary.get('llm', 'none')))}</p>
</main></body></html>"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Quick HTML tearsheet for one run")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--config", help="any config with the right storage root (default base.yaml)")
    ap.add_argument("--open", action="store_true", help="open the page in the browser")
    args = ap.parse_args(argv)
    page = build(args.run_id, args.config)
    cfg = load_config(args.config or CONFIG_DIR / "base.yaml")
    out = Paths.from_config(cfg).runs / args.run_id / "quick_report.html"
    out.write_text(page, encoding="utf-8")
    print(f"written: {out}")
    if args.open:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
