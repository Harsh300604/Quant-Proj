# Implementation plan: 20-stock prototype track ("proto20")

**Status:** approved by the user on 6 Nov 2026. Decisions D38–D45 are in `decisions_20.md`; current state is in `memory_20.md`; the dev-chat prompt is in `handoff_20.md`.

**What this is:** a first complete version of the whole project, built and run on **20 stocks**, so the student has real results to show the professor before the full 100-stock run.

**What this is not:** a replacement for the main plan. `implementation_plan.md`, `decisions.md`, `memory.md` and `handoff.md` stay unchanged and remain the plan for the full run, which follows once Norgate data arrives (D26). Everything built here must also work for the full universe: **nothing is hard-coded to 20 stocks or to 2021–2023** (D45).

---

## 1. The prototype in one table

| Item | Prototype (proto20) | Full run (main plan) |
|---|---|---|
| Universe | **20 largest NASDAQ-100 companies by market cap at the close of 2021-01-04**, fixed for the period (D39) | Historical NASDAQ-100 members on each date |
| Period | **Jan 2021 – Dec 2023, 36 monthly rebalances** (D40); data warm-up from 2014 | Jan 2015 – Dec 2023, 108 rebalances |
| Benchmark used for constraints and active metrics | **Cap-weighted index of the same 20 companies** ("proto20 index"), total return (D41) | Derived NASDAQ-100 cap weights |
| Shown for reference only | QQQ and ^NDX | QQQ and ^NDX (main benchmarks) |
| Committee views | **All 20** (no selection step, no per-sector cap) (D42) | Up to 20 of ~100, at most 3 per sector |
| Variants | Baseline, enhanced (Black-Litterman), names-hidden optional (D44) | Baseline, enhanced, names-hidden |
| Needs Norgate? | **No** | Yes (D26) |
| Funding | Dev tier on the personal key (Stage 0); paper-tier runs in Stage 1 (D43) | Stages 1–2 |

**The claim it supports:** "On the 20 largest NASDAQ-100 companies, 2021–2023, this is how the agent baseline and the Black-Litterman enhancement compare with simply holding those 20 at market weight."

**The claim it does not support:** "We beat the NASDAQ-100." The poster and every report must call this a **20-stock prototype**.

---

## 2. Why these choices

- **Top 20 by market cap on the start date, not hand-picked.**
  - Picking from the ~60 companies that stayed in the index throughout uses hindsight, because it means knowing who survived.
  - A rule applied on the start date uses only information known at that time, and it's easy to explain.
  - The largest companies almost never lack free data.
- **2021–2023.**
  - It's the paper's own test period, so our table sits next to its Table 2.
  - Starting in 2015 would need Norgate: the 2015 top 20 includes Celgene, Express Scripts and Walgreens, which are all on the missing list.
- **Benchmark = the same 20 stocks.** Survivorship then affects both sides of every comparison equally, so baseline vs. enhanced vs. benchmark stays fair.

---

## 3. Phases

Each phase follows the main plan's working method:
1. Build, run the tests, then tick the boxes here and update `memory_20.md` (and `decisions_20.md` if anything is decided).
2. Commit and push, then stop.
3. Give the user what was built, the test results and the manual checks, then wait for confirmation.

Where a phase says "as in main Phase N", the file list, tasks and tests in `implementation_plan.md` apply unchanged. Only the differences are listed here.

| Phase | Name | Based on | API spend |
|---|---|---|---|
| P0 | Laptop preparation and universe check | Main Phase 2 manual checks | $0 |
| P1 | Phase 2 follow-ups and proto20 universe/benchmark | Main Phase 2 + new | $0 |
| P2 | LLM layer and research memo | Main Phase 3 (unchanged) | < $0.02 personal |
| P3 | Constraints, optimizer, backtest engine (custom benchmark) | Main Phase 4 | $0 |
| P4 | Full agent graph; pilot; proto20 2021 dev slice; forecast v1 → **Stage 0 gate** | Main Phase 5 | ≈ $0.4–0.5 personal |
| P5 | Black-Litterman, enhanced variant, anonymizer (dev tier) | Main Phase 7 (code only) | ≈ $0.1–0.3 personal |
| P6 | **Stage 1:** Sonnet pilot; evaluation; proto20 paper-tier runs | Main Phase 6 + 7 runs | Stage 1 (student key), forecast first |
| P7 | Professor pack | Main Phase 8 (subset) | $0 |
| → | Back to the main plan: Norgate import, full runs | `implementation_plan.md` Phase 6 onward | Stage 2 |

