# Memory: current state of the build

Short, factual and always up to date. Update it at the end of every phase or work block, before pushing.
History belongs in `decisions.md`; the plan lives in `implementation_plan.md`.

_Last updated: 2026-11-06 (handover point: this chat ends here; a new dev chat continues)._

> **Active track: the 20-stock prototype (proto20).** Approved 6 Nov 2026: the whole project is built first on the 20 largest NASDAQ-100 companies (2021–2023), before the full run. For current work, read these first: `memory_20.md` (state and next steps), `implementation_plan_20.md` (phases P0–P7), `decisions_20.md` (D38–D45) and `handoff_20.md` (laptop prep and the dev-chat prompt). This file and the other original docs stay valid for the general project state and for the full run, which resumes after proto20.

## Where we are

| Item | State |
|---|---|
| Plan | `implementation_plan.md`, approved 2026-11-04 |
| Current phase | **Phase 2** built and pushed (225 tests); **user's manual checks pending** (pip install, ETL build, leak tests, gateway CLI, data report) |
| Phases done | **Phase 1** (closed 6 Nov; open item: 42 delisted-ticker prices, D26) |
| Branch | `claude/nifty-albattani-era22n` (push here only) |
| Last step | Client materials reviewed; all 7 suggestions adopted (D32-D37) and written into the plan; handoff prompt + local setup written |
| Next step | **proto20 track:** see `memory_20.md` → Next steps (P0 first). The list below is the full-run order and resumes after proto20 |

## Spend so far and funding stage

Active stage: **Stage 0** (personal key). Funding policy in `implementation_plan.md` → "Funding stages" (decision D22).

| Stage | Key label | Spent | Budget | Auto-stop | Status |
|---|---|---|---|---|---|
| 0 | personal | $0.00 | $3.00 | $2.40 | active |
| 1 | student | — | ~$20 | $16.00 | not released (needs the Stage 0 gate) |
| 2 | student | — | ~$80–90 | $72.00 | not released (needs an approved forecast) |
| Contingency | student | — | up to $150 total | — | only with explicit approval |

## What the user has provided

- [x] Alpaca account created; the user has the key ID and secret. They go into `.env` on the laptop at Phase 1's manual checks, never into chat.
- [ ] SEC User-Agent name and email (the user supplies it in `.env`)
- [ ] Personal Anthropic key in the laptop's `.env` (the user does this)
- [ ] Student Anthropic key (needed by week 4)
- [ ] Professor's confirmation of the success criterion (needed by week 4)
- [ ] Poster rules (needed by week 8)

## Environment facts (verified)

- The cloud session runs Linux with Python 3.13. Only PyPI and `api.anthropic.com` are reachable. Yahoo, SEC, Alpaca, Wikipedia, FRED and the French library are **blocked**. So downloaders are tested offline with recorded sample responses; real downloads run on the user's laptop.
- The user's laptop runs Windows. Everything lives on D:. Repo: `D:\CreatED-Quant\quantagents`. Data, caches, runs and logs: `D:\CreatED-Quant\qa_store\`. Every PowerShell session starts with `. .\scripts\env.ps1`.
- No API key is configured in the cloud session. Live API calls happen only on the laptop.

## User preferences (keep following)

- Plain explanations; the user tests every phase themselves.
- Stop after each phase with: what was built, test results, copy-paste manual checks with expected output, and what the user must provide.
- Ask before any API spend beyond a few test calls, with a cost estimate.
- Never re-open the decisions in brief §4. Ask when something is ambiguous.
- Keep `handoff.md`, `memory.md` and `decisions.md` current.
- Mentoring: 16 sessions × 60 min, `docs/mentoring.md` written at the end (see `handoff.md`).
- Funding: never ask for money ahead of evidence. At each stage gate give: what was built, evidence, spend vs. stage budget, next-stage forecast, exact amount to request. The money buys test runs, not outcomes.

## Phase 1 facts a new chat needs

- Company level (D27): `derived/company_map.csv` (ticker → company_id), company spells `derived/ndx_membership_companies.csv`; ticker-level files kept for downloads. SEC name lookup (D28): `raw/edgar/cik_matches.csv`.
- Phase 2: store = `qa_store/quantagents.duckdb` built by `python -m quantagents.data.etl`; access ONLY via `quantagents.data.gateway.Gateway` (company level). Rules in the plan's Phase 2 'Availability rules' table and D29-D31.
- Python 3.12 is required (D15). Package: `quantagents/` with an editable install (`pip install -e .`).
- Downloads: `python -m quantagents.data.download.run_all --pilot | --all`. Raw files go to `<storage>/raw/...` with `manifest.jsonl`. Membership spells go to `<storage>/derived/ndx_membership.csv`.
- Hand-maintained corrections live in `reference/*.csv`.
- Tests: `pytest -q`. Sockets are blocked in tests; HTTP is mocked with `responses`; storage root is redirected via the `QA_STORE_ROOT` env var.
- The `.ps1` scripts have never been executed (no PowerShell in the cloud). Fix them from the user's error output if needed.

## Open questions waiting on the user

- **Client materials review** (`docs/client_materials_review.md`): which of the 7 suggestions to adopt (ENT/ENB metrics, Python simulated trading for Bob, risk-score inputs for Dave, track-record memory, paper persona wording, ADX/RVOL, poster framing).

- **Delisted prices (blocks Phase 1 close):** 43 of 192 tickers have no Yahoo prices (30% of members in 2015 → 6% in 2023). Decided (D26): WRDS/CRSP via UT Dallas first, else a paid one-month vendor download. Waiting for the client/student to check WRDS access.

- **Share classes:** answered 6 Nov → company level (D27), built.

- Full-download results: summary table, Yahoo-missing count, SEC-missing count.
- Optional: confirm the 2016-03-01 CSX added / KLAC removed change.
- `ANTHROPIC_API_KEY` is still empty in the laptop `.env` (not needed until Phase 3).

## Next steps (in order)

_Current work follows `memory_20.md`. proto20's P0–P1 cover steps 1–3 below; steps 4–6 come after proto20, except that the main Phase 3–5 code is built during proto20 P2–P4._

1. **Phase 2 manual checks** (user, laptop): `git pull`, `pip install -r requirements.txt`, `pytest -q`
   (225 passed), `python -m quantagents.data.etl`, leak tests, `python -m quantagents.data.gateway
   --as-of 2016-03-01 --show universe` / `--show sectors`, `python scripts\data_report.py`.
2. **From the data report:** fill `reference/adr_ratios.csv` for 20-F/40-F filers (section 3);
   fix ticker-reuse findings (section 2); check the derived index vs QQQ (section 4).
3. **Phase 2 follow-ups:** ADX(14) + RVOL(20) indicators (D36) with tests; then close Phase 2.
4. **Delisted prices (D26):** waiting on WRDS (UT Dallas) or a paid vendor (Norgate). When the file
   arrives, write the importer to match it exactly (`docs/wrds_export_guide.md`).
5. **Phase 3:** LLM layer (client wrapper, response cache, cost ledger with key and stage budgets,
   80% stops) and 5 research memos on Haiku. Read the Claude API docs first. Needs the user's
   personal key in `.env` (`ANTHROPIC_API_KEY` is still empty on the laptop).
6. Phase 4 (constraints, optimizer, backtest engine), then Phase 5 incl. D32-D35, Stage 0 gate.

## Documents sent to the user (not in the repo)

- 6 Nov: completed project scope docx for the student/parent (template from the user; contains the student's name, so kept out of git). Student age, grade, location and background left highlighted for the family to fill in. Costs section matches the funding stages (D22) and D26.
