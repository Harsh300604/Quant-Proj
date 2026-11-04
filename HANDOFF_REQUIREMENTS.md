# Handoff Requirements: Final Documentation Phase

This file tells the development chat what to produce **after the project is built and the final results exist**. It is part of the project scope, not optional. Add it to `implementation_plan.md` as the **final phase**, after the poster materials.

## Why these documents exist

Once the build is finished, QuantAgents passes to a **mentor**. The mentor guides a **student** through the project: running it, understanding it, and extending it. The mentor did not take part in the build and may not know the codebase, LangGraph or the finance concepts in depth. From these documents alone, the mentor must be able to:

1. Understand what the project is, why it was built and what it found.
2. Set it up and run it.
3. Explain the design and its trade-offs.
4. Teach it to a student step by step and judge the student's progress.

**Write for a capable reader who is new to this project.** Be plain, specific and honest:
- Explain jargon the first time it appears.
- Prefer diagrams, tables and exact commands over long prose.
- State limitations and known issues openly.

## Deliverables

Create these in a `docs/` folder at the repository root:

| File | Audience | Purpose |
|---|---|---|
| `docs/handoff.md` | Mentor (first read) | What the project is, its state, how to run it, results, limitations |
| `docs/handoff.docx` | Mentor and non-technical stakeholders | The same content as `handoff.md`, as a formatted Word document |
| `docs/design.md` | Mentor and student (technical) | How the system works and why it was built this way |
| `docs/mentoring.md` | Mentor | How to teach the project to a student: sessions, exercises, checks |

All figures, tables and numbers must come from the **actual final runs** (the `runs/` outputs and the evaluation report), not from estimates in `PROJECT_BRIEF.md`. Where reality differs from the brief, say so.

---

## 1. `docs/handoff.md` (and `docs/handoff.docx`)

The mentor's starting point. Target length: 4–8 pages.

1. **Project in one paragraph:** what it is, who it is for, and the conference poster context.
2. **Status at handoff:**
   - What is complete, partial or not built.
   - A table of committed, stretch and out-of-scope items with their final state.
3. **Results summary:**
   - The final comparison table (baseline vs. enhanced vs. names-hidden vs. QQQ/^NDX).
   - The growth-of-$1 chart.
   - Two or three sentences on what the results do and do not show.
4. **Quick start:**
   - Prerequisites.
   - Accounts and API keys needed, and where each goes (`.env`).
   - Install steps and how to obtain or rebuild the data snapshot.
   - How to run:
     - the tests;
     - the 5-stock pilot;
     - a full backtest;
     - the evaluation report.
   - Exact commands, tested on Windows.
5. **Repository map:** each folder and key file with a one-line purpose.
6. **Configuration:** the important config fields and what changing each one does.
7. **Data:**
   - Sources, the date range, and where the snapshot lives.
   - How to refresh it.
   - Known gaps (e.g., delisted tickers, non-US filers).
8. **Costs:**
   - Actual API spend per run and in total, from the cost ledger.
   - The cost to rerun from scratch, and with the response cache.
9. **Limitations and honest caveats:**
   - LLM training-data contamination.
   - Backtest-only status.
   - Data gaps.
   - Assumptions that a finance expert might challenge.
10. **Known issues and technical debt:** what is fragile, hacky or untested.
11. **Decisions log:**
    - Key decisions, who made them, and why: the finance review answers, the thinking on/off pilot result, the success criterion.
    - Every deviation from `PROJECT_BRIEF.md`.
12. **Next steps:** a prioritized list of sensible extensions, e.g.:
    - The stretch items.
    - Weekly rebalancing.
    - Repeat seeds.
    - The risk veto.
    - A post-cutoff out-of-sample test.
13. **Contacts and links:** the repository, the poster file, and the brief.

**`handoff.docx`:** generate it from the same content, with proper headings, tables and embedded charts (e.g., python-docx, or pandoc from the markdown). Check that it opens cleanly in Word and that the tables and images render.

---

## 2. `docs/design.md`

The technical explanation: how the system works and why. Target length: as long as needed, organized for skimming.

1. **Goals and non-goals.**
2. **Architecture overview:**
   - A diagram (Mermaid) of the data layer, the point-in-time gateway, the outer backtest loop, the inner LangGraph pipeline, the optimizer and the evaluator.
   - One paragraph per component.
3. **Data layer:**
   - Sources and schemas: the DuckDB tables and key columns.
   - The ETL flow.
   - How availability timestamps are defined for prices, news and filings.
4. **Point-in-time gateway:**
   - The API.
   - How leaks are prevented.
   - What the leak tests cover.