All dollar figures are planning estimates. The forecast at the end of P4 replaces them with measured numbers.

---

## P0: Laptop preparation and universe check (user, laptop)

**Goal:** the data store is built and checked, and the top-20 list on 2021-01-04 is trustworthy.

**Tasks:**
- [ ] Main Phase 2 manual checks 1–5 (`implementation_plan.md` → Phase 2 → Manual checks); output pasted to the dev chat
- [ ] Look at the top 30 by weight on 2021-01-04:
  ```powershell
  python -m quantagents.data.gateway --as-of 2021-01-04 --show universe
  ```
- [ ] **ADR ratios** (`reference/adr_ratios.csv`) filled at least for every foreign filer (20-F/40-F) in that top 30, e.g. ASML, PDD, JD, BIDU, NTES if present.
  - A missing ratio can make a market cap wrong by up to 10×, which would put the wrong company into the top 20.
  - The data report's section 3 lists the foreign filers.
- [ ] After ETL is rebuilt with the ratios, the top 20 match a sensible outside view. For example, the large names in the NASDAQ-100 in early January 2021 include Apple, Microsoft, Amazon, Alphabet, Facebook, Tesla and Nvidia. Discuss any surprise in the dev chat.
- [ ] Every one of the 20 shows `has_prices = True`.

---

## P1: Phase 2 follow-ups and the proto20 universe and benchmark

**Goal:** close main Phase 2, and add a universe rule and a custom benchmark that work for any N and any start date.

**Files:**
- Main Phase 2 follow-ups from `memory.md`:
  - ADX(14) and RVOL(20) indicators (D36), in `quantagents/data/etl.py`, with tests;
  - ticker-reuse fixes from the data report, if any.
- `quantagents/data/universe.py` (new):
  - `top_n_by_cap(gateway, as_of, n)` returns companies ranked by `get_index_weights(as_of)` among members with prices, ties broken by `company_id`. It is point-in-time by construction, because it goes through the gateway.
  - `fixed_universe(company_ids)`.
  - `resolve_universe(config, gateway)` returns the company list used by the run, written to `runs/<run_id>/universe.csv`.
- `quantagents/config.py`: extend the `universe` block, keeping the current fields and default behaviour:
  ```yaml
  universe:
    index: NDX
    mode: index_members        # index_members | tickers | top_n_by_cap
    tickers: null              # used when mode = tickers
    top_n: 20                  # used when mode = top_n_by_cap
    chosen_at: 2021-01-04      # trading day whose close defines the ranking
    keep_fixed: true           # the chosen list is held for the whole period
  ```
  Existing configs (`base.yaml`, `pilot.yaml`) must keep working with no edits: `tickers` set means `mode: tickers`.
- `quantagents/eval/benchmarks.py` (new): `custom_cap_index(gateway or store, companies, start, end)` gives daily weights (renormalised from `index_weights` to the chosen companies) and daily total return. It uses the same timing as `quality.index_vs_benchmark`: the weights at the close of t−1 apply to the returns on t.
- `reference/proto20_universe.csv`: the frozen list (company_id, name, sector, weight on 2021-01-04), produced by a script from the laptop's store and committed. It contains no licensed data, only names and weights derived from public filings.
- `scripts/proto20_universe.py`: prints and writes the frozen list. `--check` fails if the live rule no longer matches the frozen file.
- `configs/proto20.yaml`:
  ```yaml
  extends: base.yaml
  run_id: proto20
  dates: {warmup_start: 2014-01-01, start: 2021-01-01, end: 2023-12-31}
  universe: {index: NDX, mode: top_n_by_cap, top_n: 20, chosen_at: 2021-01-04, keep_fixed: true}
  benchmark: {mode: custom_cap_index}      # constraints and active metrics vs the same 20
  selection: {max_views: 20, max_per_sector: null}
  models: {tier: dev}
  budget: {key_label: personal, stage: stage0, run_budget_usd: 0.50, inr_per_usd: 88.0}
  ```
