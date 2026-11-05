# Handoff: continuing QuantAgents in a new dev chat

This file lets a new Claude Code chat pick up the build if the current session is lost (credit limit, disconnect).
It is different from `docs/handoff.md`, which is the **final** handoff document for the mentor, written in Phase 9.

_Last updated: 2026-11-06 (handover to a new dev chat; review suggestions adopted)._

---

## 1. Prompt to paste into a new dev chat

Use this in a **local** Claude Code session started inside `D:\CreatED-Quant\quantagents` (recommended, see section 1a), or in a new cloud session on the same GitHub repo. Copy everything inside the box:

```text
You are the lead developer for QuantAgents, taking over a build that a previous Claude Code chat
started. I am the developer and future mentor of this project. I test every phase myself; keep
explanations plain and give me copy-paste PowerShell commands with expected output.

REPOSITORY AND BRANCH
- Repo: github.com/Harsh300604/Quant-Proj, branch `claude/nifty-albattani-era22n`
  (local copy: D:\CreatED-Quant\quantagents). Commit and push only to this branch. No pull requests.

READ FIRST, IN THIS ORDER (before doing anything else)
1. memory.md                      - current state, open items, exact next steps
2. handoff.md                     - working method, rules, mentoring plan
3. implementation_plan.md         - approved phases; ticked = done; "Funding stages"; the
                                    "Additions adopted from the client materials review" section
4. decisions.md                   - decisions D1-D37, deviations from the brief, known issues
5. PROJECT_BRIEF.md               - the specification (single source of truth, with the
                                    deviations recorded in decisions.md)
6. HANDOFF_REQUIREMENTS.md        - final documentation phase (docs/mentoring.md = 16 x 60 min)
7. DEV_CHAT_PROMPT.md             - my original working rules (all still apply)
8. docs/client_materials_review.md - what the QuantAgents paper does and what we adopted
Then skim the code: quantagents/config.py, paths.py, env_secrets.py, data/companies.py,
data/download/*, data/calendar.py, data/etl.py, data/gateway.py, data/quality.py; configs/;
reference/; tests/ (tests/fixtures/synthetic_store.py is the point-in-time test world).
Run `pytest -q` and confirm it passes before changing anything.

WHERE THINGS RUN
- Everything on my laptop lives on D: (C: is nearly full). Every PowerShell session starts with:
    cd D:\CreatED-Quant\quantagents
    Set-ExecutionPolicy -Scope Process Bypass -Force; . .\scripts\env.ps1
  (activates .venv; caches and TEMP go to D:\CreatED-Quant\qa_store). Python 3.12.
- Data store: D:\CreatED-Quant\qa_store\quantagents.duckdb, built by `python -m quantagents.data.etl`.
  Pipeline code reads data ONLY through quantagents/data/gateway.py (company level, D27).
- If you are a cloud session: data websites are blocked there; write code and tests on the
  synthetic store and give me the commands to run on the laptop.
- If you are a local session: you may run tests and scripts, but ASK before any download that
  is larger than a pilot, and before ANY Anthropic API call. Never print, copy or commit .env.

HOW TO WORK
- First reply: a 5-line summary of where the project stands (from memory.md) and your next step.
- Never re-open the brief's section 4 decisions or decisions.md. Ask me when unsure; do not guess.
- One phase (or work block) at a time: build, run its tests, tick implementation_plan.md, update
  memory.md and decisions.md (and handoff.md if the method changes), commit and push, then stop and
  give me: what was built, test results, manual checks (commands, expected output, pass/fail),
  anything I must provide. Wait for my confirmation before the next phase.
- Point-in-time correctness first: leak tests must pass before any backtest; scraped sources use
  only content saved on or before each date (D21); new tests should follow the pattern in
  tests/test_gateway_leaks.py ("nothing after as_of influences results").
- LLMs never do maths; Python computes everything (weights, returns, backtests for Bob's simulated
  trading, risk stats). Every LLM output is validated against a pydantic schema.

API AND MONEY
- Official `anthropic` SDK only, via one wrapper quantagents/llm/client.py (Phase 3). Model IDs:
  claude-haiku-5-5 (memos; everything on the dev tier) and claude-sonnet-5-5 (committee, paper tier).
  Never send temperature, top_p or top_k; never force tool_choice. Structured outputs, prompt
  caching, SQLite response cache keyed WITHOUT the API key, cost ledger with per-key and
  per-stage budgets (configs/keys.yaml, configs/stages.yaml). Read the Claude API docs/skill
  before writing API code; do not guess SDK signatures.
- Funding stages (D22): Stage 0 = my personal key, Rs 300 (budget $3.00, auto-stop $2.40), Haiku
  only. Stage 1 (student key ~$20) and Stage 2 (~$80-90) only after a gate checklist and my approval.
  Before any API step beyond a few test calls: give the estimated cost in USD and INR and wait.

MENTORING (FINAL PHASE)
- After the build, I mentor a student over 16 sessions of 60 minutes; the student re-develops the
  project with the finished repo as the reference. docs/mentoring.md is written at the end.

START WITH the "Next steps" list in memory.md.
```

