# QuantAgents: Implementation Plan

Source of truth: `PROJECT_BRIEF.md`. Final documentation phase: `HANDOFF_REQUIREMENTS.md`.
Running log of decisions, deviations and known issues: `decisions.md`.

Status legend: `[ ]` not started, `[x]` done, `[~]` partial or deviated (see the log).

---

## 0. How we work

### Who runs what

| Where | What runs there | Why |
|---|---|---|
| **Cloud session** (where I write code) | Writing code, automated tests on small synthetic data, git pushes | The data websites (Yahoo, SEC, Alpaca, Wikipedia, FRED, French library) are blocked from here (checked 4 Nov 2026). Its disk is temporary. |
| **Your Windows laptop, D: drive only** | Downloads, building the DuckDB data store, every API call, every backtest | Your data, keys and outputs stay on D:. |

The repo is cloned to `D:\CreatED-Quant\quantagents`. All data, caches, run outputs and logs go to `D:\CreatED-Quant\qa_store\`. This path is set in `configs/base.yaml` and can be changed there. Nothing large is committed to git.

### Every PowerShell session starts with these two lines

```powershell
cd D:\CreatED-Quant\quantagents
Set-ExecutionPolicy -Scope Process Bypass -Force; . .\scripts\env.ps1
```

`env.ps1` affects only that PowerShell window; nothing changes system-wide. It:
- sets `PIP_CACHE_DIR`, `UV_CACHE_DIR`, `TMP`, `TEMP`, `HF_HOME` and `npm_config_cache` to folders under `D:\CreatED-Quant\qa_store\`;
- activates `.venv`;
- refuses to run if the repo is not on D:.

### Spending rules

These are built into the ledger, not left to memory.

- **Personal key:**
  - `key_label: personal` and `budget_usd: 3.00`.
  - Every API call stops automatically at **$2.40 (80%)**.
  - Spend is shown in **USD and INR**. The default rate is ₹88 per $1 (`inr_per_usd` in config).
  - Only the `dev` tier (Haiku 5.5) is used, except for one Sonnet measurement pilot that you approve first.
- **Student key:** `key_label: student`, with the $150 project cap. Per-run budgets are in config.
- **Before any pilot or run:** I give you the estimated cost and wait for your go-ahead.

### Phase overview

| Phase | Week | Name | API spend |
|---|---|---|---|
| 1 | 1 | Setup, config, D:-drive scripts, downloaders | $0 |
| 2 | 2 | DuckDB data store, point-in-time gateway, leak tests, index and sector weights | $0 |
| 3 | 2 | LLM layer (cache, ledger, budgets) and research memo on 5 stocks | < $0.02 |
| 4 | 3 | Constraints, baseline optimizer, backtest engine | $0 |
| 5 | 3 | Full agent graph; 5-stock × 3-month pilot end to end; Sonnet thinking pilot | ≈ $0.05 Haiku + ≈ $0.6–1.2 Sonnet (asked first) |
| 6 | 4–5 | Full universe, evaluation, red flags, small-slice proofs, cost extrapolation, **baseline full run** | ≈ $0.4 personal; ≈ $16–20 student key |
| **MVP** | **end of week 5** | **Baseline vs. QQQ/^NDX table and chart** | |
| 7 | 6–7 | Enhancement (Black-Litterman), names-hidden mode, both full runs, comparison | ≈ $0.3 personal; ≈ $45–52 student key |
| 8 | 8 | Poster materials, README, sample transcript | $0 |
| 9 | Final | Handoff documentation (`HANDOFF_REQUIREMENTS.md`) | $0 |
| S1, S2 | Only if week 7 exits early | Stretch: bull/bear debate; no-AI ranking baseline | S1 ≈ $5–10; S2 $0 |

All dollar figures are planning estimates. Phase 6 replaces them with measured numbers.

---

## Recommendations adopted

You approved these on 4 Nov 2026. They are also recorded in `decisions.md`.

| # | Question | Decision |
|---|---|---|
| R1 | Membership source | **Free reconstruction.** Start from the current NASDAQ-100 list and replay Wikipedia's yearly change tables backwards, cross-checked against Nasdaq's annual reconstitution announcements. The result is a versioned file, `reference/ndx_membership.csv`, with one row per membership spell: ticker, start, end, source. The source sits behind an interface, so a paid dataset (Norgate, or CRSP via WRDS) can replace it later without code changes elsewhere. |
| R2 | Delisted prices | yfinance first. Any gaps can be filled from your own CSV files in `D:\CreatED-Quant\qa_store\manual_prices\` (same adapter interface). A member that still has no price data on a date is left out of that date's universe, and its index weight is redistributed. Every such case is logged, and a coverage report shows the % of index weight missing per date. A red flag is raised if more than 2% is missing. |
| R3 | Success criterion | Information ratio vs. the NASDAQ-100 and Carhart 4-factor alpha, alongside Sharpe, Sortino and max drawdown. **To be confirmed with the professor before any full-run result is shown.** All metrics are computed regardless. |
| R4 | Sector band | ±2 percentage points (`sector_band_pp: 2.0`). |
| R5 | Rating → return table | The brief's defaults (−6 / −3 / 0 / +3 / +6 %). Converted to a monthly figure by dividing by 3 (simple compounding); documented in `design.md`. |
| R6 | Index weights | Plain derived cap weights: shares outstanding from EDGAR (by filing date) × price, normalized across members. Nasdaq's capping rules are **not** copied. We validate by comparing our derived index with QQQ and report the tracking error. GOOG and GOOGL stay as two members, as in the real index, both in the same sector. |
| R7 | Sector and country | Sector comes from the SEC industry code (SIC), mapped to 11 GICS-like sectors in `reference/sic_to_sector.csv`. HQ country comes from the EDGAR business address. Neither is a GICS licence. Both are static per company. |
| R8 | Geography | Reported and checked (weights by country vs. the index), **not** enforced as a band. |
| R9 | Decision timing | `as_of` is the **close (4 pm ET) of the first trading day of the month**. News published before 4 pm that day counts. Trades happen at the next trading day's open. |
| R10 | Package layout | The brief's layout, placed inside one Python package `quantagents/` (e.g., `quantagents/data/gateway.py`). This avoids clashes with other libraries named `data` or `eval`. `configs/`, `tests/`, `scripts/`, `reference/` and `docs/` sit at the repo root. |

---

## Phase 1: Setup, config and downloaders (week 1)

**Status:** built and tested in the cloud session on 4 Nov 2026 (74 automated tests pass after the 5 Nov membership fixes, including a look-ahead guard). **Waiting for your manual checks on the laptop.**

**Goal:** the repo installs on D:, config loads, secrets are handled safely, and the downloads you run on your laptop have started.

**Files:**
- `pyproject.toml`, pinned `requirements.txt`, `.gitignore`, `.env.example`, `README.md` (with the key swap checklist)
- `scripts/env.ps1` and `scripts/setup.ps1`: per-session cache and temp folders on D:; venv on D:
- `configs/base.yaml`, `configs/pilot.yaml`, `configs/keys.yaml` (key label → budget)
- `quantagents/config.py`: pydantic-validated config loader; rejects `temperature`/`top_p`/`top_k` and non-allowed model IDs
- `quantagents/paths.py`: all storage paths come from config; refuses anything on C:; redirects yfinance, matplotlib and numba caches and temp files to D:
- `quantagents/env_secrets.py` (renamed from `secrets.py`, see D17): reads `.env` only; masks values in logs and errors
- `quantagents/logs.py`: logging with secret redaction
- `quantagents/data/download/`:
  - `base.py`: source interfaces, HTTP client, manifest
  - one module per source: `membership.py`, `prices.py`, `news.py`, `edgar.py`, `factors.py` (French factors and FRED `DTB3`; replaces the planned `riskfree.py`)
  - `run_all.py`
- `reference/`: `ticker_aliases.csv`, `cik_overrides.csv`, `ndx_changes_manual.csv`, `membership_bad_revisions.csv`, `wiki_title_tickers.csv` (hand-maintained corrections)
- `scripts/check_env.py`
- `decisions.md`, `memory.md`, `handoff.md`

**Tasks:**
- [x] Project skeleton and dependencies (**Python 3.12**; see D15)
- [x] `env.ps1` and `setup.ps1` (per-session environment variables only). *Not executable in the cloud session (no PowerShell); first real run is on your laptop.*
- [x] Config schema and loader; `base.yaml` and `pilot.yaml`. Pilot: AAPL, MSFT, NVDA, AMZN, plus one later-removed member, chosen automatically (the first alphabetically that has Yahoo data)
- [x] Path guard that rejects C: paths
- [x] `.env` loading and secret masking
- [x] Source interfaces: `MembershipSource`, `PriceSource`, `NewsSource`, `FundamentalsSource`
- [x] Downloaders. Each is resumable, rate-limited, shows a progress bar, saves raw files plus a manifest entry, and writes under the storage root only:
  - [x] Membership from Wikipedia page-history snapshots (1st and 15th of each month), with hand-correction files (D16), plus `--year` change report and `--diagnose`. Point-in-time guard (D21): tickers must appear in that day's own wikitext; 2016-18 read from the members template's own history
  - [x] yfinance prices for every ticker that was ever a member, plus QQQ and ^NDX; gaps listed in `raw\prices\missing.csv`; manual CSV fallback
  - [x] Alpaca news, 2015–2023 (headline and summary, not full text)
  - [x] SEC EDGAR company facts and submissions (acceptance times, SIC code, address); missing CIKs listed
  - [x] Kenneth French factors (FF3 and momentum, daily and monthly) and FRED `DTB3`
- [x] `check_env.py`
- [x] Decisions log and continuity files
- [ ] **Your manual checks below**

**Automated tests (74 passing):**
- `test_config.py`: base and pilot load; bad values are rejected; sampling parameters rejected; key budgets ($2.40 stop)
- `test_paths.py`: C: paths (including `/mnt/c`) raise an error; D: paths resolve; library caches and temp redirected
- `test_secrets.py`: a fake key never appears in log output, error messages or `repr`; only `.env` is read
- `test_membership_parse.py`: table and list parsing; spells from snapshots; manual corrections; change report
- `test_downloaders_offline.py`: every downloader against mocked responses (no network): files, manifest, resume, retries, missing lists
- `test_run_all_offline.py`: the full `--pilot` run end to end with all services mocked

**Manual checks (on your laptop):**

1. One-time setup. If Python 3.12+ isn't installed, first install Python 3.12.10 to `D:\Python312` (installer: https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe → "Customize installation" → set the location). An existing Python 3.11 can stay installed.
   ```powershell
   cd D:\CreatED-Quant
   git clone https://github.com/Harsh300604/Quant-Proj quantagents
   cd quantagents
   git checkout claude/nifty-albattani-era22n
   Set-ExecutionPolicy -Scope Process Bypass -Force; .\scripts\setup.ps1
   ```
   **Pass:** it ends with a green `Setup complete. venv: D:\CreatED-Quant\quantagents\.venv`. **Fail:** any red error, or a path starting with `C:` (other than the Python install itself, if it was already on C:).
2. Open `.env` in Notepad (`notepad .env`) and fill in `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `SEC_USER_AGENT` (e.g., `QuantAgents research yourname@example.com`) and `ANTHROPIC_API_KEY` (your personal key). Save. Then:
   ```powershell
   . .\scripts\env.ps1; python scripts\check_env.py
   ```
   **Pass:**
   - every line is `OK` or `INFO`;
   - the four keys say `present` (never the key itself);
   - repo, venv, storage, `PIP_CACHE_DIR`, `UV_CACHE_DIR`, `TMP` and `TEMP` are all on `D:`;
   - the last line is `All checks passed.`

   Run it a second time: the C: line should say `C: free space change since last check: +0.0 GB` (anything within ±0.1 GB is fine).
   **Fail:** any `FAIL` or `MISSING`, or any part of a key printed.
