You are the lead developer for QuantAgents. The complete project specification is in `PROJECT_BRIEF.md` in this folder. It is the single source of truth. `HANDOFF_REQUIREMENTS.md` defines the final documentation phase: the handoff, design and mentoring documents for a mentor and student.

**Step 1: Understand the project.**
- Read `PROJECT_BRIEF.md` and `HANDOFF_REQUIREMENTS.md` in full before doing anything else.
- Then reply with:
  - A short summary (10 bullets at most) of what you will build, to confirm you understood it.
  - The open decisions from section 5 that block the early phases, especially the data source for historical NASDAQ-100 membership and delisted-stock prices. Ask me about these.
  - Any genuine ambiguity you found.
- Do not write code yet.

**Step 2: Write `implementation_plan.md`.** Break the project into phases that follow the 8-week schedule in section 13. Use small, testable phases, typically 6–9 of them. For each phase, list:
- The goal and the files or modules it creates.
- Tasks as a checklist.
- Automated tests it adds.
- **Manual checks I can run myself.** Give the exact commands, what I should see, and what counts as pass or fail. Write these for someone who is not an expert.
- Expected API spend, if any.
- Dependencies on earlier phases.

Mark the MVP boundary (end of week 5) and the stretch items clearly. Make the handoff documentation from `HANDOFF_REQUIREMENTS.md` the final phase. Throughout the build, keep notes on decisions, deviations and known issues so those documents can be written accurately. Show me the plan and wait for my approval before building.

**Step 3: Build one phase at a time.**
- Implement only the current phase. Write its automated tests and run them.
- When the phase is done, stop and give me:
  - What was built.
  - The test results.
  - The manual checks to run, as copy-paste commands with expected output.
  - Anything I need to provide, such as API keys or data files.
- Do not start the next phase until I confirm the manual checks passed.
- Tick off completed tasks in `implementation_plan.md` as you go, and note any deviation from the brief and why.

**Rules throughout:**
- Follow the decisions in section 4 of the brief exactly. Do not re-open them. If something is ambiguous or missing, ask me rather than guess.
- Point-in-time correctness comes first. All pipeline data access goes through the gateway, and the leak tests must pass before any backtest.
- LLMs never do maths. Validate every LLM output against a schema.
- **API calls:**
  - Use the exact model IDs from the brief and the official `anthropic` Python SDK.
  - Never send `temperature`, `top_p` or `top_k`.
  - Never use forced `tool_choice`.
  - Use structured outputs, prompt caching, the SQLite response cache and the cost ledger from the start.
  - If a Claude API skill or documentation is available, consult it before writing API code. Do not guess SDK signatures.
- **Spending money:** before any step that calls the Anthropic API beyond a few test calls (pilots and full runs), tell me the estimated cost and wait for my go-ahead. Never exceed the run budget in config or the $150 project cap.
- Develop and debug on the 5-stock, 3-month pilot. Run the full 2015–2023 backtest only when I approve.
- **Temporary API key with a ₹300 hard limit.** The student has not yet provided the project's Anthropic API key. Until they do, I am building with my **personal key**, and the most I can spend on it is **₹300 (about $3.40; treat the usable budget as $3.00** to allow for exchange rate and taxes). The project's $150 budget applies only after the key is swapped. With the personal key:
  - **Set the ledger budget for this key to $3.00.** Stop all API calls automatically at 80% ($2.40) and tell me. Track spend per key label (e.g., `personal`, `student`), never the key itself. Show the cost in both USD and INR, using a configurable exchange rate.
  - **Use the `dev` tier (Haiku 5.5) for all building and debugging.** Use structured outputs, low effort, tight `max_tokens`, and the response cache, so repeated test runs cost nothing.
  - **Sonnet 5.5 only for a tiny measurement pilot,** e.g., 2–3 rebalances on 5 stocks, to measure real token counts and test thinking on vs. off. Ask me first and give the cost estimate.
  - **No full or long backtests on this key.** A full 108-month run does not fit in ₹300, even on Haiku. Prove the whole pipeline end to end on small slices (5–20 stocks, 3–12 months). Then extrapolate the full-run cost from the measured numbers so we know exactly what the student's key must cover.
  - **Make the key swap trivial:** the key is read only from `.env` (`ANTHROPIC_API_KEY`), plus a `key_label` in config. Nothing else changes. The response cache must not depend on the key, so cached responses carry over after the swap. Never print, log or commit the key.
  - Give me a short "key swap checklist" in the README for when the student's key arrives.
- Keep secrets in `.env` and never commit them. The code must run on Windows.
- **Use only the D: drive for storage.** The C: drive is nearly full. Everything you install, download or write goes on D:, never C:. This includes:
  - **Project and environment:** the repo and the Python virtual environment (e.g., `D:\CreatED-Quant\quantagents\.venv`).
  - **Caches:** pip/uv caches (set `PIP_CACHE_DIR` / `UV_CACHE_DIR` to a folder on D:), and any npm cache.
  - **Data:** downloaded data, the DuckDB file, the SQLite caches, run outputs and logs.
  - **Temporary files:** set `TMP` / `TEMP` to a D: folder for the session or the project's scripts.
  - **Any new tool or Python install.**

  Set these per session or in project scripts or config, not as permanent system-wide changes, unless I approve. Before any large download, say where it will go. Check the C: drive isn't being used.
- Keep explanations plain. I will test each phase myself.

Start with Step 1 now.
