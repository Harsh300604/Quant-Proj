# Memory: 20-stock prototype track (proto20)

Short, factual and always up to date for the prototype track. Update it at the end of every P-phase, before pushing.
The general project state (Phase 1 facts, environment, preferences, funding table) is in `memory.md` and still applies.

_Last updated: 2026-11-12 (MVP budget set, D46; user finished P0 steps 1–8)._

## Where we are

| Item | State |
|---|---|
| Plan | `implementation_plan_20.md` (approved 6 Nov 2026); decisions D38–D46 in `decisions_20.md` |
| Main plan position | Phase 1 closed; Phase 2 built (225 tests), user's manual checks pending |
| Current P-phase | **P0** (user, laptop): steps 1–8 of `handoff_20.md` done on 12 Nov; outputs to be pasted into the dev chat. Remaining: ADR ratios for foreign filers in the 2021-01-04 top 30; student key in `.env` |
| Branch | `claude/nifty-albattani-era22n` (push here only) |
| Funding | **MVP budget $40 on the student key** (D46): $0.00 spent; auto-stop at $32; hard cap $40. The key's Console limit is $200 (outer safety net only). Personal key not used |
| Norgate | Email and company list prepared for the student (sent outside the repo); not needed for proto20 |

## proto20 facts

- Universe: top 20 companies by derived cap weight at the close of 2021-01-04, fixed (D39). Frozen list will be `reference/proto20_universe.csv` (created in P1).
- Period: 2021-01 to 2023-12, 36 rebalances (D40). Dev slice: 2021 only (`configs/proto20_2021.yaml`).
- Benchmark: proto20 cap-weighted index of the same 20 (D41); QQQ and ^NDX as reference only.
- All 20 get committee views (D42).
- No hard-coding of N or dates (D45).

## Next steps (in order)

1. **P0 (user):** main Phase 2 manual checks 1–5; `python -m quantagents.data.gateway --as-of 2021-01-04 --show universe`; fill `reference/adr_ratios.csv` for 20-F/40-F filers in the top 30; paste outputs.
2. **P1:** `configs/stages.yaml` gets the `proto20` stage (D46); ADX/RVOL (D36); `quantagents/data/universe.py`; `quantagents/eval/benchmarks.py`; config `universe.mode`; `configs/proto20.yaml`, `configs/proto20_2021.yaml`; `scripts/proto20_universe.py`; tests.
3. **P2:** main Phase 3 (LLM layer), on the student key in the laptop `.env`, inside the $40 MVP budget (D46).
4. **P3 → P7** as in `implementation_plan_20.md`.

## Open questions waiting on the user

- None yet for proto20. Items from `memory.md` (ADR ratios, ticker-reuse findings, success criterion with the professor, poster rules) still apply.
