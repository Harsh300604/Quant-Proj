# Decisions, Deviations and Known Issues

Running log of every decision, deviation from `PROJECT_BRIEF.md`, and known issue. Newest entries at the bottom of each table.
The final handoff documents (`docs/handoff.md`, `docs/design.md`, `docs/mentoring.md`) are written from this file, so keep it current.

## Decisions

| Date | ID | Decision | Made by | Why |
|---|---|---|---|---|
| 2026-11-04 | D1 | Code and tests are written in the cloud session; downloads, DuckDB, API calls and runs happen on the developer's Windows laptop under `D:\CreatED-Quant\` | Developer (approved) | Data hosts are blocked from the cloud session; C: is full; data must persist |
| 2026-11-04 | D2 | NASDAQ-100 membership reconstructed for free from Wikipedia change tables, cross-checked against Nasdaq announcements; source behind a swappable interface | Developer (approved) | No paid dataset or WRDS confirmed; open decision 1 |
| 2026-11-04 | D3 | Delisted prices: yfinance plus optional user CSVs; members with no data are dropped for that date, weight redistributed, logged; red flag if > 2% of index weight is missing | Developer (approved) | yfinance gaps for delisted tickers |
| 2026-11-04 | D4 | Success criterion: information ratio + Carhart alpha (with Sharpe, Sortino, max drawdown), pending professor confirmation | Developer (approved) | Open decision 2 |
| 2026-11-04 | D5 | Sector band ±2 pp; rating table defaults −6/−3/0/+3/+6 %, monthly = 3-month ÷ 3 | Developer (approved) | Open decisions 3 and 4 |
| 2026-11-04 | D6 | Index weights: plain derived cap weights (no Nasdaq capping rules); GOOG and GOOGL kept as separate members | Developer (approved) | Simplicity; validated by tracking error vs. QQQ |
| 2026-11-04 | D7 | Sector from SEC SIC code mapped to 11 GICS-like sectors; country from EDGAR business address; static per company | Developer (approved) | GICS is proprietary |
| 2026-11-04 | D8 | Geography reported and checked, not enforced as a band | Developer (approved) | Brief only enforces sector bands |
| 2026-11-04 | D9 | `as_of` = 4 pm ET close of the first trading day of the month; trade at next open | Developer (approved) | Ambiguity in brief §4 |
| 2026-11-04 | D10 | Brief's suggested layout placed inside a `quantagents/` package | Developer (approved) | Avoids name clashes with `data`/`eval` |
| 2026-11-04 | D11 | Personal key: `key_label: personal`, $3.00 budget, stop at $2.40, INR shown at configurable rate (default ₹88/$) | Developer | Temporary ₹300 key limit |
| 2026-11-04 | D12 | Session continuity files at repo root: `handoff.md` (prompt for a new dev chat), `memory.md` (current state), `decisions.md` (this log). Updated at the end of every phase or work block | User | The cloud session may disconnect (credit limit) |
| 2026-11-04 | D13 | `docs/mentoring.md` is written at the end of the project and covers **16 sessions of 60 minutes**. The mentor first builds and tests the whole project, then uses it as the reference while teaching the student to develop it | User | The mentor's preferred teaching style |
| 2026-11-04 | D14 | The Alpaca account (news) is created by the developer/mentor, not the client | User | Free, and only needed for downloading news |

## Deviations from PROJECT_BRIEF.md

| Date | Brief says | We do | Why |
|---|---|---|---|
| 2026-11-04 | Index weights preferably official | Derived cap weights without capping rules | No free official history (D6) |
| 2026-11-04 | No survivorship bias | Members with no price data at all are dropped for that date (logged, measured) | Free data gaps (D3) |
| 2026-11-04 | `HANDOFF_REQUIREMENTS.md`: mentoring plan of 6–10 sessions of 60–90 min | 16 sessions of 60 min, student re-develops the project with the finished repo as reference | User's mentoring style (D13) |

## Known issues

| Date | Issue | Impact | Status |
|---|---|---|---|
| 2026-11-04 | Free membership reconstruction may contain dating errors | Universe may differ slightly from the true index | Open; spot-checks in Phase 1 |
| 2026-11-04 | Cloud dev session cannot reach Yahoo, SEC, Alpaca, Wikipedia, FRED, French library (only PyPI and api.anthropic.com) | Downloaders can only be tested offline with recorded samples here; first real test is on the laptop | Accepted (D1) |