## 1a. Setting up a local dev chat (on the laptop)

A local Claude Code session works directly in `D:\CreatED-Quant\quantagents`: it can run the tests, the ETL and the reports itself, so there's no copy-paste loop.

1. Install Claude Code on Windows from the official instructions: https://code.claude.com/docs/en/setup (or use the **Code** tab of the Claude desktop app). The program itself and its settings folder are small and live in your user profile on C:; that's the only C: footprint. All project files, caches and temp files stay on D: because you start it from a prepared PowerShell window (step 3).
2. Make sure the laptop copy is up to date:
   ```powershell
   cd D:\CreatED-Quant\quantagents
   git checkout claude/nifty-albattani-era22n
   git pull
   ```
3. Start it from a prepared window, so TEMP and caches point to D::
   ```powershell
   cd D:\CreatED-Quant\quantagents
   Set-ExecutionPolicy -Scope Process Bypass -Force; . .\scripts\env.ps1
   claude
   ```
4. Paste the prompt from section 1.
5. When it asks for permission to run commands, allow tests and scripts; say no to anything that would read or print `.env`, and approve API calls only after it has told you the cost.

---

## 2. The project in brief

- QuantAgents is an LLM multi-agent system that manages a **simulated** NASDAQ-100 portfolio.
- It replays history month by month, 2015–2023, using only information available at each date (point-in-time).
- It compares three things:
  - the **baseline**: the QuantAgents paper's method, adapted to index-relative weights;
  - the **enhanced** version: LLM ratings fed into Black-Litterman;
  - the **benchmarks**: QQQ (total return) and ^NDX.

  It also runs the enhanced version with company names hidden, as a control against the model remembering history.
- Output: a poster at the UT Dallas Biz AI Conference (March 2027). Review package due **15 January 2027**.
- LLMs judge; Python does all the maths. Every LLM output is schema-validated.
- Models: Haiku 5.5 (`claude-haiku-5-5`) for memos; Sonnet 5.5 (`claude-sonnet-5-5`) for the committee.

## 3. How the work is split

| Where | What |
|---|---|
| Cloud dev chat | Writes code and tests; runs tests on synthetic and recorded data; pushes to the branch |
| User's Windows laptop (D: only) | Downloads, DuckDB build, all API calls, all backtests, manual checks |

Data websites are blocked from the cloud session, so never try to download real data there.

## 4. Rules that must not be forgotten

- **Point-in-time first.** All pipeline data access goes through `quantagents/data/gateway.py`. Leak tests must pass before any backtest.
- **API calls:**
  - use the official `anthropic` SDK through `quantagents/llm/client.py` only;
  - never send `temperature`, `top_p` or `top_k`;
  - never force `tool_choice`;
  - use structured outputs, prompt caching, the SQLite response cache (keyed without the API key) and the cost ledger;
  - read the Claude API skill or documentation before writing API code.
- **Budgets:**
  - personal key (`key_label: personal`): $3.00 budget, **automatic stop at $2.40**, shown in USD and INR; `dev` tier (Haiku) only (the Sonnet pilot is Stage 1 on the student key, D23);
  - student key: $150 project cap;
  - no full or long backtests on the personal key.
- **Funding stages (D22):** Stage 0 personal $3.00 (Haiku, small slices) → Stage 1 student ~$20 (Sonnet pilot, thinking decision, first baseline slice) → Stage 2 ~$80–90 (three full runs, after an approved ±20% forecast) → Contingency up to $150 total with explicit approval. Budgets live in `configs/stages.yaml`; the active stage is `budget.stage`; the ledger stops at 80% of the stage budget. At each gate: what was built, evidence, spend vs. budget, next forecast (`docs/cost_forecast.md`), exact amount to request. The money buys test runs, not outcomes; deliverables don't depend on a win.
- **Key swap:** the key comes only from `.env` (`ANTHROPIC_API_KEY`), plus `key_label` and `stage` in config. Never print, log or commit keys.
- **Storage:** all paths come from config and point to `D:\CreatED-Quant\...`. Caches and temp folders are redirected per session by `scripts/env.ps1`. Nothing is written to C:.
- **Phase gate:** build one phase, test it, give the user copy-paste manual checks, then stop.
- **Universe is company level (D27):** share classes and renames are one company (`derived/company_map.csv`); a company's index weight is the sum of its classes.
- **Data gaps are measured, not hidden:** delisted prices come from WRDS/CRSP or a paid vendor (D26, `docs/wrds_export_guide.md`); every gap is logged and checked by red flags.