3. Run the tests:
   ```powershell
   pytest -q
   ```
   **Pass:** the last line says `74 passed` with no `failed`.
4. Pilot downloads. About 50 MB goes to `D:\CreatED-Quant\qa_store\raw\`, taking roughly 5–10 minutes, mostly Wikipedia history at 1 request per second.
   ```powershell
   python -m quantagents.data.download.run_all --pilot
   ```
   **Pass:**
   - `members on 2015-01-02` and `members on 2023-12-01` are each between 100 and 104;
   - a line `pilot 5th stock (left the index later): XXXX`;
   - the summary table shows `OK` with rows above 0 for membership, prices, edgar, news, factors and riskfree.

   **Fail:** any `FAILED` or `SKIPPED`. Send me the last 30 lines and the file `D:\CreatED-Quant\qa_store\logs\download_<date>.log` (it contains no keys).
5. Spot-check membership against Nasdaq's official announcements:
   ```powershell
   python -m quantagents.data.download.membership --year 2017
   ```
   Then search the web for "Nasdaq-100 annual changes December 2017" and open Nasdaq's announcement.
   **Pass:** the tickers listed as `added`/`removed` around mid-December match the announcement, and the dates are within about 2 weeks. Repeat for 2020 and 2022. **Fail:** a ticker is missing or extra. Tell me which; I'll add a correction to `reference\ndx_changes_manual.csv`.
6. Start the full downloads (only after checks 1–5 pass). They can run overnight; if stopped, rerun the same command and it resumes. Expect roughly 1–2 GB in `D:\CreatED-Quant\qa_store\raw\`, most of it SEC data and news. News takes the longest (several hours).
   ```powershell
   python -m quantagents.data.download.run_all --all
   ```
   **Pass:** the progress bars move, the summary shows `OK` for every source, and a rerun finishes quickly because it skips completed files. Then send me:
   - the number of tickers in `D:\CreatED-Quant\qa_store\raw\prices\missing.csv` (companies with no Yahoo data);
   - the number in `D:\CreatED-Quant\qa_store\raw\edgar\missing.csv`.

**API spend:** $0. **Depends on:** nothing.

---

## Phase 2: Data store, point-in-time gateway and leak tests (week 2)

**Goal:** one versioned DuckDB file and one gateway that can never return future data.

**Files:**
- `quantagents/data/etl.py`: raw files → DuckDB `D:\CreatED-Quant\qa_store\quantagents.duckdb`, with a manifest table (source, download date, rows, checksums)
- `quantagents/data/calendar.py`: NYSE trading days and the 4 pm ET close in UTC, daylight saving handled (`pandas_market_calendars`)
- `quantagents/data/indicators.py`: pandas-ta indicators (RSI, MACD, SMA/EMA 20/50/200, ATR, Bollinger, momentum 1/3/6/12-1)
- `quantagents/data/weights.py`: derived index weights, sector and country weights
- `quantagents/data/gateway.py`: `get_universe`, `get_index_weights`, `get_prices`, `get_indicators`, `get_fundamentals`, `get_news`; each logs its `as_of` date for the red-flag check
- `reference/sic_to_sector.csv`
- `scripts/data_report.py`: coverage report (missing prices, non-US filers, news counts, % of index weight missing per date)

**Availability timestamps (all stored in UTC):**

| Data | Available from |
|---|---|
| Daily price bar | That day's 4 pm ET close |
| Filing | EDGAR acceptance time |
| News | Publish time; if after 4 pm ET, from the next trading day's close |
| Membership | The effective date (from the start of that trading day) |

Indicators are computed only from bars that are already available.

**Tasks:**
- [ ] ETL into DuckDB tables: `prices_raw`, `prices_adj`, `news`, `fundamentals`, `shares_out`, `membership`, `company_info`, `factors`, `riskfree`, `manifest`
- [ ] Trading calendar and timezone helpers
- [ ] Indicators, computed per ticker on adjusted prices
- [ ] Derived index weights, sector map, country map
- [ ] Gateway, with an `as_of` audit log
- [ ] Coverage report
- [ ] Derived-index check: daily return of our cap-weighted index vs. QQQ, with tracking error per year

**Automated tests (leak tests are mandatory):**
- `test_gateway_leaks.py`: for many random `as_of` dates, no function returns a row with an availability time after `as_of`
- `test_timezones.py`:
  - news at 3:59 pm ET is included that day; 4:01 pm ET is not;
  - both daylight-saving switch days;
  - a UTC timestamp just after midnight that is still the previous day in ET;
  - a weekend publish counts from the next trading day.
- `test_filing_dates.py`: a 10-K is invisible before its acceptance time even if its period ended months earlier
- `test_membership_pit.py`: a company that later left the index is present before its removal date and absent after
- `test_indicators_pit.py`: an indicator on date t is identical whether computed with data up to t or with data up to 2023 (proves no future bars leak in)
- `test_weights.py`: weights sum to 1 on each date and use only shares data known at the time

**Manual checks:**

1. Build the data store:
   ```powershell
   python -m quantagents.data.etl --config configs\base.yaml
   ```
   **Pass:** ends with `DuckDB written: D:\CreatED-Quant\qa_store\quantagents.duckdb` and a row-count table.
2. Run the leak tests:
   ```powershell
   pytest -q tests\test_gateway_leaks.py tests\test_timezones.py
   ```
   **Pass:** all passed. **Fail:** any failure; nothing else proceeds until these pass.
3. Coverage report:
   ```powershell
   python scripts\data_report.py
   ```
   **Pass:** it lists missing tickers with reasons. "Max % of index weight missing on any date" should be under 2%. If it's higher, tell me and we decide (e.g., supply CSVs for the missing tickers).
4. Look up one date:
   ```powershell
   python -m quantagents.data.gateway --as-of 2016-03-01 --show universe
   ```
   **Pass:** about 100–104 tickers, weights summing to 1.000, and the largest weights are names you'd expect for 2016 (e.g., AAPL, MSFT, GOOG/GOOGL, AMZN, FB).
5. Derived-index check: the report shows yearly tracking error of our derived index vs. QQQ. **Pass:** under about 2% per year, which suggests the derived weights are close. If higher, it becomes a stated limitation in the log.

**API spend:** $0. **Depends on:** Phase 1 (downloads at least for the pilot tickers).

---

## Phase 3: LLM layer and research memo (week 2)

**Goal:** a safe, cheap, cached API wrapper, and sensible memos for 5 stocks.

Before writing this phase I read the Claude API reference (skill) for the exact SDK signatures: structured outputs, effort, thinking, `cache_control`, usage fields.

**Files:**
- `quantagents/llm/client.py`: the one wrapper all nodes use. It:
  - builds requests from config; never sends `temperature`, `top_p` or `top_k`; never sends a forced `tool_choice`;
  - uses structured outputs validated by pydantic;
  - puts `cache_control` on the stable prefix;
  - checks `stop_reason` (handles `refusal` and `max_tokens`);
  - retries with backoff on 429 and 5xx errors.
- `quantagents/llm/cache.py`: SQLite response cache in `D:\...\qa_store\cache\responses.sqlite`. The key is the SHA-256 of: model, system prompt, messages, schema, thinking and effort settings, `max_tokens`, replicate index. The API key and key label are **not** part of it.
- `quantagents/llm/ledger.py`: SQLite cost ledger. It:
  - records per call: time, run ID, node, model, `key_label`, all four token counts, USD, INR;
  - enforces two budgets, per key label and per run;
  - **refuses new calls at 80% of the key budget ($2.40 personal)**, with a clear message;
  - also refuses a call if its worst-case cost (`max_tokens` at output price) would cross the limit.
- `quantagents/llm/pricing.py`: prices from the brief, in config
- `quantagents/agents/schemas.py`: `ResearchMemo` and the other schemas
- `quantagents/agents/prompts/memo_v1.txt`
- `quantagents/agents/memo.py`: builds a memo for one stock from gateway data
- `scripts/ledger_report.py`: spend by key label, run and model, in USD and INR

**Tasks:**
- [ ] Read the Claude API skill and documentation; note the SDK version and exact parameters in the log
- [ ] Client wrapper, with a parameter allow-list
- [ ] Response cache and key function
- [ ] Ledger, budgets and the 80% stop
- [ ] Memo schema, prompt and node
- [ ] Ledger report

**Automated tests (no network; the SDK is mocked):**
- `test_client_params.py`: the request never contains `temperature`, `top_p`, `top_k` or a forced `tool_choice`; it always contains `max_tokens`; model IDs come from the allowed list
- `test_cache.py`: the same request hits the cache without calling the API; any change to prompt, schema, effort or replicate is a miss; **changing the API key or key label is still a hit**
- `test_ledger.py`: cost maths for all four token types; stops at $2.40 for `personal`; worst-case pre-check; USD/INR conversion
- `test_schema_failures.py`: invalid JSON is retried, then logged and defaulted to "no view"
- `test_no_key_leak.py`: the key never appears in the ledger, cache, logs or exceptions

**Manual checks:**

1. Five memos (live Haiku, ≈ $0.002):
   ```powershell
   python -m quantagents.agents.memo --config configs\pilot.yaml --as-of 2015-03-02
   ```
   **Pass:** 5 memo files in `D:\CreatED-Quant\qa_store\runs\memo_check\`. Each is readable, mentions only facts from before 2 March 2015, and has every schema field filled.
2. Run it again.
   **Pass:** the output says `cache hits: 5, API calls: 0, cost: $0.0000`.
3. Check the spend:
   ```powershell
   python scripts\ledger_report.py
   ```
   **Pass:** a `personal` row with spend under $0.01 (₹1), a remaining budget, and no key text anywhere.
4. Budget stop test (no real spend):
   ```powershell
   python scripts\ledger_report.py --simulate-spend 2.41
   ```
   **Pass:** `BLOCKED: key 'personal' at 80% of $3.00 budget`.

**API spend:** < $0.02. **Depends on:** Phase 2.

---

## Phase 4: Constraints, baseline optimizer and backtest engine (week 3)

**Goal:** correct portfolio accounting, tested without any LLM.

**Files:**
- `quantagents/portfolio/constraints.py`: 0×–2× index weight, sector bands, long-only, sum to 1, feasibility checks
- `quantagents/portfolio/baseline_opt.py`: projects proposed multipliers onto the constraints, minimizing squared distance (cvxpy or scipy)
- `quantagents/engine/backtest.py`. It:
  - runs the monthly loop and executes at the next day's open;
  - charges 10 bps × turnover; allows fractional shares;
  - marks to market daily with total returns;
  - sells a delisted holding at its last price and holds the proceeds as cash until the next rebalance;
  - saves checkpoints and can resume.
- `quantagents/engine/strategies.py`: test strategies with no AI (hold index weights; deterministic random tilts) behind the same `decide(as_of, holdings, prior_report)` signature the agent graph will use
- `runs/<run_id>/`: weights, trades, daily NAV, checkpoints. These live on D:; the repo only has a link and README.

**Tasks:**
- [ ] Constraint set and feasibility checks
- [ ] Baseline projection optimizer
- [ ] Backtest loop, execution, costs, mark-to-market
- [ ] Delisting handling
- [ ] Checkpoint and resume
- [ ] Test strategies

**Automated tests:**
- `test_constraints.py`: output always satisfies all constraints; infeasible inputs give a clear error; with all multipliers at 1 the output equals the index weights
- `test_engine_accounting.py`. A hand-computed 3-stock example covers:
  - next-open fill prices;
  - the cost charged;
  - the NAV path to the cent;
  - a dividend;
  - a split;
  - a delisting mid-month (cash until the next rebalance).
- `test_engine_index_tracker.py`: the hold-index strategy tracks the derived index almost exactly
- `test_resume.py`: kill the run mid-way, resume, and get an identical NAV

**Manual checks:**

1. No-AI backtest over the whole period:
   ```powershell
   python -m quantagents.engine.backtest --config configs\base.yaml --strategy index --run-id idx_check
   ```
   **Pass:**
   - finishes in minutes and writes `runs\idx_check\nav.csv`;
   - the printed CAGR is close to QQQ's 2015–2023 CAGR (within about 1–2 points a year);
   - turnover is near 0%.
2. Random tilts:
   ```powershell
   python -m quantagents.engine.backtest --config configs\pilot.yaml --strategy random --run-id rnd_check
   ```
   **Pass:** the log shows every rebalance passing the constraint checks (`constraints OK`) and costs charged.
3. Resume test: press Ctrl+C halfway through check 2, then rerun the same command.
   **Pass:** it says `resuming from checkpoint`, and the final NAV matches a clean run.

**API spend:** $0. **Depends on:** Phase 2.

---

## Phase 5: Full agent graph and pilot end to end (week 3)

**Goal:** `quant_agents(as_of, holdings, prior_report, variant)` runs as a pure function. The 5-stock × 3-month baseline runs end to end and produces the first tearsheet. The Sonnet thinking pilot decides thinking on vs. off.

**Files:**
- `quantagents/agents/graph.py` (LangGraph):
  - coverage node;
  - `Send()` fan-out of memos;
  - Market Analysis meeting (Emily → Bob → Dave);
  - Strategy meeting;
  - Decision meeting (Otto);
  - optimizer node.
- `quantagents/agents/selection.py`: deterministic selection of at most 20 names, at most 3 per sector, ranked by the memo's signal strength
- `quantagents/agents/summaries.py`: compact summaries (~400 tokens) for selected names and one-liners for the rest, built by Python from memo fields
- `quantagents/agents/prompts/emily_v1.txt`, `bob_v1.txt`, `dave_v1.txt`, `otto_baseline_v1.txt`
- `quantagents/agents/transcript.py`: one markdown transcript per rebalance
- `quantagents/eval/quick_report.py`: first tearsheet (quantstats) vs. QQQ

**Tasks:**
- [ ] Graph state and nodes; the graph keeps no state between rebalances
- [ ] Selection and summaries
- [ ] Committee prompts and schemas (assessments, `BaselineTilts`)
- [ ] Prompt-cache layout (stable prefix: system, persona, memo pool) and a cache-hit check
- [ ] Transcripts
- [ ] Wire the graph into the engine as a strategy
- [ ] 5-stock × 3-month pilot on the `dev` tier
- [ ] **Sonnet measurement pilot** (only after your go-ahead): 2 rebalances × 5 stocks with thinking off (`between_tools`) and 2 with thinking on at effort `medium`. Record tokens, cost and quality notes, then set the thinking default in config

**Automated tests (SDK mocked):**
- `test_graph_pure.py`: the same inputs plus cache give identical outputs; no gateway call has `as_of` after the rebalance date; no network access inside nodes (sockets blocked during the test)
- `test_selection.py`: never more than 20 names or 3 per sector; deterministic; tie-breaks are stable
- `test_invalid_llm_output.py`: a broken committee answer leads to retries, then "no view" (index weight), and is logged
- `test_transcript.py`: the transcript has every meeting's inputs and outputs

**Manual checks:**

1. Pilot run (Haiku dev tier, ≈ $0.05):
   ```powershell
   python -m quantagents.engine.backtest --config configs\pilot.yaml --strategy agents --variant baseline --run-id pilot_base_dev
   ```
   **Pass:**
   - 3 rebalances complete;
   - `runs\pilot_base_dev\` contains `nav.csv`, `weights.csv` and 3 transcripts;
   - the last line shows the cost, under $0.10.
2. Run it again.
   **Pass:** the cost line shows `$0.0000` (everything from the cache) and the NAV is identical.
3. Open `runs\pilot_base_dev\transcripts\2015-02-02.md`.
   **Pass:** you can follow Emily → Bob → Dave → Otto, the reasoning mentions only information from before that date, and no numbers are calculated by the agents (they quote inputs only).
4. First tearsheet:
   ```powershell
   python -m quantagents.eval.quick_report --run-id pilot_base_dev
   ```
   **Pass:** an HTML file opens in your browser with a chart against QQQ.
5. Sonnet pilot. I'll give you the exact estimate first: about $0.6–1.2, keeping the personal key's total under $2.40.
   ```powershell
   python scripts\thinking_pilot.py --config configs\pilot.yaml --rebalances 2
   ```
   **Pass:** a table comparing thinking off vs. on (tokens, cost, sample rationales), saved to `runs\thinking_pilot\summary.md`.

**API spend:** ≈ $0.05 (Haiku), plus ≈ $0.6–1.2 Sonnet pilot after approval. **Depends on:** Phases 3 and 4. **Week-3 exit:** first results to the professor.

---

## Phase 6: Scale-up, evaluation and baseline full run (weeks 4–5)

**Goal:** the complete evaluation, proven on small slices; a measured cost forecast; then the 2015–2023 baseline on the student key.

**Files:**
- `quantagents/eval/metrics.py`:
  - CAGR, annual returns, Sharpe, Sortino (T-bill risk-free rate);
  - max drawdown, Calmar;
  - tracking error, information ratio, active return;
  - turnover, cost drag;
  - sub-periods;
  - bootstrap confidence intervals.
- `quantagents/eval/factors.py`: Carhart 4-factor regression (alpha with t-stat, loadings), with Newey-West standard errors
- `quantagents/eval/red_flags.py`: every check in brief §9, including geography and the missing-weight check
- `quantagents/eval/report.py`: one command produces the tables (CSV and markdown), the growth-of-$1 chart and tearsheets from stored runs, with **no LLM calls**
- `scripts/cost_forecast.py`: measured tokens per memo and per committee call → cost of each full run, per tier

**Tasks:**
- [ ] Metrics, factor regression, red flags, report
- [ ] Geography check (reported, not enforced)
- [ ] Small-slice proofs on the personal key: 20 stocks × 12 months, dev tier (≈ $0.35; asked first)
- [ ] Cost forecast from measured numbers. It states exactly what the student key must cover
- [ ] **Student key swap** (README checklist)
- [ ] **Baseline full run 2015–2023, `paper` tier** (only after your go-ahead and the success criterion is confirmed)
- [ ] Red flags reviewed; any hit investigated before results are shared

**Automated tests:**
- `test_metrics.py`: each metric against hand-computed or quantstats values on a synthetic series
- `test_factors.py`: the regression recovers known alpha and loadings from a synthetic series
- `test_red_flags.py`: each flag fires on a planted bad case and stays silent on a clean one
- `test_report_no_llm.py`: the report runs with networking blocked

**Manual checks:**

1. Small-slice run (≈ $0.35, after go-ahead):
   ```powershell
   python -m quantagents.engine.backtest --config configs\slice20.yaml --strategy agents --variant baseline --run-id slice_base_dev
   ```
   **Pass:** 12 rebalances, red flags `0 hits` (or each explained), and the ledger shows the personal key still under $2.40 in total.
2. Cost forecast:
   ```powershell
   python scripts\cost_forecast.py
   ```
   **Pass:** a table with measured tokens per call and the forecast for each full run, e.g. `baseline paper: $X (± range)`.
3. After the key swap:
   ```powershell
   python scripts\check_env.py
   ```
   **Pass:** `key_label: student, budget $150`. Then rerun manual check 1 of Phase 5 and confirm it costs `$0.0000`, because the cache survived the swap.
4. Full baseline (student key, after go-ahead):
   ```powershell
   python -m quantagents.engine.backtest --config configs\base.yaml --strategy agents --variant baseline --run-id baseline_2015_2023
   ```
   **Pass:** 108 rebalances, spend within the forecast and the run budget, and a red-flag summary.
5. Report:
   ```powershell
   python -m quantagents.eval.report --runs baseline_2015_2023
   ```
   **Pass:** `reports\results.md` holds a table of baseline vs. QQQ vs. ^NDX, and `reports\growth_of_1.png` has three lines.

**API spend:** ≈ $0.4 personal key; ≈ $16–20 student key (the forecast replaces this).
**Depends on:** Phase 5. The full run also needs the student key and a confirmed success criterion.

### ═══ MVP BOUNDARY (end of week 5) ═══

The MVP is the baseline vs. QQQ/^NDX results table and growth-of-$1 chart, from a red-flag-clean 2015–2023 run.

If the student key has not arrived by then, the MVP is shown on the small-slice run, and the full run is marked "blocked on key".

---

## Phase 7: Enhancement and names-hidden run (weeks 6–7)

**Goal:** LLM ratings → Black-Litterman, the names-hidden control, and a three-way comparison with view accuracy.

**Files:**
- `quantagents/portfolio/black_litterman.py`. It builds:
  - the prior from cap weights on date t (δ = 2.5);
  - P and Q from ratings, using the calibration table divided by 3 to get monthly figures;
  - Ω using Idzorek's method from confidence;
  - τ = 0.05;
  - a Ledoit-Wolf 252-day covariance.

  It then computes the posterior and runs the same constraint set (PyPortfolioOpt).
- `quantagents/agents/prompts/otto_enhanced_v1.txt` and an `EnhancedViews` schema (rating, confidence, rationale, 3-month horizon)
- `quantagents/agents/anonymize.py`: stable aliases such as "Company 017, semiconductors, large cap"; names and tickers removed from news; relative dates where feasible
- `quantagents/eval/view_accuracy.py`: realized 3-month excess return by rating, hit rate, rank IC

**Tasks:**
- [ ] Black-Litterman module
- [ ] Enhanced prompt and schema; `variant: enhanced` in the graph
- [ ] Anonymizer, with a leak scan (no real ticker or name in any LLM input)
- [ ] View-accuracy analysis
- [ ] Pilot and slice runs of enhanced (dev tier, personal key if budget remains, otherwise student key)
- [ ] **Enhanced full run** (student key, after go-ahead)
- [ ] **Names-hidden enhanced full run** (student key, after go-ahead)
- [ ] Three-way comparison table

**Automated tests:**
- `test_black_litterman.py`:
  - with no views, the posterior equals the prior and the weights equal the index;
  - a buy view raises that stock's weight;
  - higher confidence moves the weight further;
  - matches a hand-worked 3-asset example;
  - constraints always hold.
- `test_idzorek.py`: confidence 1 gives Ω ≈ 0 (full tilt); confidence 0 gives no tilt
- `test_anonymize.py`: no ticker, company name or obvious alias in any prompt across a sample of rebalances; aliases are stable across dates
- `test_fairness.py`: baseline and enhanced share the same universe, data, constraints, costs and evaluation code path. Only the decision node differs

**Manual checks:**

1. Enhanced pilot:
   ```powershell
   python -m quantagents.engine.backtest --config configs\pilot.yaml --strategy agents --variant enhanced --run-id pilot_enh_dev
   ```
   **Pass:** the transcripts show ratings and confidence, and the weights move in the direction of the ratings.
2. Names-hidden check:
   ```powershell
   python -m quantagents.agents.anonymize --scan --run-id pilot_enh_hidden_dev
   ```
   **Pass:** `0 real names found in 100% of LLM inputs`.
3. Full runs (student key, after go-ahead). Same command as Phase 6 check 4, with `--variant enhanced` and then `--variant enhanced --names-hidden`.
4. Final report:
   ```powershell
   python -m quantagents.eval.report --runs baseline_2015_2023 enhanced_2015_2023 enhanced_hidden_2015_2023
   ```
   **Pass:**
   - a five-row table (baseline, enhanced, names-hidden, QQQ, ^NDX);
   - one chart with all five lines;
   - a view-accuracy table;
   - red flags clean or explained.

**API spend:** ≈ $0.3 personal; ≈ $22–26 per full run × 2 on the student key (the forecast replaces this).
**Depends on:** Phase 6.

---

## Phase 8: Poster materials and README (week 8)

**Goal:** the review package for the professor (due 15 January 2027).

**Files:**
- `reports/poster/`: results table, growth-of-$1 chart, architecture diagram (Mermaid → PNG), one sample transcript, a limitations box
- `README.md`: overview, Windows quick start, D: setup, **key swap checklist**, commands
- `scripts/build_poster_assets.py`

**Tasks:**
- [ ] Figures and table generated from the final runs only
- [ ] Sample transcript chosen and lightly formatted (content unchanged)
- [ ] README with the key swap checklist (the checklist itself is written in Phase 3 and kept up to date)
- [ ] Poster rules applied once you share them (open decision 5)

**Automated tests:** `test_poster_assets.py`: every figure regenerates from stored runs with no network.

**Manual checks:**
```powershell
python scripts\build_poster_assets.py
```
**Pass:** `reports\poster\` contains the PNGs, `results_table.md` and `sample_transcript.md`, and the numbers match `reports\results.md`.

**API spend:** $0. **Depends on:** Phase 7.

---

## Phase 9 (final): Handoff documentation

**Goal:** the documents in `HANDOFF_REQUIREMENTS.md`, written from actual run outputs and the decisions log.

**Files:** `docs/handoff.md`, `docs/handoff.docx`, `docs/design.md`, `docs/mentoring.md`, `scripts/build_handoff_docx.py`

**Tasks:**
- [ ] `handoff.md`: all 13 required sections; numbers pulled from `runs/` and `reports/`
- [ ] `handoff.docx`: generated from the same content, with tables and charts embedded
- [ ] `design.md`: all 12 sections, with Mermaid diagrams (architecture, one-rebalance sequence)
- [ ] `mentoring.md`: all 9 required sections, **16 sessions of 60 minutes** (decision D13). The mentor first builds and tests the whole project, then uses the finished repo as the reference ("answer key") while the student re-develops it step by step. Each session has:
  - an objective;
  - a 10-minute recap of the previous session;
  - the concepts to explain, with pointers to `design.md` and code;
  - a build task for the student, with exact commands;
  - how to compare the student's code with the reference;
  - an acceptance check;
  - common mistakes;
  - homework.

  It also includes an exercise bank that uses real files and commands. The planned session arc is in `handoff.md` (root).
- [ ] Quality-bar checklist from `HANDOFF_REQUIREMENTS.md`, including following the quick start in a clean clone

**Automated tests:**
- `test_docs.py`:
  - every command in the docs exists (each CLI's `--help` exits 0);
  - every file path mentioned exists;
  - numbers in `handoff.md` match `reports/results.csv`;
  - no secrets or emails appear (pattern scan);
  - the Mermaid diagrams parse.

**Manual checks:**
1. Open `docs\handoff.docx` in Word. **Pass:** headings, tables and charts all render.
2. In a fresh folder on D:, follow `handoff.md`'s quick start exactly. **Pass:** the tests, the pilot (served from the cache) and the report all run.
3. Skim `mentoring.md` session 1 and run its exercise. **Pass:** the expected outcome matches.

**API spend:** $0. **Depends on:** Phase 8.

---

## Stretch (only after Phase 7's exit check passes)

### S1: Bull vs. bear debate
- [ ] Bull and bear agents argue each selected stock for 1 round (configurable, at most 2), before the Strategy meeting
- [ ] The rating gap between bull and bear feeds Ω: wider disagreement means lower confidence
- [ ] Tests: a larger gap gives a larger Ω; the round cap is respected
- Spend: ≈ $5–10 for a full run; forecast first.

### S2: No-AI quant ranking baseline
- [ ] Value + quality + momentum composite, within-sector ranks → tilts → the same optimizer
- [ ] Tests: deterministic; same constraints; no LLM calls
- Spend: $0.

---

## Personal-key budget plan ($3.00 key budget, hard stop at $2.40)

| Step | Estimate |
|---|---|
| Phase 3 memo checks | $0.01 |
| Phase 5 Haiku pilot | $0.05 |
| Phase 5 Sonnet thinking pilot (asked first) | $0.60–1.20 |
| Phase 6 slice proof, 20 stocks × 12 months (asked first) | $0.35 |
| Phase 7 enhanced pilot and slice (dev) | $0.30 |
| Reruns from cache | $0.00 |
| **Total** | **≈ $1.3–1.9**, leaving headroom below $2.40 |

If measured costs come in higher, I'll shrink the slices (fewer stocks or months) before touching the stop.