- `configs/proto20_2021.yaml`: the same, with `dates.end: 2021-12-31` (the Stage 0 slice).

**Tests:**
- `test_universe.py`:
  - `top_n_by_cap` on the synthetic store returns the right names;
  - it is deterministic, with stable ties;
  - a company that becomes large only after `chosen_at` is never chosen (leak test: rebuild the store with a cutoff at `chosen_at` and get the same list);
  - `keep_fixed` holds the list through the period;
  - the old configs still load.
- `test_custom_benchmark.py`:
  - weights sum to 1 every day;
  - the return equals a hand-computed two-stock example;
  - no weight uses data after t−1.

**Manual checks (laptop):**
```powershell
python -m quantagents.data.etl
python scripts\proto20_universe.py
python scripts\proto20_universe.py --check
pytest -q
```
**Pass:**
- 20 companies are printed with weights and sectors, and the list matches P0;
- `--check` prints OK;
- all tests pass.

---

## P2: LLM layer and research memo

As in **main Phase 3**, unchanged: client wrapper, response cache, cost ledger with key and stage budgets, 80% stops, memo schema, memos on the 5 pilot stocks on Haiku.

**Read the Claude API docs/skill before writing API code.**

**Addition:** one manual check runs memos for 3 of the proto20 companies on 2021-01-04, to confirm that 2021 news and fundamentals reach the memo. This costs about $0.01 and must be asked first.

---

## P3: Constraints, optimizer and backtest engine

As in **main Phase 4**, plus:
- `constraints.py` and `baseline_opt.py` take the **benchmark weight vector as an input**: either the NASDAQ-100 derived weights or the proto20 index. 0×–2× multiples and sector bands are measured against that vector.
- `engine/backtest.py` reads the universe from `resolve_universe` and the benchmark from config, and writes `universe.csv` and `benchmark_nav.csv` into the run folder.
- No-AI test strategies (hold benchmark weights, deterministic random tilts) run on proto20 2021–2023 for free.

**Tests:**
- Holding the proto20 index weights reproduces `custom_cap_index` returns within 1e-8 before costs.
- With ±2 pp sector bands, constraints on the 20-stock benchmark are always feasible on the synthetic store.
- If a real rebalance is infeasible, the run stops with a clear message. It doesn't loosen the constraints by itself: ask the user (D41 note).

**Manual check:**
```powershell
python -m quantagents.engine.backtest --config configs\proto20.yaml --strategy hold_benchmark --run-id proto20_hold
```
**Pass:** the NAV matches the proto20 index, minus about 10 bps of cost at the start.

---

## P4: Full agent graph, pilot and the Stage 0 gate

As in **main Phase 5** (D32–D35 included: simulated trading for Bob, risk stats for Dave, track-record memory, paper persona wording), with these changes:
- **Selection:** when the universe is at most `max_views` and `max_per_sector` is null, every company gets a view and the "one-liners for the rest" list is empty. `test_selection.py` gets this case.
- **Dave's risk stats and Bob's simulated trading** are computed against the configured benchmark (the proto20 index here).
- **The track record** starts empty in Jan 2021 and fills from April 2021, because only fully known 3-month outcomes count. The transcript says so.
- **Stage 0 slice:** `configs/proto20_2021.yaml`, baseline, dev tier, 12 rebalances. It replaces the main plan's "20 stocks × 12 months" slice at the same estimated cost of about $0.35, and must be **asked first**.
- **Cost forecast v1** (`docs/cost_forecast.md`) includes:
  - proto20 2021–2023 on the `paper` tier for baseline, enhanced and names-hidden;
  - the main full runs.
