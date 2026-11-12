"""SQLite cost ledger with three budgets (brief section 8, D22, D46).

Every call is recorded: time, run, node, model, key label, funding stage, variant, all four
token counts, cache hit or miss, USD and INR. Before a call, ``check`` refuses it when
- the key label's spend would pass its stop (budget x stop_fraction, configs/keys.yaml),
- the funding stage's spend would pass its stop (configs/stages.yaml; proto20: $32 of $40), or
- the run's spend would pass the run budget (config budget.run_budget_usd),
counting the call's WORST-CASE cost (all max_tokens used). Cache hits cost $0.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from quantagents.config import load_key_budgets, load_stage_budgets

COLUMNS = ["time_utc", "run_id", "node", "model", "key_label", "stage", "variant", "input_tokens",
           "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens", "cache_hit",
           "usd", "inr"]


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class Limits:
    key_label: str
    key_budget: float
    key_stop: float
    key_fraction: float
    stage: str
    stage_budget: float
    stage_stop: float
    stage_fraction: float
    run_budget: float
    inr_per_usd: float

    @classmethod
    def from_config(cls, cfg) -> "Limits":
        k = load_key_budgets()[cfg.budget.key_label]
        s = load_stage_budgets()[cfg.budget.stage]
        return cls(cfg.budget.key_label, k.budget_usd, k.stop_at_usd, k.stop_fraction,
                   cfg.budget.stage, s.budget_usd, s.stop_at_usd, s.stop_fraction,
                   cfg.budget.run_budget_usd, cfg.budget.inr_per_usd)


class Ledger:
    """``path`` may be ":memory:" (tests and --simulate-spend)."""

    def __init__(self, path: Path | str):
        # an in-memory ledger may be used from the memo threads; LLMClient serialises access with a lock
        self._mem = sqlite3.connect(":memory:", check_same_thread=False) if str(path) == ":memory:" else None
        self.path = None if self._mem is not None else Path(path)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.execute(f"CREATE TABLE IF NOT EXISTS calls ({', '.join(COLUMNS)})")

    @contextmanager
    def _con(self):
        con = self._mem if self._mem is not None else sqlite3.connect(self.path)
        try:
            with con:              # commits on success
                yield con
        finally:
            if self._mem is None:
                con.close()

    def copy_to_memory(self) -> "Ledger":
        """An in-memory copy (for simulations that must not touch the real ledger)."""
        mem = Ledger(":memory:")
        rows = self.frame()
        if len(rows):
            with mem._con() as con:
                con.executemany(f"INSERT INTO calls VALUES ({', '.join('?' * len(COLUMNS))})",
                                rows[COLUMNS].itertuples(index=False, name=None))
        return mem

    def record(self, *, run_id: str, node: str, model: str, key_label: str, stage: str, variant: str,
               usage: dict, cache_hit: bool, usd: float, inr_per_usd: float) -> None:
        row = [datetime.now(timezone.utc).isoformat(timespec="seconds"), run_id, node, model, key_label, stage,
               variant, int(usage.get("input_tokens") or 0), int(usage.get("cache_creation_input_tokens") or 0),
               int(usage.get("cache_read_input_tokens") or 0), int(usage.get("output_tokens") or 0),
               int(bool(cache_hit)), float(usd), float(usd) * inr_per_usd]
        with self._con() as con:
            con.execute(f"INSERT INTO calls VALUES ({', '.join('?' * len(COLUMNS))})", row)

    def frame(self) -> pd.DataFrame:
        with self._con() as con:
            return pd.read_sql_query("SELECT * FROM calls", con)

    def spent(self, *, key_label: str | None = None, stage: str | None = None, run_id: str | None = None) -> float:
        where, params = [], []
        for col, val in (("key_label", key_label), ("stage", stage), ("run_id", run_id)):
            if val is not None:
                where.append(f"{col} = ?")
                params.append(val)
        sql = "SELECT coalesce(sum(usd), 0) FROM calls" + (" WHERE " + " AND ".join(where) if where else "")
        with self._con() as con:
            return float(con.execute(sql, params).fetchone()[0])

    def check(self, limits: Limits, run_id: str, worst_case_usd: float = 0.0) -> None:
        """Raise BudgetExceeded if this call could pass any stop. Messages are safe to print."""
        key = self.spent(key_label=limits.key_label)
        stage = self.spent(stage=limits.stage, key_label=limits.key_label)
        run = self.spent(run_id=run_id)
        if key + worst_case_usd > limits.key_stop:
            raise BudgetExceeded(
                f"BLOCKED: key '{limits.key_label}' at {limits.key_fraction:.0%} of ${limits.key_budget:.2f} budget "
                f"(spent ${key:.4f}; stop at ${limits.key_stop:.2f}; this call could cost up to ${worst_case_usd:.4f})")
        if stage + worst_case_usd > limits.stage_stop:
            raise BudgetExceeded(
                f"BLOCKED: stage '{limits.stage}' at {limits.stage_fraction:.0%} of ${limits.stage_budget:.2f} budget "
                f"(spent ${stage:.4f}; stop at ${limits.stage_stop:.2f}; this call could cost up to "
                f"${worst_case_usd:.4f}). Going further needs the user's explicit approval.")
        if run + worst_case_usd > limits.run_budget:
            raise BudgetExceeded(
                f"BLOCKED: run '{run_id}' budget ${limits.run_budget:.2f} (spent ${run:.4f}; this call could cost up "
                f"to ${worst_case_usd:.4f})")