5. **Agent pipeline:**
   - Each node: inputs, outputs (with pydantic schemas), model, and prompt file location.
   - The state that flows through the graph.
   - How up to 20 stocks are selected.
   - A sequence diagram of one rebalance.
6. **Baseline vs. enhancement:**
   - Exactly what differs.
   - The Black-Litterman maths in plain words plus formulas: prior, P, Q, Ω via Idzorek, δ, τ, covariance with shrinkage.
   - The rating-to-return table.
   - The constraints: 0×–2× index weight, sector bands, long-only.
7. **Backtest engine:**
   - The calendar.
   - Execution at the next open.
   - Costs.
   - Daily mark-to-market.
   - Delisting handling.
   - Checkpoints and resume.
8. **LLM layer:**
   - The client wrapper.
   - Model tiers.
   - Thinking and effort settings, and why.
   - Structured outputs.
   - Prompt caching.
   - The response cache key.
   - The cost ledger.
   - Retries and refusals.
9. **Contamination controls:**
   - How the names-hidden mode works.
   - What it does not fix.
10. **Evaluation:**
    - Each metric's definition.
    - The factor regression setup.
    - The red-flag checks.
    - How report figures are generated.
11. **Key design decisions and trade-offs:**
    - A table: decision, alternatives considered, why chosen.
    - Include: the stateless graph, Python-only maths, monthly with 3-month views, index-relative weights, Haiku/Sonnet split, no `temperature`, and the response cache.
12. **Extension points:**
    - Where to add a new agent, a new data source, a new view type or a new metric.
    - Which files to touch.

---

## 3. `docs/mentoring.md`

A teaching guide for the mentor. Assume the student is a capable beginner: knows Python basics but not LangGraph, LLM APIs, backtesting or portfolio theory.

1. **Learning outcomes:** what the student should understand and be able to do by the end.
2. **Prerequisites:**
   - The concepts to learn first, each with a short explanation or a suggested reading topic.
   - Cover: returns and risk, Sharpe and drawdown, look-ahead and survivorship bias, an index-relative portfolio, the Black-Litterman intuition, LLM APIs and structured outputs, and LangGraph basics.
3. **Session plan:** 6–10 sessions of about 60–90 minutes each. Each session has:
   - Its objective.
   - What the mentor explains, with pointers to `design.md` sections and code files.
   - A hands-on exercise with the exact commands.
   - The expected outcome, and how the mentor checks it.
   - Common mistakes and misconceptions to watch for.

   Suggested arc:
   1. Running the pilot.
   2. The data layer and the leak tests.
   3. The backtest engine.
   4. The agent graph.
   5. The LLM layer and costs.
   6. Portfolio construction and Black-Litterman.
   7. Evaluation and reading a tearsheet.
   8. Making a small extension.
   9. Presenting the results honestly.
4. **Exercises bank:** graded from easy to hard, each with a goal, hints and an acceptance check. For example:
   - Change the cost assumption and explain the impact.
   - Add an indicator.
   - Break a leak test on purpose and see it fail.
   - Add a metric.
   - Add a new agent persona.
   - Implement the bull/bear debate stretch item.
5. **Discussion questions:** questions that test understanding, e.g.:
   - Why can't the LLM compute weights?
   - What would happen if news timestamps were in the wrong time zone?
   - Why might a backtest Sharpe of 3 be a bad sign?
6. **Assessment checklist:** observable signs that the student understands each part.
7. **Cost guardrails for students:**
   - How to use the `dev` tier and the response cache.
   - How to avoid accidental spend.
   - The budget to give a student.
8. **Troubleshooting:** the common setup and runtime errors, and how to fix them.
9. **Further reading:** topics and the related projects referenced in the brief (QuantAgents paper, TradingAgents).

---

## Quality bar (check before declaring the phase complete)

- [ ] A person who has never seen the project can follow `handoff.md` from a fresh clone to running the pilot and the evaluation report, using only the commands written there. Verify this by running them yourself in a clean environment.
- [ ] Every number in `handoff.md` matches the final run outputs.
- [ ] `handoff.docx` opens in Word, and its headings, tables and charts render correctly.
- [ ] `design.md` diagrams render (Mermaid), and every component in the code is covered.
- [ ] `mentoring.md` exercises reference real files and commands that exist.
- [ ] Limitations, known issues and deviations from the brief are stated plainly.
- [ ] No secrets, API keys or personal data appear in any document.

When this phase is done, give the user the manual checks: open each document, follow the quick start, and confirm that the docx renders.
