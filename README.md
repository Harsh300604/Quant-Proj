# QuantAgents

An LLM multi-agent system that manages a **simulated** NASDAQ-100 portfolio. It replays 2015–2023 month by month, using only information available at each date, and compares the baseline (QuantAgents paper) and the enhanced version (Black-Litterman) against QQQ and ^NDX. It is a research backtest only: no real money, no live trading.

- Specification: [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md)
- Build plan and progress: [`implementation_plan.md`](implementation_plan.md)
- Current state: [`memory.md`](memory.md)
- Decisions: [`decisions.md`](decisions.md)
- Continuing in a new dev chat: [`handoff.md`](handoff.md)

## Quick start (Windows, everything on D:)

1. Install **Python 3.12.10** (the last 3.12 release with a Windows installer: https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe) to `D:\Python312`. Use the installer, choose "Customize installation", and set the install location. Skip this if Python 3.12 or newer is already installed.
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

## Key swap checklist

**Status (12 Nov 2026, D46):** the student's key is in use, with a $200 Console limit. The configs are already set to `key_label: student` and `stage: proto20` (MVP budget $40, automatic stop at $32). The personal key is no longer used.

To move to another stage later (for example `stage2` for the full run):
1. Only once you've approved that stage's funds (see "Funding stages" in `implementation_plan.md` and D46): in the Anthropic Console, check that the key's spend limit covers it.
2. If the key changes: open `D:\CreatED-Quant\quantagents\.env` in Notepad and replace the value after `ANTHROPIC_API_KEY=`. Save.
3. In the config you run, set `budget.key_label` and `budget.stage` to the approved values.
4. Run `python scripts\check_env.py`. It shows the key label, the stage budget and the automatic stop.
5. Rerun a pilot that already ran. It should cost **$0.0000**, because the response cache doesn't depend on the key.

Do not paste keys into chat, email or code. Never commit `.env`.
