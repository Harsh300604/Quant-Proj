# Memory: current state of the build

Short, factual and always up to date. Update it at the end of every phase or work block, before pushing.
History belongs in `decisions.md`; the plan lives in `implementation_plan.md`.

_Last updated: 2026-11-05 (Phase 1 manual checks in progress)._

## Where we are

| Item | State |
|---|---|
| Plan | `implementation_plan.md`, approved 2026-11-04 |
| Current phase | **Phase 1: Setup, config and downloaders.** Built; 61 tests pass; **waiting for the user's manual checks on the laptop** |
| Phases done | none |
| Branch | `claude/nifty-albattani-era22n` (push here only) |
| Last step | User passed manual checks 1–3. Pilot download (check 4) worked except membership before ~2018 (parser); parser fixed, 64 tests pass |
| Next step | User does `git pull`, reruns `run_all --pilot` (membership pages are cached, so it's fast). If snapshots still need review, user sends the `membership --diagnose` output. Then checks 5–6 |

## Spend so far

| Key label | Spent | Budget | Hard stop |
|---|---|---|---|
| personal | $0.00 | $3.00 | $2.40 |
| student | not received yet | $150 | per-run budgets in config |

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

## Phase 1 facts a new chat needs

- Python 3.12 is required (D15). Package: `quantagents/` with an editable install (`pip install -e .`).
- Downloads: `python -m quantagents.data.download.run_all --pilot | --all`. Raw files go to `<storage>/raw/...` with `manifest.jsonl`. Membership spells go to `<storage>/derived/ndx_membership.csv`.
- Hand-maintained corrections live in `reference/*.csv`.
- Tests: `pytest -q`. Sockets are blocked in tests; HTTP is mocked with `responses`; storage root is redirected via the `QA_STORE_ROOT` env var.
- The `.ps1` scripts have never been executed (no PowerShell in the cloud). Fix them from the user's error output if needed.

## Open questions waiting on the user

- Pilot rerun result after the parser fix; later, the missing-ticker counts from the full download.
- `ANTHROPIC_API_KEY` is still empty in the laptop `.env` (not needed until Phase 3).
