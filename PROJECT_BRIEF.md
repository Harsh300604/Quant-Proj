# QuantAgents: Project Brief for the Development Team

This document is the single source of truth for building QuantAgents. It covers what we are building, why, every design decision made so far, the open questions, and the constraints. Read it fully before writing code.

Last updated: 4 November 2026.

---

## 1. Summary

QuantAgents is an AI system that manages a **simulated** NASDAQ-100 stock portfolio. A team of LLM agents with specialist roles (fundamental analyst, quantitative analyst, risk manager, portfolio manager) studies each stock's prices, financials and news. The team decides how the portfolio should differ from the NASDAQ-100 index, and a Python optimizer turns those decisions into weights.

We replay history **month by month from 2015 to 2023**, using only information that was available at each date. We compare three things:

1. **Baseline:** our implementation of the method in the paper *"QuantAgents: Towards Multi-Agent Financial System via Simulated Trading"*.
2. **Enhanced:** the baseline plus our enhancement (LLM views fed into Black-Litterman; see section 7).
3. **Benchmark:** the NASDAQ-100 itself (QQQ total return and the ^NDX index).

The result is presented as a **poster at the UT Dallas Biz AI Conference (March 2027)**. A reviewable package is due to the professor by **15 January 2027**.

No real money is involved. No live trading. This is a research backtest.

### What the project solves

1. **Cognitive overload:** a single LLM given 100 charts and hundreds of articles hallucinates. We divide the work across specialist agents.
2. **News vs. numbers:** quant models ignore news, and LLMs are poor at arithmetic. We use LLMs for judgment and Python for all maths.
3. **Untested strategies:** decisions are replayed historically under strict point-in-time rules before anyone trusts them.
4. **Black boxes:** every rebalance produces a human-readable transcript explaining the reasoning.

---

## 2. Constraints

