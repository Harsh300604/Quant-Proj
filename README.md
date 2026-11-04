# QuantAgents

An LLM multi-agent system that manages a **simulated** NASDAQ-100 portfolio. It replays 2015–2023 month by month, using only information available at each date, and compares the baseline (QuantAgents paper) and the enhanced version (Black-Litterman) against QQQ and ^NDX. It is a research backtest only: no real money, no live trading.

- Specification: [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md)
- Build plan and progress: [`implementation_plan.md`](implementation_plan.md)
- Current state: [`memory.md`](memory.md)
- Decisions: [`decisions.md`](decisions.md)
- Continuing in a new dev chat: [`handoff.md`](handoff.md)

## Quick start (Windows, everything on D:)

1. Install **Python 3.12** to `D:\Python312`. Use the python.org installer, choose "Customize installation", and set the install location. Skip this if Python 3.12 or newer is already installed.
2. In PowerShell:
   ```powershell
   cd D:\CreatED-Quant
   git clone https://github.com/Harsh300604/Quant-Proj quantagents
   cd quantagents
   git checkout claude/nifty-albattani-era22n
   Set-ExecutionPolicy -Scope Process Bypass -Force; .\scripts\setup.ps1
   ```
3. Open `.env` in Notepad and fill in the values (see `.env.example`).
4. In every new PowerShell window:
   ```powershell
   cd D:\CreatED-Quant\quantagents
   Set-ExecutionPolicy -Scope Process Bypass -Force; . .\scripts\env.ps1
   ```
   This window only: caches and temp files go to `D:\CreatED-Quant\qa_store\`, and the virtual environment is activated.
5. Check the setup and run the tests:
   ```powershell
   python scripts\check_env.py
   pytest -q
   ```

## Where things are stored

| What | Where |
|---|---|
| Code | `D:\CreatED-Quant\quantagents` (this repo) |
| Virtual environment | `D:\CreatED-Quant\quantagents\.venv` |
| Downloads, DuckDB, caches, runs, logs, temp | `D:\CreatED-Quant\qa_store\` (`storage.root` in `configs\base.yaml`) |
| Secrets | `.env` in the repo folder (never committed) |

## Key swap checklist (when the student's Anthropic key arrives)

1. In the Anthropic Console, check that the student's key has **$150 of credit** and a **$150 spend limit**.
2. Open `D:\CreatED-Quant\quantagents\.env` in Notepad and replace the value after `ANTHROPIC_API_KEY=` with the student's key. Save.
3. In `configs\base.yaml`, change `key_label: personal` to `key_label: student`. Do the same in any other config you run, e.g. `configs\pilot.yaml`.
4. Run `python scripts\check_env.py`. It should say `API key label: student, budget $150.00`.
5. Rerun a pilot that already ran on the personal key. It should cost **$0.0000**, because the response cache doesn't depend on the key.
6. Revoke the personal key in the Console if it's no longer needed.

Do not paste keys into chat, email or code. Never commit `.env`.