- **Stage 0 gate** as in the main plan's Funding stages section. The ask for Stage 1 is based on this forecast.

**Manual checks:** as in main Phase 5 (pilot run, rerun from cache, read a transcript), plus:
```powershell
python -m quantagents.engine.backtest --config configs\proto20_2021.yaml --strategy agents --variant baseline --run-id proto20_2021_base_dev
```
**Pass:**
- 12 rebalances complete;
- 12 transcripts, each with views on all 20 companies;
- the cost line is within the estimate;
- the red-flag checks are silent, or every flag is explained.

---

## P5: Black-Litterman, enhanced variant and anonymizer (code; dev tier only)

As in **main Phase 7**, files and tests only: `black_litterman.py`, `otto_enhanced_v1.txt` and the `EnhancedViews` schema, `anonymize.py` with a leak scan, and `view_accuracy.py`. Black-Litterman uses the proto20 index weights as the market prior.

Runs in this phase:
- the 5-stock pilot for enhanced and names-hidden, on the dev tier;
- optionally proto20 2021 enhanced on the dev tier, if the Stage 0 budget allows (asked first).

**Extra test:** Black-Litterman with no views returns the benchmark weights exactly. This is the "no view = market weight" property we explain to the parents.

---

## P6: Stage 1 runs and evaluation

**Starts only** after the user confirms that Stage 1 (about $20) is approved and the student key is in `.env`. Then set `budget.key_label: student` and `budget.stage: stage1`, following the README key swap checklist.

**Tasks:**
- [ ] Sonnet measurement pilot (thinking off vs. on), as in main Phase 6 (asked first)
- [ ] Evaluation code as in main Phase 6:
  - metrics with ENT/ENB;
  - Carhart regression with Newey-West;
  - bootstrap CIs;
  - `report.py` with no LLM calls.

  Active metrics are measured against the configured benchmark; QQQ and ^NDX are added as reference rows.
- [ ] Re-issued forecast for the proto20 `paper` runs, then ask
- [ ] **proto20 baseline**, 2021–2023, `paper` tier (`configs/proto20_paper_baseline.yaml`, after the go-ahead)
- [ ] **proto20 enhanced**, 2021–2023, `paper` tier (after the go-ahead)
- [ ] **proto20 names-hidden enhanced** (optional, D44; only if the forecast fits Stage 1)
- [ ] Three-way table and growth-of-$1 chart: proto20 index, baseline, enhanced, (names-hidden), with QQQ and ^NDX as reference lines

**Honesty notes the report must print:**
- 36 months is a short sample, so alpha t-stats have low power. Don't claim significance without the numbers.
- Survivorship: the universe was chosen on 2021-01-04 from that day's data, so there's no hindsight in the choice. Results are not comparable to the full NASDAQ-100.
- Names-hidden on 20 mega-caps is a weak control, because descriptions like "large-cap consumer electronics" identify the company. It is labelled as such (D44).

If the forecast shows that Stage 1 can't cover all proto20 runs, stop and ask. Don't shorten the period or drop a variant without the user's approval.

---

## P7: Professor pack

**Goal:** everything the student needs to present the prototype, produced from stored runs with **no LLM calls**.

**Files:** `reports/proto20/` on D:, plus `docs/proto20_summary.md` in the repo (numbers only, no licensed data):
- results table (CSV and markdown) with ENT/ENB, and a 2021–2023 column set next to the paper's Table 2;
- growth-of-$1 chart (PNG);
- architecture diagram;
- one sample transcript (markdown);
- view accuracy by rating;
- a limitations list (the honesty notes above);
- "next step: full 100-stock run 2015–2023".

**Manual check:** the user and the student read `docs/proto20_summary.md` and confirm it can be shown to the professor.

---

## After the prototype

Go back to `implementation_plan.md`, Phase 6 onward:
- Norgate import (D26);
- the full `paper` baseline;
- the enhanced and names-hidden full runs (Stage 2).

The proto20 code paths stay. `configs/proto20*.yaml` remain runnable for regression checks.
