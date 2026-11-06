# Handoff: building the 20-stock prototype (proto20) in a new dev chat

Section 1 is the user's laptop preparation, done before the dev chat starts. Section 2 is the prompt to paste into the dev chat.
The general handoff (`handoff.md`) still applies; this file only adds the prototype track.

_Last updated: 2026-11-06._

---

## 1. Laptop preparation (run these before starting the dev chat)

Open **PowerShell** and run each block in order. Paste any output that doesn't match the "Expected" line into the dev chat.

**1. Open the project and prepare the window.** Do this in every new PowerShell window.
```powershell
cd D:\CreatED-Quant\quantagents
Set-ExecutionPolicy -Scope Process Bypass -Force; . .\scripts\env.ps1
```
Expected: the prompt starts with `(.venv)`.

**2. Get the latest code, including these `_20` documents.**
```powershell
git fetch origin claude/nifty-albattani-era22n
git checkout claude/nifty-albattani-era22n
git pull origin claude/nifty-albattani-era22n
```
Expected: `implementation_plan_20.md`, `decisions_20.md`, `memory_20.md` and `handoff_20.md` exist (`dir *_20.md`).

**3. Check Python and install the packages.**
```powershell
python --version
pip install -r requirements.txt
pip install -e .
```
Expected: `Python 3.12.x`, and the installs finish without errors.

**4. Check the machine setup.**
```powershell
python scripts\check_env.py
```
Expected: only OK, WARN or INFO lines. `ANTHROPIC_API_KEY` may show as missing until step 9.

**5. Run all tests.**
```powershell
pytest -q
```
Expected: `225 passed`.

**6. Build the data store.** This takes a few minutes.
```powershell
python -m quantagents.data.etl
```
Expected: it ends with `DuckDB written: D:\CreatED-Quant\qa_store\quantagents.duckdb`, and the row counts for prices, fundamentals, news, indicators and index_weights are well above 0.

**7. Run the leak tests on the built store.**
```powershell
pytest -q tests\test_gateway_leaks.py tests\test_timezones.py tests\test_filing_dates.py
```
Expected: all passed.

**8. Look at the data.**
```powershell
python -m quantagents.data.gateway --as-of 2016-03-01 --show universe
python -m quantagents.data.gateway --as-of 2021-01-04 --show universe
python -m quantagents.data.gateway --as-of 2021-01-04 --show sectors
python scripts\data_report.py
```
Expected:
- about 100 companies on each date, with `weights sum to 1.000`;
- on 2021-01-04, the top rows are names like Apple, Microsoft, Amazon, Alphabet, Facebook and Tesla, and the top 20 all show `has_prices = True`;
- the data report shows the delisted-price RED FLAG for 2015. That's expected (D26) and doesn't affect proto20.

Save the 2021-01-04 output and the data report output, because the dev chat needs both.

**9. Add your personal Anthropic key.** This is the Stage 0 key with ₹300.
- In the Anthropic Console, make sure this key's workspace has a spend limit no higher than the ₹300 credit.
- Then add the key to `.env`:
  ```powershell
  notepad .env
  ```
  Put the key after `ANTHROPIC_API_KEY=`, then save and close. Never paste the key into a chat.
- Check it:
  ```powershell
  python scripts\check_env.py
  ```
  Expected: the `ANTHROPIC_API_KEY` line shows as set. The value is never printed.

**10. Start the local dev chat** from the same prepared window (see `handoff.md` section 1a for installing Claude Code).
```powershell
claude
```
Then paste the prompt from section 2.

---

## 2. Prompt to paste into the dev chat

