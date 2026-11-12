"""Which companies a run uses (config ``universe``; D39, D45).

Every rule reads data only through the point-in-time gateway, so a universe chosen at a date
uses only what was known at that date's close.

    top_n_by_cap(gateway, as_of, n)     the n largest index members (with prices) by derived cap weight
    fixed_universe(company_ids)          a fixed list
    resolve_universe(cfg, gateway)       the rule from config -> ResolvedUniverse
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from quantagents.config import Config
from quantagents.data import calendar as cal
from quantagents.data.gateway import Gateway, LookAheadError


def as_of_close(day) -> pd.Timestamp:
    """The close of ``day``, or of the next trading day if ``day`` is not one."""
    d = pd.Timestamp(day)
    return cal.as_of_for(d if cal.is_trading_day(d) else cal.next_trading_day(d))


def top_n_by_cap(gateway: Gateway, as_of, n: int) -> pd.DataFrame:
    """The ``n`` largest companies by derived index weight at ``as_of``, among index members
    that have prices. Ties are broken by company_id. Columns: rank, company_id, name, sector,
    weight (in the full index), mcap."""
    u = gateway.get_universe(as_of)
    w = gateway.get_index_weights(as_of)
    m = u[u["has_prices"].fillna(False).astype(bool)].merge(w[["company_id", "weight", "mcap"]], on="company_id")
    m = m.dropna(subset=["weight"]).sort_values(["weight", "company_id"], ascending=[False, True])
    if len(m) < n:
        raise ValueError(f"only {len(m)} members with prices and a weight at {as_of}; cannot choose {n}")
    top = m.head(n).reset_index(drop=True)
    top.insert(0, "rank", range(1, n + 1))
    return top[["rank", "company_id", "name", "sector", "weight", "mcap"]]


def fixed_universe(company_ids) -> list[str]:
    ids = [str(c).strip().upper() for c in company_ids]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate company ids in the universe: {ids}")
    return ids


@dataclass
class ResolvedUniverse:
    """The run's universe. ``fixed`` is the company list when it does not change over the run;
    ``table`` describes how it was chosen (written to runs/<run_id>/universe.csv)."""
    mode: str
    fixed: list[str] | None
    table: pd.DataFrame
    chosen_at: pd.Timestamp | None = None
    top_n: int | None = None

    def at(self, gateway: Gateway, as_of) -> list[str]:
        """Companies for a decision at ``as_of`` (index members with prices, for dynamic modes)."""
        t = cal.require_utc(as_of)
        if self.chosen_at is not None and self.chosen_at > t:
            raise LookAheadError(f"the universe was chosen at {self.chosen_at}, after the decision time {t}")
        if self.fixed is not None:
            return list(self.fixed)
        if self.mode == "top_n_by_cap":
            return list(top_n_by_cap(gateway, t, self.top_n)["company_id"])
        u = gateway.get_universe(t)
        return sorted(u.loc[u["has_prices"].fillna(False).astype(bool), "company_id"])

    def write(self, run_dir: Path) -> Path:
        run_dir.mkdir(parents=True, exist_ok=True)
        f = run_dir / "universe.csv"
        self.table.to_csv(f, index=False)
        return f


def removed_member(gateway: Gateway, start, exclude=(), last_check: str = "2023-12-01") -> str | None:
    """Pilot only (config ``add_removed_member``): the first company, alphabetically, that was an
    index member with prices at ``start`` and is no longer a member on ``last_check``. It looks
    at a later date on purpose - the pilot must contain a stock that leaves - so it is never used
    inside a decision."""
    t0, t1 = as_of_close(start), as_of_close(last_check)
    u0 = gateway.get_universe(t0)
    later = set(gateway.get_universe(t1)["company_id"])
    cands = sorted(c for c in u0.loc[u0["has_prices"].fillna(False).astype(bool), "company_id"]
                   if c not in later and c not in set(exclude))
    return cands[0] if cands else None


def resolve_universe(cfg: Config, gateway: Gateway, run_dir: Path | None = None) -> ResolvedUniverse:
    """Apply the config's universe rule. With ``run_dir``, also write universe.csv there."""
    u = cfg.universe
    if u.mode == "tickers":
        ids = fixed_universe(u.tickers)
        notes = ["configured"] * len(ids)
        if u.add_removed_member:
            extra = removed_member(gateway, cfg.dates.start, exclude=ids)
            if extra:
                ids, notes = ids + [extra], notes + ["member at the start that left the index later (pilot)"]
        res = ResolvedUniverse("tickers", ids, pd.DataFrame({"company_id": ids, "why": notes}))
    elif u.mode == "top_n_by_cap":
        t = as_of_close(u.chosen_at)
        table = top_n_by_cap(gateway, t, u.top_n)
        table.insert(1, "chosen_at", str(pd.Timestamp(u.chosen_at).date()))
        fixed = list(table["company_id"]) if u.keep_fixed else None
        res = ResolvedUniverse("top_n_by_cap", fixed, table, chosen_at=t if u.keep_fixed else None, top_n=u.top_n)
    else:
        res = ResolvedUniverse("index_members", None, pd.DataFrame({"rule": ["index members with prices on each date"]}))
    if run_dir is not None:
        res.write(run_dir)
    return res