| Constraint | Value |
|---|---|
| Team | **One developer** (using Claude Code), no ongoing finance reviewer |
| Duration | **8 weeks maximum** from start. MVP by end of week 5. |
| Hard deadline | Review package to the professor by 15 January 2027 |
| LLM budget | **$150 cap** (expected ~$100–110), Anthropic API, prepaid credits, on the student's project key |
| Temporary key (now) | The student's key is not available yet. Building starts on the developer's **personal key with a hard limit of ₹300 (≈ $3.40; use $3.00 as the budget)**. On this key: Haiku-only development, at most a tiny Sonnet measurement pilot, and no full or long backtests. The key is swapped via `.env` later, with no code changes. |
| Hardware | Normal laptop (16 GB RAM, ~10 GB disk); no GPU |
| Language | Python 3.10+ |
| OS | Developer is on Windows; code must run on Windows (and should be portable) |
| Storage | **D: drive only.** C: is nearly full. Repo, virtual environment, pip/uv caches, temp files, downloaded data, DuckDB, SQLite caches, run outputs and any new installs all live on D: (e.g., under `D:\CreatED-Quant\`). Redirect caches and temp files via environment variables set per session or in project scripts, not system-wide without approval. |

The Anthropic API key is **separate** from any Claude Pro subscription. All agent calls in the pipeline are billed per token through the API.

---

## 3. Scope

### Committed (must ship)

- Baseline system implementing the paper's method, first tested on **5 stocks**.
- Full run on the **NASDAQ-100 (historical members on each date), 2015–2023, monthly rebalancing**.
- Benchmark comparison against **QQQ total return and ^NDX**, including factor attribution.
- **One enhancement** (LLM views → Black-Litterman) and a full re-run.
- A **names-hidden run** of the enhanced version (contamination control; see section 9).
- Everything needed for a **poster**: results table, growth-of-$1 chart, architecture diagram, one sample agent transcript.

### Stretch (only if the core finishes early)

- Bull vs. bear debate step whose disagreement sets view confidence (Ω).
- No-AI quant ranking baseline (value + quality + momentum composite).

### Out of scope for these 8 weeks

- Risk-manager hard veto loop.
- Repeat runs with multiple seeds.
- Weekly rebalancing.
- Live trading, a UI, or a web app.

---

## 4. Decisions already made (do not re-open)

These came from the team and a finance review.

| Topic | Decision |
|---|---|
| Universe | **NASDAQ-100 members as they were on each date.** Includes companies that later left the index. No survivorship bias. |
| Benchmark | Measure against **both** QQQ (total return, dividends reinvested) and ^NDX. |
| Portfolio shape | Start from **NASDAQ-100 index weights**. Each stock's weight must stay **between 0× and 2× its index weight**. |
| Similarity to index | Portfolio must resemble the NASDAQ-100 in **size, business mix (sector) and geography**, so performance differences cannot be explained by those factors. Enforce sector weights near the index, and verify with factor regression. |
| Long/short | **Long-only**, no leverage, weights sum to 1. |
| Financials | Use all standard fundamentals. Each figure counts as known from its **SEC filing date** (EDGAR acceptance timestamp), never the period-end date. |
| Rebalancing | **Monthly**, on the first trading day of the month. |
| View horizon | Each agent view is a **3-month outlook** (one month is too noisy), even though rebalancing is monthly. |
| Execution | Trade at the **next trading day's open** after the decision date. |
| Costs | **10 bps** per unit of turnover. Fractional shares allowed. |
| Returns | Split- and dividend-adjusted total returns. |
| Risk-free rate | 3-month US T-bill (FRED `DTB3`). |
| News timing | News published after the **4 pm ET close** is usable from the next trading day. |
| Delistings | A holding that is acquired or delisted is sold at its last traded price, and the proceeds are redistributed at the next rebalance (held as cash in between). |
| Warm-up | Data starts in **2014** so indicators and covariance estimates are ready by January 2015. |
| Models | Haiku 5.5 for research memos, Sonnet 5.5 for the committee (section 8). |
| Reproducibility | Pinned model IDs plus a response cache, **not** a `temperature` setting (the API rejects it). |

---

## 5. Open decisions (ask the user; do not guess)

1. **Data source for historical NASDAQ-100 membership and prices of delisted companies.** yfinance often lacks delisted tickers. A paid dataset may be needed. **This blocks week 1.** Build the data layer behind an interface so the source can be swapped.
2. **Success criterion.** Proposed: information ratio vs. the NASDAQ-100 and factor-adjusted alpha (Carhart 4-factor), alongside Sharpe, Sortino and max drawdown. To be agreed with the professor **before** any full-run results are produced. Compute all of these regardless.
3. **Sector band width.** Default: each sector's weight within **±2 percentage points** of its index weight. Make it configurable.
4. **Rating-to-return mapping values** (section 7). Defaults are set by judgment; keep them configurable.
5. **Poster rules** (size, template, deadlines) from the conference. Not needed until week 8.

When something is ambiguous and not listed here, stop and ask rather than assume.

---

## 6. System architecture

The AI is a **pure function**. The backtest engine is a **loop around it**. They never share state except through the function's inputs and outputs.

```
OFFLINE DATA LAYER (built once, frozen, versioned)
  yfinance prices ─┐
  Alpaca news ─────┤
  SEC EDGAR ───────┼──► ETL ──► DuckDB ──► indicators (pandas-ta)
  NDX membership ──┤
  index weights ───┘
            │
            │  the ONLY way in: gateway.get_*(as_of_date)
            ▼  every query filtered: timestamp <= as_of_date
OUTER LOOP: backtest engine
  for t in monthly rebalance dates (2015-01 .. 2023-12):
      target_weights, transcript = quant_agents(as_of_date=t, holdings, prior_report)
      execute at next open with 10 bps costs
      mark to market daily until the next rebalance
            │
            ▼
  INNER: LangGraph pipeline (pure function: date -> weights)
    [0] Coverage: all index members on date t (Python)
    [1] Send() fan-out: one research memo per stock (Haiku 5.5) -> shared pool
    [2] Market Analysis meeting: Emily -> Bob -> Dave (Sonnet 5.5)
    [3] Strategy meeting: views on up to 20 stocks (Sonnet 5.5)
          baseline: tilts proposed directly
          enhanced: ratings + confidence -> Black-Litterman
    [4] Decision meeting: Otto finalizes (Sonnet 5.5)
    [5] Optimizer (Python): applies 0x–2x and sector constraints -> weights
    -> transcript log + LLM response cache
            │
            ▼ daily NAV
EVALUATOR: quantstats + factor regression vs QQQ and ^NDX
```

### Agent personas

| Name | Role | Reads | Produces |
|---|---|---|---|
| Research memo nodes | Junior analysts | One stock's indicators, fundamentals, news for the period | A fixed-schema one-page memo (JSON) |
| **Emily** | Fundamental analyst | Memo pool | Fundamental assessment per stock |
| **Bob** | Quantitative analyst | Memo pool, indicators | Quantitative assessment per stock |
| **Dave** | Risk manager | Memo pool, Emily, Bob, portfolio risk stats | Risk assessment, concentration and sector concerns |
| **Otto** | Portfolio manager | Everything above | Final views or tilts, with rationale |

### Coverage and the "top 20"

- **Every index member on date t** gets a Haiku research memo (cheap).
- The committee forms views on **at most 20 stocks** per rebalance: the ones with the strongest signals, **spread across sectors** (e.g., up to 3 per sector), chosen by a deterministic Python ranking of memo signals. It is not a momentum filter.
- **Stocks without a view stay at index weight** (subject to renormalization).
- Never pass all 100 full memos into the committee. That is ~390k tokens per rebalance and degrades quality. The committee receives compact summaries (~400 tokens per stock) of the selected names, plus one-line summaries of the rest.

---

## 7. Baseline vs. enhancement

Both versions use the **same universe, data, constraints, optimizer, costs and evaluation**. Only the decision mechanism differs. That is what makes the comparison fair.

### Baseline (paper's method, adapted to index-relative weights)

- The committee runs the paper's sequential meetings and Otto outputs a **target active tilt** per selected stock: a multiplier of its index weight in [0, 2].
- The optimizer projects these onto the constraints (0×–2×, sector bands, sum to 1, long-only), minimizing distance to the proposed weights.

### Enhanced: LLM views → Black-Litterman

1. For each selected stock, the committee outputs a **five-level rating** (strong sell, sell, hold, buy, strong buy) and a **confidence** in [0, 1], both over a **3-month horizon**, with a written rationale.
2. A **calibration table** maps ratings to 3-month expected excess returns vs. the index. Configurable defaults, set by judgment:

   | Rating | Expected 3-month excess return |
   |---|---|
   | Strong sell | −6% |
   | Sell | −3% |
   | Hold | 0% |
   | Buy | +3% |
   | Strong buy | +6% |

   Convert to the rebalance frequency consistently and document how.
3. Build absolute views: **P** (one row per viewed stock) and **Q** (from the table).
4. **Ω** from confidence via **Idzorek's method**.
5. **Prior:** market-implied equilibrium returns from **NASDAQ-100 cap weights on date t**. Defaults: δ = 2.5, τ = 0.05 (configurable).
6. **Covariance:** 1 year of daily returns, **Ledoit-Wolf shrinkage**, annualized.
7. Black-Litterman posterior → constrained optimizer (0×–2× index weight, sector bands, long-only, sum to 1) → weights.

Use **PyPortfolioOpt** (`BlackLittermanModel`, `EfficientFrontier` with custom constraints) or `scipy.optimize`. **LLMs never compute weights, covariances or returns in text.**

### Stretch: bull vs. bear debate

Before the strategy meeting, a bull and a bear agent argue each selected stock for 1 round (configurable cap of 2). The gap between their ratings feeds Ω: wider disagreement means lower confidence. Only build this if the core is done early.

---

## 8. LLM usage (Anthropic API)

### Models

| Tier (config) | Research memos | Committee | Purpose |
|---|---|---|---|
| `dev` | `claude-haiku-5-5` | `claude-haiku-5-5` | Build and debug cheaply, same model family |
| `paper` | `claude-haiku-5-5` | `claude-sonnet-5-5` | All reported results |
| `robustness` (optional) | `claude-haiku-5-5` | `claude-opus-5-5` | Show results are not model-specific |

Prices per million tokens (input / output), as of October 2026:

- Haiku 5.5: $0.10 / $0.50.
- Sonnet 5.5: $2 / $10, with cache reads at $0.20.
- Opus 5.5: $4 / $20.

Use these exact model ID strings. Do not use older generations: Haiku 4.5 costs 10× more and Sonnet 4.6 costs 50% more.

### API rules that will otherwise cause errors

- **Do not send `temperature`, `top_p` or `top_k`.** Since 21 October 2026 the API returns a 400 error for them.
- **Forced tool choice (`tool_choice` `any` or `tool`) returns a 400** on Sonnet 5.5 and Opus 5.5. For JSON output, use **structured outputs** (`output_config: {format: ...}` / `client.messages.parse()`), or `tool_choice: auto` with `strict: true` tools.
- **Thinking:** Sonnet 5.5 thinks by default, and thinking tokens are billed as output.
  - To turn it off, send `thinking: {type: "between_tools"}`. This is only valid at effort `high` or below, with no other thinking fields.
  - `{type: "disabled"}` returns a 400.
  - Control depth with `output_config: {effort: "low" | "medium" | "high"}`.
  - Haiku 5.5 defaults to effort `medium`; set `low` for memos.
- **Prompt caching:** put stable content first (system prompt, persona instructions, the memo pool for this rebalance) and mark it with `cache_control`. Put volatile content last. Confirm hits with `usage.cache_read_input_tokens`.
- Use the **official `anthropic` Python SDK** inside LangGraph nodes through one thin wrapper module (`llm/client.py`) that all nodes share. Avoid wrappers that may not pass the newer parameters. If a Claude API skill or documentation is available in your environment, consult it before writing API code. Do not guess SDK signatures.
- Check `stop_reason` before reading content; handle `refusal`, `max_tokens` and errors with retries for 429/5xx.

### Thinking on or off: decided by a pilot

In week 3, run the pilot (3 months × the selected stocks) twice: Sonnet thinking **off** (`between_tools`) and **on** at effort `medium`. Compare cost and output quality (view sanity, rationale quality). Default to **off** unless quality clearly drops. Record the decision in config.

### Response cache (mandatory)

- SQLite, keyed on `SHA256` of: model ID, system prompt, messages, tool schemas, thinking/effort settings, `max_tokens`, output schema, and a **replicate index**.
- On a hit, return the stored response with no API call. This makes crashed runs resume for free and reruns of evaluation free.
- Any prompt change produces new keys, so a full rerun costs money again. Debug on small slices.

### Cost ledger (mandatory)

- Log every call: timestamp, run ID, node, model, `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`, computed $ cost.
- Per-run budget in config. **Stop the run** when the projected or actual spend exceeds it.
- Set `max_tokens` on every call.

### Token and cost budget (planning estimate, to be replaced by measured pilot numbers)

| Per rebalance | Input tokens | Output tokens |
|---|---|---|
| Research memos, Haiku (all ~100 members) | ~200k | ~40k |
| Committee, Sonnet (~8 calls) | ~84k | ~7k (thinking off) |

| Run (108 monthly rebalances) | Estimated cost |
|---|---|
| Baseline | ~$16–20 |
| Enhanced | ~$22–26 |
| Enhanced, names hidden | ~$22–26 |
| Development and pilots | ~$20–30 |
| **Total** | **~$100–110 (cap $150)** |

With thinking on, the committee cost roughly 2.5×. That would break the cap with all three runs, so that decision must be made from pilot data.

---

## 9. Point-in-time rules and contamination controls

### Point-in-time gateway (the most important module)

- All data access inside the pipeline goes through `data/gateway.py`.
  - Functions: `get_universe(as_of)`, `get_index_weights(as_of)`, `get_prices(tickers, as_of, lookback)`, `get_indicators(tickers, as_of)`, `get_fundamentals(tickers, as_of)`, `get_news(tickers, as_of, window)`.
- Every query filters `timestamp <= as_of_date`, using the **availability** timestamp:
  - Fundamentals: the filing acceptance time.
  - News: the publish time, with the after-close rule.
  - Prices: the close of the bar.
- **No live APIs or web access inside LangGraph nodes during a backtest.** Everything comes from the frozen DuckDB snapshot.
- **Leak tests** (pytest) fail the build if any gateway function can return a row after `as_of_date`. Include timezone edge cases (UTC vs. ET, after-close news).

### Contamination (LLM training data covers 2015–2023)

- The **names-hidden run** replaces tickers and company names in everything the LLMs see with stable aliases (e.g., "Company 017, semiconductors, large cap"). Also strip names from news text, and use relative dates where feasible.
- Report the enhanced results both with and without names. The poster states this limitation openly.

### Red-flag checks (replace a human reviewer)

Run automatically after every backtest. Any hit pauses for investigation:

- Annualized Sharpe > 2, or no losing calendar year.
- Single-day portfolio move > 15% absent a matching index move.
- Weights outside 0×–2× of index weight, sector weights outside the band, or weights not summing to 1.
- Monthly turnover > 100%.
- Any gateway call with `as_of_date` later than the rebalance date.

---

## 10. Data

| Data | Source | Notes |
|---|---|---|
| Daily OHLCV, adjusted | yfinance | Download once, store raw and adjusted. Gaps for delisted tickers are expected (see open decision 1). |
| NDX membership by date | **TBD** (open decision 1) | Needed for 2014–2023. |
| Index weights by date | Derived: shares outstanding (EDGAR, by filing date) × price, normalized over members | If an official weight history is available, prefer it. Document the method. |
| Sector / geography | Static classification (GICS-like sector, HQ country) per ticker | For sector bands and factor checks. |
| News | Alpaca historical news API (free account) | Headline, summary, symbols, `created_at` UTC. Starts 2015; acceptable with the 2014 warm-up for prices only. |
| Fundamentals | SEC EDGAR (XBRL company facts) | Revenue, margins, EPS, FCF, debt, equity, shares outstanding. Keyed by acceptance date. Requires a User-Agent with contact email; respect SEC rate limits. Non-US filers (20-F/40-F) may have gaps: log them. |
| Benchmarks | QQQ (total return) and ^NDX via yfinance | |
| Risk-free | FRED `DTB3` | |
| Factors | Kenneth French data library: Fama-French 3 factors + momentum, daily/monthly | For factor-adjusted alpha. |
| Indicators | Computed with pandas-ta | RSI, MACD, SMA/EMA (20/50/200), ATR, Bollinger, momentum 1/3/6/12-1 months. Zero LLM tokens. |

Store everything in **one DuckDB file**, versioned with a manifest (source, download date, row counts, checksums).

---

## 11. Evaluation

For baseline, enhanced, names-hidden, QQQ and ^NDX:

- **Return metrics:** CAGR and annual returns.
- **Risk-adjusted:** Sharpe and Sortino, using the T-bill risk-free rate.
- **Drawdown:** max drawdown and Calmar.
- **Relative to the NASDAQ-100:** tracking error, information ratio and active return.
- **Factor regression:** Carhart 4-factor alpha (with t-stat), plus loadings on market, size, value and momentum.
- **Trading:** turnover and cost drag.
- **Robustness:** sub-periods 2015–2019, 2020, 2021, 2022 and 2023.
- **View accuracy (enhanced):** realized 3-month excess return grouped by rating, hit rate, and rank IC.
- **Outputs:** quantstats HTML tearsheets, a growth-of-$1 chart (all versions on one chart), and one CSV/markdown results table. All generated by **one script** from stored run outputs, with no LLM calls.

Do not claim statistical significance unless the numbers support it. Report confidence intervals (bootstrap) where possible.

---

## 12. Suggested repository layout

```
quantagents/
  configs/
    base.yaml            # universe, dates, costs, constraints, model tiers, budgets
    pilot.yaml           # 5 stocks / 3 months
  data/
    download/            # one script per source (prices, news, edgar, membership, factors)
    etl.py               # build DuckDB
    gateway.py           # point-in-time access (ONLY entry point)
  llm/
    client.py            # Anthropic SDK wrapper: cache, ledger, retries, structured outputs
    cache.py
    ledger.py
  agents/
    prompts/             # persona and memo prompts (versioned text files)
    schemas.py           # pydantic models for memos, assessments, views, tilts
    graph.py             # LangGraph: quant_agents(as_of, holdings, prior_report, variant)
    selection.py         # deterministic choice of up to 20 names across sectors
    anonymize.py         # names-hidden mode
  portfolio/
    constraints.py       # 0x–2x, sector bands, long-only, sum to 1
    baseline_opt.py      # project proposed tilts onto constraints
    black_litterman.py   # ratings -> Q, confidence -> Omega, posterior, optimize
  engine/
    calendar.py
    backtest.py          # loop, next-open execution, costs, daily MTM, delistings, checkpoints
  eval/
    metrics.py
    factors.py
    report.py            # tables, charts, tearsheets
    red_flags.py
  tests/                 # leak tests, constraint tests, engine accounting tests
  runs/                  # outputs per run_id (weights, NAV, transcripts, ledger)
  README.md
```

Use `pyproject.toml` or a pinned `requirements.txt`. Secrets go in a `.env` file (`ANTHROPIC_API_KEY`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `SEC_USER_AGENT`), never committed.

### Example config (illustrative)

```yaml
run_id: enhanced_2015_2023
variant: enhanced            # baseline | enhanced
names_hidden: false
dates: {start: 2015-01-01, end: 2023-12-31, warmup_start: 2014-01-01}
rebalance: monthly_first_trading_day
execution: next_open
cost_bps: 10
constraints:
  min_multiple_of_index: 0.0
  max_multiple_of_index: 2.0
  sector_band_pp: 2.0
  long_only: true
selection: {max_views: 20, max_per_sector: 3}
views:
  horizon_months: 3
  rating_to_excess_return: {strong_sell: -0.06, sell: -0.03, hold: 0.0, buy: 0.03, strong_buy: 0.06}
black_litterman: {delta: 2.5, tau: 0.05, omega: idzorek, cov: ledoit_wolf_252d}
models:
  tier: paper
  memo: {model: claude-haiku-5-5, effort: low, max_tokens: 1500}
  committee: {model: claude-sonnet-5-5, thinking: between_tools, effort: medium, max_tokens: 4000}
budget_usd: 40
replicate: 0
```

---

## 13. Schedule (8 weeks)

| Week | Milestone | Exit check |
|---|---|---|
| 1 | Setup; resolve the data source; start downloads (news and EDGAR take longest) | Repo runs; config loads; downloads in progress; data source decided |
| 2 | DuckDB built; point-in-time gateway; leak tests; index and sector weights; memo node on 5 stocks | Leak tests pass; 5 memos look sensible |
| 3 | Full graph as a pure function; constraint optimizer; backtest engine; benchmark comparison; thinking pilot | 5-stock, 3-month backtest end to end; first tearsheet; **first results to the professor** |
| 4–5 | Scale to full historical universe; baseline run 2015–2023; evaluation script; red flags | **MVP complete**: baseline vs. QQQ/^NDX table and chart |
| 6–7 | Enhancement (ratings → Black-Litterman); enhanced run; names-hidden run; comparison | Three-way results table; view-accuracy analysis |
| 8 | Poster figures, sample transcript, README; buffer | Review package ready |
| Final | Handoff documentation per `HANDOFF_REQUIREMENTS.md`: `docs/handoff.md`/`.docx`, `docs/design.md`, `docs/mentoring.md` | Quality-bar checklist in that file passes |

Stretch items start only after week 7's exit check passes. Throughout the build, keep a running decisions-and-deviations log (e.g., `docs/decisions_log.md`) so the handoff documents can be written accurately.

---

## 14. Engineering principles

1. **Point-in-time correctness beats everything.** A fast, wrong backtest is worse than none.
2. **LLMs judge, Python calculates.** No numbers computed in prompts.
3. **Every LLM output is schema-validated** (pydantic). Invalid outputs are retried, then logged and defaulted to "no view" (index weight), never silently accepted.
4. **Small before large:** 5 stocks × 3 months before any full run. Never debug on the full 108-month run.
5. **Everything reproducible from config plus the frozen data snapshot plus the response cache.**
6. **Fair comparison:** baseline and enhanced share everything except the decision mechanism.
7. **Transcripts are a product:** save every meeting's inputs and outputs per rebalance, readable as markdown.
8. **Budget discipline:** check the ledger after every run; never exceed the cap.

---

## 15. Related work and positioning

- **QuantAgents paper** (the method we implement): a multi-agent financial system with simulated trading and sequential meetings among specialist agents.
- **TradingAgents** (TauricResearch, `github.com/TauricResearch/TradingAgents`): the closest open-source LangGraph framework.
  - **How we differ:** it rates single tickers (`propagate(ticker, date)`). We construct and constrain a whole index-relative portfolio, convert views through Black-Litterman, and benchmark point-in-time against the NASDAQ-100.
  - **What we borrow:** the bull/bear debate idea (stretch), the fast/deep model split, EDGAR filing-date fundamentals, and scoring decisions by rating.
- **AI ranking-based fund managers** (e.g., cross-sectional ranking approaches): motivate expressing views relatively within sectors and the optional no-AI ranking baseline.

---

## 16. Glossary

- **Point-in-time (PIT):** using only data that was available at the decision date.
- **Look-ahead bias:** accidentally using future information. It makes results look better than they could have been.
- **Survivorship bias:** testing only on companies that still exist today.
- **Black-Litterman:** a portfolio model that blends market-implied returns (from index weights) with subjective views, weighted by confidence.
- **P, Q, Ω:** the view matrix (which assets), the view returns, and the view uncertainty.
- **Information ratio:** active return divided by tracking error against the benchmark.
- **Factor-adjusted alpha:** return not explained by market, size, value and momentum exposures.
- **Rebalance:** resetting the portfolio to target weights.