```text
You are the lead developer for QuantAgents, taking over a build that a previous Claude Code chat
started. I am the developer and future mentor of this project. I test every phase myself; keep
explanations plain and give me copy-paste PowerShell commands with expected output.

THE TASK: build the 20-stock prototype track ("proto20") end to end, phase by phase (P0-P7), as
described in implementation_plan_20.md. It is a first complete version of the whole project on the
20 largest NASDAQ-100 companies (chosen by market cap at the close of 2021-01-04, held fixed),
2021-2023, benchmarked against a cap-weighted index of the same 20 companies, so the student has
results for the professor before the full 100-stock run. The original plan stays unchanged and
resumes afterwards; nothing may be hard-coded to 20 stocks or 2021-2023 (D45).

REPOSITORY AND BRANCH
- Repo: github.com/Harsh300604/Quant-Proj, branch `claude/nifty-albattani-era22n`
  (local copy: D:\CreatED-Quant\quantagents). Commit and push only to this branch. No pull requests.

READ FIRST, IN THIS ORDER (before doing anything else)
1. memory_20.md            - prototype state and next steps (START HERE)
2. implementation_plan_20.md - the prototype plan: P0-P7, files, tests, manual checks
3. decisions_20.md         - prototype decisions D38-D45
4. memory.md               - general project state, environment, preferences, funding table
5. handoff.md              - working method, rules, mentoring plan (sections 3-4 are rules)
6. implementation_plan.md  - the main plan; proto20 phases say "as in main Phase N", so the
                             main phase's files, tasks and tests apply unless a difference is listed
7. decisions.md            - D1-D37, deviations from the brief, known issues (all still apply)
8. PROJECT_BRIEF.md        - the specification
9. docs/client_materials_review.md - the QuantAgents paper and what we adopted (D32-D37)
10. DEV_CHAT_PROMPT.md and HANDOFF_REQUIREMENTS.md - original working rules and final-docs phase
Then skim the code: quantagents/config.py, paths.py, env_secrets.py, data/companies.py,
data/calendar.py, data/etl.py, data/gateway.py, data/quality.py; configs/base.yaml, pilot.yaml,
keys.yaml, stages.yaml; reference/; tests/ (tests/fixtures/synthetic_store.py is the point-in-time
test world; tests/test_gateway_leaks.py is the pattern for leak tests).
Run `pytest -q` and confirm it passes (225) before changing anything.

KEY POINTS OF THE PROTOTYPE (details in implementation_plan_20.md)
- Universe rule (D39): top 20 companies (company level, D27) by derived cap weight from
  gateway.get_index_weights at the close of 2021-01-04, among members with prices; ties by
  company_id; fixed for the period; frozen in reference/proto20_universe.csv. Never hand-pick.
- Period (D40): 2021-01 to 2023-12, 36 monthly rebalances; Stage 0 slice = 2021 only.
- Benchmark (D41): cap-weighted index of the same 20 (weights at the close of t-1 apply to returns
  on t, as in data/quality.py index_vs_benchmark). 0x-2x multiples and +-2 pp sector bands are
  measured against it. If a rebalance is infeasible, stop and ask; never loosen constraints yourself.
  QQQ and ^NDX are reference rows only. Never claim "beats the NASDAQ-100" from proto20.
- All 20 get committee views (D42): max_views 20, max_per_sector null.
- Config: extend `universe` with mode (index_members | tickers | top_n_by_cap), top_n, chosen_at,
  keep_fixed; add `benchmark.mode`. base.yaml and pilot.yaml must keep working unchanged.
- ADR ratios (reference/adr_ratios.csv) must be filled for foreign filers near the top before the
  universe is frozen, or a market cap can be wrong by up to 10x (P0).

WHERE THINGS RUN
- Everything on my laptop lives on D: (C: is nearly full). Every PowerShell session starts with:
    cd D:\CreatED-Quant\quantagents
    Set-ExecutionPolicy -Scope Process Bypass -Force; . .\scripts\env.ps1
  (activates .venv; caches and TEMP go to D:\CreatED-Quant\qa_store). Python 3.12.
- Data store: D:\CreatED-Quant\qa_store\quantagents.duckdb, built by `python -m quantagents.data.etl`.
  Pipeline code reads data ONLY through quantagents/data/gateway.py.
- If you are a cloud session: data websites are blocked there; write code and tests on the
  synthetic store and give me the commands to run on the laptop.
- If you are a local session: you may run tests and scripts, but ASK before any large download and
  before ANY Anthropic API call. Never print, copy or commit .env.

HOW TO WORK
- First reply: a 5-line summary of where the project stands (from memory_20.md and memory.md) and
  your next step. I will paste my P0 outputs (2021-01-04 universe and the data report).
- Never re-open the brief's section 4 decisions, decisions.md or decisions_20.md. Ask me when
  unsure; do not guess.
- One P-phase at a time: build, run its tests, tick implementation_plan_20.md, update memory_20.md
  (and decisions_20.md for any new decision, numbered from D46), commit and push, then stop and
  give me: what was built, test results, manual checks (commands, expected output, pass/fail),
  anything I must provide. Wait for my confirmation before the next phase.
- Edit the _20 documents for prototype work. Only touch implementation_plan.md / memory.md /
  decisions.md when a main-plan item is completed (e.g. ADX/RVOL closes a main Phase 2 task).
- Point-in-time correctness first: leak tests must pass before any backtest; new tests follow
  "nothing after as_of influences results" (rebuild the store with a cutoff and compare).
- LLMs never do maths; Python computes everything (weights, returns, simulated trading for Bob,
  risk stats for Dave, the benchmark). Every LLM output is validated against a pydantic schema.

API AND MONEY
- Official `anthropic` SDK only, via one wrapper quantagents/llm/client.py (P2 = main Phase 3).
  Model IDs: claude-haiku-5-5 (memos; everything on the dev tier) and claude-sonnet-5-5 (committee,
  paper tier). Never send temperature, top_p or top_k; never force tool_choice. Structured outputs,
  prompt caching, SQLite response cache keyed WITHOUT the API key, cost ledger with per-key and
  per-stage budgets (configs/keys.yaml, configs/stages.yaml), automatic stop at 80%. Read the Claude
  API docs/skill before writing API code; do not guess SDK signatures.
- Funding stages (D22, D43): Stage 0 = my personal key, Rs 300 (budget $3.00, auto-stop $2.40),
  Haiku only: development, the 5-stock pilot and the proto20 2021 dev slice. proto20 2021-2023
  paper-tier runs happen only in Stage 1 (student key, ~$20), after a measured forecast and my
  go-ahead. Before any API step beyond a few test calls: give the estimated cost in USD and INR
  and wait for my yes. If the forecast does not fit, stop and ask; never shorten the period or drop
  a variant on your own.

MENTORING (FINAL PHASE)
- After the build, I mentor a student over 16 sessions of 60 minutes; docs/mentoring.md is written
  at the end (handoff.md section 5).

START WITH the "Next steps" list in memory_20.md.
```
