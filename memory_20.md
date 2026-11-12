# Memory: 20-stock prototype track (proto20)

Short, factual and always up to date for the prototype track. Update it at the end of every P-phase, before pushing.
The general project state (Phase 1 facts, environment, preferences, funding table) is in `memory.md` and still applies.

_Last updated: 2026-11-13 (P6 done: all three paper runs; waiting for the user's go-ahead for P7)._

## Where we are

| Item | State |
|---|---|
| Plan | `implementation_plan_20.md` (approved 6 Nov 2026); decisions D38–D55 in `decisions_20.md` |
| Main plan position | Phase 1 closed; Phase 2 done except ADR ratios for AZN/VIP/VOD and the delisted-price importer (both full run); Phases 3, 4 and 5 built (as proto20 P2, P3, P4) |
| Current P-phase | P0–P3 done (confirmed); P4 done (MVP checkpoint); P5 done; **P6 done 13 Nov** (baseline +42.61%, enhanced +42.94%, names-hidden +42.57% vs the same-20 index +42.84%; report in <storage>/reports/proto20_paper/); next is P7 (professor pack, $0) |
| Tests | 449 pass |
| Session | Local Claude Code session on the laptop: it runs tests, the ETL and small downloads itself; it asks before large downloads and before any API call |
| Branch | `claude/nifty-albattani-era22n` (push here only) |
| Funding | **MVP budget $40 on the student key** (D46): **$25.5651 spent** (spend log below); auto-stop at $32; hard cap $40. `configs/stages.yaml` has `proto20`; `base.yaml`, `pilot.yaml` and the proto20 configs use `student / proto20`. The key's Console limit is $200 (outer safety net only) |
| Norgate | Not needed for proto20 |

## proto20 facts

- Universe (frozen in `reference/proto20_universe.csv`, rule D39, `--check` OK on 12 Nov): AAPL, MSFT, AMZN, GOOGL, FB, TSLA, NVDA, PYPL, ADBE, CMCSA, NFLX, ASML, INTC, PEP, PDD, CSCO, AVGO, COST, QCOM, TMUS. These are 74.6% of the whole index; Apple is 19.9% of the 20. 21st is TXN.
- PDD is Consumer Discretionary (D47).
- Benchmark (same 20 at market weight, `quantagents/eval/benchmarks.py`), after the split fix of 12 Nov: +33.2% (2021), −37.6% (2022), +68.9% (2023); QQQ +27.4%, −32.6%, +54.9%. No missing weights on any day.
- No-AI runs (P3): `proto20_hold` +43.16% vs index +42.84% (tracking error 0.15%); `rnd_clean` random tilts +34.99% (turnover 63% a month, cost 2.47% over 3 years).
- Engine: `python -m quantagents.engine.backtest --config <cfg> --strategy hold_benchmark|random --run-id <id> [--fresh] [--stop-after N]` writes nav.csv, benchmark_nav.csv, weights.csv, rebalances.csv, universe.csv, summary.json and checkpoint.json to `runs/<id>/`. A strategy is `decide(Context) -> Decision`; its gateway is frozen at `as_of`.
- Code: `quantagents/data/universe.py` (`resolve_universe(cfg, gw).at(gw, as_of)`), `config.universe.mode` (index_members | tickers | top_n_by_cap), `config.benchmark.mode` (index | custom_cap_index).
- Period: 2021-01 to 2023-12, 36 rebalances (D40). Dev slice: 2021 only (`configs/proto20_2021.yaml`).
- All 20 get committee views (D42); `selection.max_per_sector: null`.
- No hard-coding of N or dates (D45). MVP first: build only what proto20 needs; log full-run items as deferred.
- Student guide: `docs/proto20_student_guide.md`, plain language, updated every phase (convert to docx at the end).
- Problems log: `docs/proto20_problems_log.md` (user's request, 13 Nov): every problem found and how it was solved, in plain language. Add a row whenever a problem is found or fixed.

## Spend log (MVP budget $40, stage `proto20`, key label `student`)

Source of truth: `python scripts\ledger_report.py` (ledger in `D:\CreatED-Quant\qa_store\cache\ledger.sqlite`).

| Date | Phase | What | API calls | USD | INR | Total so far | Approved by user |
|---|---|---|---|---|---|---|---|
| 2026-11-12 | P2 | 5 pilot memos, 2015-03-02, Haiku | 5 | 0.0031 | 0.27 | 0.0031 | yes |
| 2026-11-12 | P2 | 3 proto20 memos (AAPL, PDD, TMUS), 2021-01-04, Haiku | 3 | 0.0018 | 0.16 | 0.0049 | yes |
| 2026-11-12 | P2 | Rerun of both from the cache | 0 (8 hits) | 0.0000 | 0.00 | 0.0049 | — |
| 2026-11-12 | P4 | Pilot `pilot_base_dev`, 5 × 3, Haiku: 1st attempt (crashed in month 1), full run, rerun after the cache fix; then a rerun from the cache ($0) | 50 | 0.0390 | 3.43 | 0.0439 | yes |
| 2026-11-13 | P4 | 2021 dev slice `proto20_2021_base_dev`, 20 × 12, Haiku | 297 | 0.2717 | 23.91 | 0.3156 | yes |
| 2026-11-13 | P5 | Baseline pilot rerun after D50 (meant to be cache-only; it was not) | 11 | 0.0100 | 0.88 | 0.3256 | **no** (disclosed) |
| 2026-11-13 | P5 | Enhanced pilot, before and after D54 | 26 | 0.0238 | 2.09 | 0.3494 | yes |
| 2026-11-13 | P5 | Names-hidden enhanced pilot | 30 | 0.0210 | 1.85 | 0.3704 | yes |
| 2026-11-13 | P5 | 2021 enhanced slice `proto20_2021_enh_dev` | 60 | 0.1335 | 11.75 | 0.5039 | yes |
| 2026-11-13 | P6 | Sonnet thinking pilot (off and on, 5 × 3 each) | 30 | 0.4899 | 43.11 | 0.9938 | yes |
| 2026-11-13 | P6 | **proto20 baseline 2021–2023, paper tier** (`proto20_paper_baseline`) | 660 | 7.9639 | 700.82 | 8.9577 | yes |
| 2026-11-13 | P6 | **proto20 enhanced 2021–2023, paper tier** (`proto20_paper_enhanced`) | 180 | 8.1393 | 716.26 | 17.0970 | yes |
| 2026-11-13 | P6 | **proto20 names-hidden enhanced 2021–2023** (`proto20_paper_enh_hidden`) | 900 | 8.4681 | 745.20 | 25.5651 | yes |

Measured: a memo is about 2,700 input tokens (41% read from the prompt cache) and about 870 output tokens, about $0.0006 on Haiku.
Measured on the 2021 slice: the committee's cached briefing is about 22,300 tokens; each committee call outputs about 2,000 tokens; the committee prompt-cache read share is 69%. Per rebalance: $0.023 on the dev tier, about $0.23 projected on the paper tier (forecast v1, `docs/cost_forecast.md`).

## Agent graph facts (P4)

- `python -m quantagents.engine.backtest --config <cfg> --strategy agents --variant baseline --run-id <id>`. It writes memos/<date>/, transcripts/<date>.md, decisions/<date>.json, checks.csv (latest gateway read per decision) and red_flags.json, besides the P3 files. `--variant enhanced` raises "arrives in P5".
- Free briefing preview: `python -m quantagents.agents.graph --config configs\proto20.yaml --as-of 2021-04-01`. The briefing is about 2,700 tokens of Python numbers plus about 8,000 for 20 memo summaries.
- Five committee calls per month share one cached system block (committee rules + briefing) and ONE answer schema, `CommitteeAnswer` (D51). The pilot's committee prompt-cache read share was 65%.
- Otto's multipliers are 0–2 in steps of 0.25; the optimizer uses relative distance (D50, `constraints.projection`).
- The committee's `max_tokens` is 6000; reasons are capped at about 25 words.
- Quick report: `python -m quantagents.eval.quick_report --run-id <id> [--open]`. Forecast: `python scripts\cost_forecast.py`.
- Track record: a view made at rebalance t is scored at the first trading day 3 months later (Jan → Apr).
- Random-tilt reference after D50: `rnd_relative` +39.32% (turnover 55% a month, tracking error 3.21%).

## LLM layer facts (P2)

- `quantagents/llm/client.py`: `LLMClient(cfg, run_id).structured(node, model, system, user, schema, max_tokens, effort, thinking_off)` returns a `CallResult`. Response cache: `cache/responses.sqlite`. Ledger: `cache/ledger.sqlite`.
- Memo CLI: `python -m quantagents.agents.memo --config <cfg> --as-of <date> [--companies A,B] [--dry-run]` writes `runs/<run_id>/memos/<date>/<id>.{json,md,input.txt}`.
- Foreign filers' figures are in their own currency (CNY, EUR); P/E is computed only for USD.

## Next steps (in order)

1. **User:** the go-ahead for P7.
2. **P7 = professor pack ($0, no LLM calls):** `docs/proto20_summary.md` (numbers only); results table next to the paper's Table 2; growth-of-$1 chart (needs a PNG: matplotlib is not installed, so either a small install, asked first, or the existing SVG/HTML); architecture diagram; one sample transcript; view-accuracy tables; limitations list; "next step: full 100-stock run 2015–2023". Convert the student guide and the problems log to docx.
3. After proto20: back to `implementation_plan.md` (Norgate data, D26; the full runs need their own forecast and approval).

P6 results (13 Nov): baseline +42.61%, enhanced +42.94%, names-hidden enhanced +42.57%, same-20 index +42.84%, QQQ +34.94%. Every active-return interval includes zero; rank ICs +0.05 to +0.09. The committee was cautious (most views at the benchmark weight). Spend $25.57 of $40; $6.43 left before the stop.

## Deferred to the full run (not needed for proto20)

- ADR ratios for AZN, VIP, VOD; Baidu has no SEC share count after 2010; Baidu/Trip.com 2021 share subdivisions (ratio vs share-count units).
- Marvell predecessor filer (no MRVL weight before April 2021); Okta has no share count.
- MercadoLibre and eBay sectors (SIC → Industrials).
- 2015 derived index vs QQQ (tracking error 11.6%; mostly the delisted-price gap, D26).

## Open questions waiting on the user

- Check the ADR rows marked "check" in `reference/adr_ratios.csv`. JD = 2 and PDD = 4 matter for proto20.
- Items from `memory.md` (success criterion with the professor, poster rules) still apply.
