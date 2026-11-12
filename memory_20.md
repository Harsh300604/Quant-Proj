# Memory: 20-stock prototype track (proto20)

Short, factual and always up to date for the prototype track. Update it at the end of every P-phase, before pushing.
The general project state (Phase 1 facts, environment, preferences, funding table) is in `memory.md` and still applies.

_Last updated: 2026-11-12 (P1 built and pushed; waiting for the user to confirm P1)._

## Where we are

| Item | State |
|---|---|
| Plan | `implementation_plan_20.md` (approved 6 Nov 2026); decisions D38–D47 in `decisions_20.md` |
| Main plan position | Phase 1 closed; Phase 2 done except ADR ratios for AZN/VIP/VOD and the delisted-price importer (both full run) |
| Current P-phase | **P0 done** (confirmed by the user); **P1 built, waiting for the user's confirmation**; next is P2 (LLM layer) |
| Tests | 262 pass |
| Session | Local Claude Code session on the laptop: it runs tests, the ETL and small downloads itself; it asks before large downloads and before any API call |
| Branch | `claude/nifty-albattani-era22n` (push here only) |
| Funding | **MVP budget $40 on the student key** (D46): $0.00 spent; auto-stop at $32; hard cap $40. `configs/stages.yaml` has `proto20`; `base.yaml`, `pilot.yaml` and the proto20 configs use `student / proto20`. The key's Console limit is $200 (outer safety net only) |
| Norgate | Not needed for proto20 |

## proto20 facts

- Universe (frozen in `reference/proto20_universe.csv`, rule D39, `--check` OK on 12 Nov): AAPL, MSFT, AMZN, GOOGL, FB, TSLA, NVDA, PYPL, ADBE, CMCSA, NFLX, ASML, INTC, PEP, PDD, CSCO, AVGO, COST, QCOM, TMUS. These are 74.6% of the whole index; Apple is 19.9% of the 20. 21st is TXN.
- PDD is Consumer Discretionary (D47).
- Benchmark (same 20 at market weight, `quantagents/eval/benchmarks.py`): +32.7% (2021), −37.0% (2022), +68.9% (2023); QQQ +27.4%, −32.6%, +54.9%. No missing weights on any day.
- Code: `quantagents/data/universe.py` (`resolve_universe(cfg, gw).at(gw, as_of)`), `config.universe.mode` (index_members | tickers | top_n_by_cap), `config.benchmark.mode` (index | custom_cap_index).
- Period: 2021-01 to 2023-12, 36 rebalances (D40). Dev slice: 2021 only (`configs/proto20_2021.yaml`).
- All 20 get committee views (D42); `selection.max_per_sector: null`.
- No hard-coding of N or dates (D45). MVP first: build only what proto20 needs; log full-run items as deferred.
- Student guide: `docs/proto20_student_guide.md`, plain language, updated every phase (convert to docx at the end).

## Next steps (in order)

1. **User:** P1 manual checks and confirmation.
2. **P2 = main Phase 3:** read the Claude API skill/docs first; `llm/client.py`, `cache.py`, `ledger.py` (with stage `proto20` and the $32 stop test), `pricing.py`, memo schema, prompt and node, `scripts/ledger_report.py`. Manual checks: 5 pilot memos on Haiku (≈ $0.002) and 3 proto20 memos on 2021-01-04 (≈ $0.01); **ask before each paid call**.
3. **P3 → P7** as in `implementation_plan_20.md`.

## Deferred to the full run (not needed for proto20)

- ADR ratios for AZN, VIP, VOD; Baidu has no SEC share count after 2010; Baidu/Trip.com 2021 share subdivisions (ratio vs share-count units).
- Marvell predecessor filer (no MRVL weight before April 2021); Okta has no share count.
- MercadoLibre and eBay sectors (SIC → Industrials).
- 2015 derived index vs QQQ (tracking error 11.6%; mostly the delisted-price gap, D26).

## Open questions waiting on the user

- Check the ADR rows marked "check" in `reference/adr_ratios.csv`. JD = 2 and PDD = 4 matter for proto20.
- Items from `memory.md` (success criterion with the professor, poster rules) still apply.
