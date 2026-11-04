"""Check that this machine is set up correctly for QuantAgents.

    python scripts\\check_env.py [--config configs\\base.yaml]

Prints one line per check (OK / WARN / MISSING / FAIL). Never prints secret values.
Also records C: free space each run and shows the change since the previous run, so you can
see that nothing is being written to C:.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from quantagents.config import load_config, load_key_budgets  # noqa: E402
from quantagents.env_secrets import load_secrets  # noqa: E402
from quantagents.paths import Paths, drive_of  # noqa: E402

GB = 1024 ** 3


def line(status: str, what: str, detail: str = "") -> bool:
    print(f"[{status:<7}] {what}{(': ' + detail) if detail else ''}")
    return status in ("OK", "WARN", "INFO")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(REPO / "configs" / "base.yaml"))
    args = ap.parse_args(argv)
    ok = True
    windows = sys.platform == "win32"

    v = sys.version_info
    ok &= line("OK" if v >= (3, 12) else "FAIL", "Python version",
               f"{platform.python_version()} (need 3.12 or newer)")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    ok &= line("OK" if in_venv else "FAIL", "Virtual environment active", sys.prefix)

    try:
        cfg = load_config(args.config)
        line("OK", "Config loads", Path(args.config).name)
    except Exception as exc:
        line("FAIL", "Config loads", str(exc))
        return 1
    try:
        paths = Paths.from_config(cfg)
        line("OK", "Storage root (not on C:)", str(paths.root))
    except Exception as exc:
        line("FAIL", "Storage root", str(exc))
        return 1

    if windows:
        for what, p in [("Repo folder", REPO), ("Virtual environment", Path(sys.prefix)),
                        ("Storage root", paths.root)]:
            ok &= line("OK" if drive_of(p) == "D:" else "FAIL", f"{what} on D:", str(p))
        for var in ("PIP_CACHE_DIR", "UV_CACHE_DIR", "TMP", "TEMP"):
            val = os.environ.get(var, "")
            good = bool(val) and drive_of(val) == "D:"
            ok &= line("OK" if good else "FAIL", f"{var} on D:",
                       val or "not set - run  . .\\scripts\\env.ps1  first")
    else:
        line("INFO", "Drive checks", "skipped (not Windows)")

    budgets = load_key_budgets()
    kb = budgets[cfg.budget.key_label]
    line("OK", "API key label", f"{cfg.budget.key_label}, budget ${kb.budget_usd:.2f}, "
         f"automatic stop at ${kb.stop_at_usd:.2f} "
         f"(Rs {kb.stop_at_usd * cfg.budget.inr_per_usd:,.0f} at Rs {cfg.budget.inr_per_usd:g}/$)")
    line("OK", "Model tier", f"{cfg.models.tier} (memo {cfg.models.active.memo}, "
         f"committee {cfg.models.active.committee})")

    secrets = load_secrets()
    env_file = REPO / ".env"
    line("OK" if env_file.exists() else "MISSING", ".env file", str(env_file))
    for name, st in secrets.status().items():
        line("OK" if st == "present" else "MISSING", name, st)
        ok &= st == "present"
    ua = secrets.get("SEC_USER_AGENT") if secrets.has("SEC_USER_AGENT") else ""
    if ua and "@" not in ua:
        ok &= line("FAIL", "SEC_USER_AGENT format", "must contain a contact email")

    try:
        import pandas_ta  # noqa: F401
        import yfinance  # noqa: F401
        line("OK", "Key packages import", "pandas, yfinance, pandas-ta")
    except Exception as exc:
        ok &= line("FAIL", "Key packages import", str(exc))

    if windows and Path("C:\\").exists():
        free_c = shutil.disk_usage("C:\\").free / GB
        rec = paths.root / "logs" / "c_drive_free.json"
        prev = json.loads(rec.read_text()) if rec.exists() else None
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text(json.dumps({"free_gb": free_c, "time": datetime.now().isoformat()}))
        if prev:
            change = free_c - prev["free_gb"]
            line("OK" if change > -0.1 else "WARN", "C: free space",
                 f"{free_c:.1f} GB; C: free space change since last check: {change:+.1f} GB "
                 f"(last check {prev['time'][:16]})")
        else:
            line("INFO", "C: free space", f"{free_c:.1f} GB (first reading; run again later to see the change)")
        if Path("D:\\").exists():
            free_d = shutil.disk_usage("D:\\").free / GB
            line("INFO", "D: free space", f"{free_d:.1f} GB")

    print("\nAll checks passed." if ok else "\nSome checks failed - see the lines marked FAIL or MISSING.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
