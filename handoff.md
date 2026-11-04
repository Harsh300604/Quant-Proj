# Handoff: continuing QuantAgents in a new dev chat

This file lets a new Claude Code chat pick up the build if the current session is lost (credit limit, disconnect).
It is different from `docs/handoff.md`, which is the **final** handoff document for the mentor, written in Phase 9.

_Last updated: 2026-11-05 (funding stages added)._

---

## 1. Prompt to paste into a new dev chat

Copy everything inside the box below into the new chat:

```text
You are the lead developer for QuantAgents, continuing a build that a previous chat started.
The repository is github.com/Harsh300604/Quant-Proj. Work on branch `claude/nifty-albattani-era22n`
(fetch it, check it out, and push only to it).

Before doing anything else, read these files in this order:
1. memory.md                 – current state: which phase, what's done, spend so far, next step
2. handoff.md                – this file: working method, rules, mentoring plan
3. implementation_plan.md    – the approved phase plan; ticked boxes show completed tasks
4. decisions.md              – every decision, deviation from the brief, and known issue
5. PROJECT_BRIEF.md          – the full specification (single source of truth)
6. HANDOFF_REQUIREMENTS.md   – what the final documentation phase must produce
7. DEV_CHAT_PROMPT.md        – the user's original working rules (all still apply)

Then:
- Reply with a 5-line summary of where the project stands (from memory.md), and what you will do next.
- Do not redo finished work. Do not re-open decisions in PROJECT_BRIEF.md §4 or decisions.md.
- Continue the current phase only. When it is done, run its tests, tick the tasks in
  implementation_plan.md, update memory.md / decisions.md / handoff.md, commit and push,
  then stop and give me the manual checks. Wait for my confirmation before the next phase.
- Ask me before any API spend beyond a few test calls, with a cost estimate.
- Follow the "Funding stages" section of implementation_plan.md: never ask for money ahead of
  evidence; stop at each stage gate with the gate checklist; never cross into the next stage's
  budget without my explicit approval.
- Everything on my laptop lives on the D: drive (C: is full). The code must run on Windows.
```

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
  - personal key (`key_label: personal`): $3.00 budget, **automatic stop at $2.40**, shown in USD and INR; `dev` tier (Haiku) only, plus one approved Sonnet pilot;
  - student key: $150 project cap;
  - no full or long backtests on the personal key.
- **Funding stages (D22):** Stage 0 personal $3.00 (Haiku, small slices) → Stage 1 student ~$20 (Sonnet pilot, thinking decision, first baseline slice) → Stage 2 ~$80–90 (three full runs, after an approved ±20% forecast) → Contingency up to $150 total with explicit approval. Budgets live in `configs/stages.yaml`; the active stage is `budget.stage`; the ledger stops at 80% of the stage budget. At each gate: what was built, evidence, spend vs. budget, next forecast (`docs/cost_forecast.md`), exact amount to request. The money buys test runs, not outcomes; deliverables don't depend on a win.
- **Key swap:** the key comes only from `.env` (`ANTHROPIC_API_KEY`), plus `key_label` and `stage` in config. Never print, log or commit keys.
- **Storage:** all paths come from config and point to `D:\CreatED-Quant\...`. Caches and temp folders are redirected per session by `scripts/env.ps1`. Nothing is written to C:.
- **Phase gate:** build one phase, test it, give the user copy-paste manual checks, then stop.

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
| `quantagents/` | Python package: `config.py`, `paths.py`, `env_secrets.py`, `logs.py`, `data/download/*` |
| `configs/`, `scripts/`, `tests/`, `reference/` | Config, helper scripts, tests, reference CSVs |
