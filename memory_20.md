# Memory: 20-stock prototype track (proto20)

Short, factual and always up to date for the prototype track. Update it at the end of every P-phase, before pushing.
The general project state (Phase 1 facts, environment, preferences, funding table) is in `memory.md` and still applies.

_Last updated: 2026-11-12 (P0 done by the local dev chat; data bugs fixed; waiting for the user to confirm P0)._

## Where we are

| Item | State |
|---|---|
| Plan | `implementation_plan_20.md` (approved 6 Nov 2026); decisions D38–D46 in `decisions_20.md` |
| Main plan position | Phase 1 closed; Phase 2 manual checks done 12 Nov (237 tests); Phase 2 follow-ups still open: ADX/RVOL (P1), ADR ratios for AZN/VIP/VOD (full run) |
| Current P-phase | **P0 done, waiting for the user's confirmation**; next is P1 |
| Session | Local Claude Code session on the laptop: it runs tests, the ETL and small downloads itself; it asks before large downloads and before any API call |
| Branch | `claude/nifty-albattani-era22n` (push here only) |
| Funding | **MVP budget $40 on the student key** (D46): $0.00 spent; auto-stop at $32; hard cap $40. The key's Console limit is $200 (outer safety net only). Personal key not used |
| Norgate | Email and company list prepared for the student (sent outside the repo); not needed for proto20 |

## proto20 facts

- Universe: top 20 companies by derived cap weight at the close of 2021-01-04, fixed (D39). Frozen list will be `reference/proto20_universe.csv` (created in P1).
- **The live rule gives (12 Nov store):** AAPL, MSFT, AMZN, GOOGL, FB, TSLA, NVDA, PYPL, ADBE, CMCSA, NFLX, ASML, INTC, PEP, PDD, CSCO, AVGO, COST, QCOM, TMUS. 21st is TXN (1.007% vs TMUS 1.111%).
- PDD is classed as Industrials (from its SEC SIC code, D7): open question for the user (below).
- Period: 2021-01 to 2023-12, 36 rebalances (D40). Dev slice: 2021 only (`configs/proto20_2021.yaml`).
- Benchmark: proto20 cap-weighted index of the same 20 (D41); QQQ and ^NDX as reference only.
- All 20 get committee views (D42).
- No hard-coding of N or dates (D45).
- MVP first: build only what proto20 needs; log full-run items as deferred.
- Student guide: `docs/proto20_student_guide.md`, plain language, updated every phase (convert to docx at the end).

## Next steps (in order)

1. **User:** confirm P0; answer the PDD sector question.
2. **P1:** `configs/stages.yaml` gets the `proto20` stage (D46); ADX/RVOL (D36); `quantagents/data/universe.py`; `quantagents/eval/benchmarks.py`; config `universe.mode`; `configs/proto20.yaml`, `configs/proto20_2021.yaml`; `scripts/proto20_universe.py`; tests.
3. **P2:** main Phase 3 (LLM layer), on the student key in the laptop `.env`, inside the $40 MVP budget (D46).
4. **P3 → P7** as in `implementation_plan_20.md`.

## Deferred to the full run (not needed for proto20)

- ADR ratios for AZN, VIP, VOD; Baidu has no SEC share count after 2010; Baidu/Trip.com 2021 share subdivisions (ratio vs share-count units).
- Marvell predecessor filer (no MRVL weight before April 2021); Okta has no share count.
- 2015 derived index vs QQQ (tracking error 11.6%; mostly the delisted-price gap, D26).

## Open questions waiting on the user

- **PDD sector:** SIC puts Pinduoduo in Industrials. Override to Consumer Discretionary (like Amazon and JD) in `reference/sector_overrides.csv`, or keep the SIC rule (D7)?
- Items from `memory.md` (ticker-reuse findings, success criterion with the professor, poster rules) still apply.
