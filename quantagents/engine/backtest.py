"""Backtest engine: the monthly loop around a strategy (brief section 6).

    python -m quantagents.engine.backtest --config configs\\proto20.yaml --strategy hold_benchmark --run-id proto20_hold
    python -m quantagents.engine.backtest --config configs\\proto20_2021.yaml --strategy random --run-id rnd_check

Each month: decide at the close of the first trading day (the strategy sees a gateway frozen at
that moment), trade at the next open with 10 bps per unit of turnover, mark to market daily
until the next rebalance. A checkpoint is written after every month, so a stopped run resumes
where it left off (rerun the same command). Outputs in D:\\...\\qa_store\\runs\\<run_id>\\:
nav.csv, benchmark_nav.csv, weights.csv, rebalances.csv, universe.csv, summary.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from quantagents.config import CONFIG_DIR, Config, load_config
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway
from quantagents.data.universe import resolve_universe
from quantagents.engine.accounting import Book, simulate
from quantagents.engine.strategies import Context, make_strategy
from quantagents.eval.benchmarks import custom_cap_index, renormalise
from quantagents.eval.red_flags import check_run, format_flags, riskfree_daily
from quantagents.paths import Paths
from quantagents.portfolio.constraints import ConstraintSet

log = logging.getLogger("quantagents.backtest")
CHECKPOINT = "checkpoint.json"


class StopRequested(RuntimeError):
    """Raised by ``stop_after`` (tests): behaves like a run killed after N months."""


def fingerprint(cfg: Config, strategy: str, seed: int, variant: str | None = None) -> str:
    raw = Path(cfg.source_file).read_bytes() if cfg.source_file else b""
    extra = f"|{variant}" if strategy == "agents" else ""
    return hashlib.sha256(raw + f"|{strategy}|{seed}|{cfg.model_dump_json()}{extra}".encode()).hexdigest()[:16]


def wide(prices: pd.DataFrame, col: str) -> pd.DataFrame:
    t = prices.pivot_table(index="date", columns="company_id", values=col)
    t.index = pd.DatetimeIndex(t.index)
    return t


def run(cfg: Config, strategy_name: str, run_id: str, seed: int = 0, fresh: bool = False,
        stop_after: int | None = None, strategy=None, quiet: bool = False, variant: str | None = None) -> dict:
    paths = Paths.from_config(cfg)
    run_dir = paths.runs / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    variant = variant or cfg.variant
    strat = strategy or make_strategy(strategy_name, seed, cfg=cfg, run_id=run_id, run_dir=run_dir, variant=variant)
    fp = fingerprint(cfg, strategy_name, seed, variant)
    say = (lambda *a: None) if quiet else print

    gw = Gateway(paths.duckdb_file)                    # the engine's own view: realised prices
    dgw = Gateway(paths.duckdb_file)                   # the strategy's view: frozen at each decision
    try:
        universe = resolve_universe(cfg, gw, run_dir)
        rebs = cal.rebalance_dates(cfg.dates.start, cfg.dates.end)
        all_days = cal.trading_days(rebs[0], cfg.dates.end)
        exec_days = [cal.next_trading_day(d) for d in rebs]

        state = {"next": 0, "book": Book(cash=1.0).to_json(), "nav": {}, "log": [], "weights": [], "prior_report": None}
        ck = run_dir / CHECKPOINT
        if ck.exists() and not fresh:
            saved = json.loads(ck.read_text(encoding="utf-8"))
            if saved.get("fingerprint") == fp:
                state = saved
                say(f"resuming from checkpoint: {state['next']} of {len(rebs)} rebalances done")
            else:
                say("checkpoint is from a different config or strategy: starting again")
        state.setdefault("history", [])           # past views (track record, D34)
        state.setdefault("checks", [])            # latest gateway read per decision (red flag 6)
        book = Book.from_json(state["book"])
        navs = {pd.Timestamp(k): v for k, v in state["nav"].items()}
        if not navs:
            navs[pd.Timestamp(rebs[0])] = 1.0

        for i in range(state["next"], len(rebs)):
            day, t = rebs[i], cal.as_of_for(rebs[i])
            dgw.freeze_at = t
            companies = universe.at(dgw, t)
            u = dgw.get_universe(t).set_index("company_id")
            w_all = dgw.get_index_weights(t).set_index("company_id")["weight"]
            have = [c for c in companies if c in w_all.index]
            bench = renormalise(w_all, have)
            sectors = u["sector"].reindex(bench.index).fillna("Unknown")
            cs = ConstraintSet.from_config(cfg, bench, sectors)
            ctx = Context(t, pd.Timestamp(day), dgw, cfg, list(bench.index), bench, sectors, cs, book.weights(),
                          state["prior_report"], list(state["history"]))
            dgw.calls.clear()
            decision = strat.decide(ctx)
            w = decision.weights.reindex(list(cs.companies)).fillna(0.0)
            bad = cs.violations(w.to_numpy())
            if bad:
                raise RuntimeError(f"{day.date()}: decision breaks the constraints: {bad[:5]}")
            if dgw.max_as_of is not None and dgw.max_as_of > t:
                raise RuntimeError(f"{day.date()}: the strategy read data after the decision time")
            state["checks"].append({"rebalance": str(day.date()), "as_of": str(t),
                                    "max_read": str(dgw.max_as_of) if dgw.max_as_of is not None else "",
                                    "gateway_calls": len(dgw.calls)})
            if "views" in decision.report:
                state["history"].append({"rebalance": str(day.date()), "views": decision.report["views"],
                                         "labels": decision.report.get("labels") or {},
                                         "bench": {c: float(v) for c, v in bench.items()}})
            log.info("%s: %d companies, constraints OK", day.date(), len(w))

            # simulate from this rebalance's execution day to the day before the next one
            start = exec_days[i]
            end = (exec_days[i + 1] - pd.Timedelta(days=1)) if i + 1 < len(rebs) else pd.Timestamp(cfg.dates.end)
            days = all_days[(all_days >= start) & (all_days <= end)]
            names = sorted(set(w[w > 0].index) | set(book.holdings))
            px = gw.get_prices(names, cal.close_utc(days[-1]), lookback_days=(days[-1] - day).days + 10)
            px = px[pd.DatetimeIndex(px["date"]) >= day]
            nav, book, events = simulate(days, wide(px, "open"), wide(px, "close"), wide(px, "dividends"),
                                         {start: w[w > 0].to_dict()}, cfg.cost_bps, book)
            navs.update(nav.to_dict())
            reb = next(e for e in events if e["event"] == "rebalance")
            state["log"] += [{**e, "date": str(pd.Timestamp(e["date"]).date())} for e in events]
            state["weights"] += [{"rebalance": str(day.date()), "company_id": c, "weight": float(w[c]),
                                  "benchmark": float(bench[c]), "sector": sectors[c]} for c in w.index]
            llm = decision.report.get("llm")
            extra = (f"; LLM ${llm['usd']:.4f} ({llm['api_calls']} calls, {llm['cache_hits']} cache hits)"
                     if llm else "")
            if decision.report.get("failed_meetings") or decision.report.get("failed_memos"):
                extra += (f"; FAILED meetings {decision.report.get('failed_meetings')} memos "
                          f"{decision.report.get('failed_memos')}")
            say(f"{day.date()}: constraints OK; turnover {reb['turnover']:.1%}, cost ${reb['cost'] * 1e4:.2f} "
                f"per $10k; NAV {nav.iloc[-1]:.4f}{extra}")
            state.update(next=i + 1, book=book.to_json(), nav={str(k.date()): v for k, v in sorted(navs.items())},
                         prior_report=decision.report, fingerprint=fp)
            tmp = ck.with_suffix(".tmp")
            tmp.write_text(json.dumps(state), encoding="utf-8")
            tmp.replace(ck)
            if stop_after is not None and i + 1 >= stop_after and i + 1 < len(rebs):
                raise StopRequested(f"stopped after {i + 1} rebalances")

        nav = pd.Series(navs).sort_index().rename("nav")
        bench_companies = universe.fixed if universe.fixed is not None else \
            sorted(set(gw.con.execute("SELECT DISTINCT company_id FROM index_weights").df()["company_id"]))
        bi = custom_cap_index(gw, bench_companies, nav.index[1], nav.index[-1])
        bnav = pd.concat([pd.Series([1.0], index=[nav.index[0]]), (1 + bi.returns).cumprod()]).rename("benchmark_nav")
        out = pd.concat([nav, bnav], axis=1)
        out.index.name = "date"
        out.to_csv(run_dir / "nav.csv")
        bnav.to_frame().rename_axis("date").to_csv(run_dir / "benchmark_nav.csv")
        pd.DataFrame(state["weights"]).to_csv(run_dir / "weights.csv", index=False)
        pd.DataFrame(state["log"]).to_csv(run_dir / "rebalances.csv", index=False)
        pd.DataFrame(state["checks"], columns=["rebalance", "as_of", "max_read", "gateway_calls"]).to_csv(
            run_dir / "checks.csv", index=False)
        summary = summarise(out, pd.DataFrame(state["log"]), cfg, strategy_name, run_id)
        flags = check_run(run_dir, min_mult=cfg.constraints.min_multiple_of_index,
                          max_mult=cfg.constraints.max_multiple_of_index, band_pp=cfg.constraints.sector_band_pp,
                          riskfree=riskfree_daily(gw, cal.close_utc(nav.index[-1])))
        (run_dir / "red_flags.json").write_text(json.dumps(flags, indent=2), encoding="utf-8")
        summary["red_flags"] = flags
        summary["variant"] = variant if strategy_name == "agents" else None
        if hasattr(strat, "summary"):
            summary["llm"] = strat.summary()
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary
    finally:
        gw.close()
        dgw.close()


def summarise(out: pd.DataFrame, events: pd.DataFrame, cfg: Config, strategy: str, run_id: str) -> dict:
    r = out["nav"].pct_change().dropna()
    rb = out["benchmark_nav"].pct_change().dropna()
    years = (out.index[-1] - out.index[0]).days / 365.25
    cagr = lambda s: float(s.iloc[-1] ** (1 / years) - 1) if years > 0 else float("nan")  # noqa: E731
    reb = events[events["event"] == "rebalance"] if len(events) else events
    return {"run_id": run_id, "strategy": strategy, "benchmark_mode": cfg.benchmark.mode,
            "start": str(out.index[0].date()), "end": str(out.index[-1].date()), "rebalances": int(len(reb)),
            "total_return": float(out["nav"].iloc[-1] - 1), "benchmark_total_return": float(out["benchmark_nav"].iloc[-1] - 1),
            "cagr": cagr(out["nav"]), "benchmark_cagr": cagr(out["benchmark_nav"]),
            "tracking_error": float((r - rb).std() * np.sqrt(252)),
            "avg_turnover": float(reb["turnover"].mean()) if len(reb) else 0.0,
            "first_turnover": float(reb["turnover"].iloc[0]) if len(reb) else 0.0,
            "total_cost": float(reb["cost"].sum()) if len(reb) else 0.0}


def main(argv: list[str] | None = None) -> int:
    from quantagents.logs import setup_logging
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(CONFIG_DIR / "pilot.yaml"))
    ap.add_argument("--strategy", default="hold_benchmark", help="hold_benchmark | index | random | agents")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--fresh", action="store_true", help="ignore an existing checkpoint (cached LLM answers are still reused)")
    ap.add_argument("--variant", choices=["baseline", "enhanced"], help="agents only (default: the config's variant)")
    ap.add_argument("--stop-after", type=int, help="stop after N rebalances, as if the run were killed (resume test)")
    ap.add_argument("--names-hidden", action="store_true", help="agents only: the LLMs see aliases, not names (D44)")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.names_hidden:
        cfg = cfg.model_copy(update={"names_hidden": True})
    setup_logging(Paths.from_config(cfg).logs, "backtest")
    from quantagents.llm.client import LLMError
    from quantagents.llm.ledger import BudgetExceeded
    try:
        s = run(cfg, args.strategy, args.run_id, seed=args.seed, fresh=args.fresh, stop_after=args.stop_after,
                variant=args.variant)
    except StopRequested as e:
        print(f"{e}; rerun the same command (without --stop-after) to resume")
        return 0
    except (BudgetExceeded, LLMError) as e:
        print(f"STOPPED: {e}\nMonths already done are saved; rerunning the same command resumes from the "
              "checkpoint (answers already received come from the cache at no cost).")
        return 1
    print(f"\n{s['run_id']} ({s['strategy']}), {s['start']} to {s['end']}, {s['rebalances']} rebalances")
    print(f"  portfolio: total {s['total_return']:+.2%}, CAGR {s['cagr']:+.2%}")
    print(f"  benchmark ({s['benchmark_mode']}): total {s['benchmark_total_return']:+.2%}, CAGR {s['benchmark_cagr']:+.2%}")
    print(f"  tracking error {s['tracking_error']:.2%} a year; turnover first {s['first_turnover']:.0%}, "
          f"average {s['avg_turnover']:.1%}; total cost {s['total_cost']:.4%} of starting value")
    if s.get("llm"):
        print(f"  LLM this session: {s['llm']}")
    print(f"  {format_flags(s['red_flags'])}")
    print(f"  files: {Paths.from_config(cfg).runs / args.run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