## 5. Mentoring plan (the user's preferred method)

The mentor (the user) will:
1. first build out the entire project with the dev chat and test it end to end themselves;
2. then teach it to a student over **16 sessions of 60 minutes**, using the finished project as the reference. The student re-develops the project step by step, and the mentor compares the student's work with the reference.

`docs/mentoring.md` is written **at the end of the project** (Phase 9), from the finished code and real run outputs. It must be detailed and structured. For **each session** it gives:
- the objective and learning outcomes;
- prerequisites and reading to do beforehand;
- a 10-minute recap and check of homework;
- the concepts to explain, with pointers to `docs/design.md` sections and code files;
- the student's build task, with exact commands (Windows, D: drive);
- a reference comparison: which files in the finished repo show the answer, and what to look for;
- acceptance checks: tests that must pass and observable results;
- common mistakes and misconceptions;
- homework for next time.

It also includes all sections required by `HANDOFF_REQUIREMENTS.md` §3: learning outcomes, prerequisites, exercises bank, discussion questions, assessment checklist, cost guardrails for students, troubleshooting, further reading.

**Planned 16-session arc** (to be refined in Phase 9):

| # | Session | Student builds or does |
|---|---|---|
| 1 | Project tour and running the finished pilot | Sets up on D:, runs tests and the cached pilot |
| 2 | Finance basics: returns, risk, Sharpe, drawdown, index-relative portfolios | Computes metrics by hand on a small series |
| 3 | Look-ahead and survivorship bias; point-in-time thinking | Finds the bias in planted examples |
| 4 | Setup, config, secrets, storage paths | Config loader, path guard, `.env` handling |
| 5 | Data sources and downloaders | One downloader with resume and manifest |
| 6 | DuckDB store and ETL | ETL into DuckDB tables |
| 7 | The point-in-time gateway and leak tests | Gateway functions; breaks a leak test on purpose |
| 8 | Index weights, sectors, indicators | Derived weights and indicators |
| 9 | Portfolio constraints and the baseline optimizer | Constraint projection |
| 10 | Backtest engine: execution, costs, delistings, resume | Engine with the no-AI index strategy |
| 11 | LLM APIs: structured outputs, caching, response cache, cost ledger | LLM client wrapper and ledger (dev tier) |
| 12 | Agents and the LangGraph pipeline | Memo node, then the committee graph |
| 13 | Black-Litterman: the intuition and the maths | BL module from ratings and confidence |
| 14 | Evaluation: metrics, factor regression, red flags, tearsheets | Report script; reads a tearsheet |
| 15 | Contamination and names-hidden mode; a small extension | Anonymizer or a new indicator or metric |
| 16 | Presenting results honestly; poster review; next steps | Presents findings and limitations |

## 6. Keeping these files current

At the end of every phase or work block, before pushing:
- `memory.md`: current phase, what's done, spend, next step, open questions.
- `decisions.md`: any new decision, deviation or known issue.
- `implementation_plan.md`: tick the tasks.
- `handoff.md`: update only if the working method, rules or mentoring plan change.

## 7. Where things are

| Path | What |
|---|---|
| `PROJECT_BRIEF.md` | Full specification |
| `HANDOFF_REQUIREMENTS.md` | Final documentation requirements |
| `DEV_CHAT_PROMPT.md` | The user's original working rules |
| `implementation_plan.md` | Phase plan with checklists and manual checks |
| `decisions.md` | Decisions, deviations, known issues |
| `memory.md` | Current state |
| `docs/QuantAgents_Client_Requirements.docx` | What the client must provide, with costs |
| `configs/stages.yaml` | Funding-stage budgets (enforced by the ledger from Phase 3) |
| `README.md` | Windows quick start and key swap checklist |
| `quantagents/` | Python package: `config.py`, `paths.py`, `env_secrets.py`, `logs.py`, `data/companies.py`, `data/download/*` |
| `docs/wrds_export_guide.md` | How the student exports delisted-company prices from WRDS/CRSP |
| `docs/client_materials_review.md` | What the QuantAgents paper does; adopted additions D32-D37 |
| `scripts/coverage_quick.py` | Members without price data, per month |
| `scripts/build_client_requirements.js` | Regenerates the client requirements docx |
| `configs/`, `scripts/`, `tests/`, `reference/` | Config, helper scripts, tests, reference CSVs |
