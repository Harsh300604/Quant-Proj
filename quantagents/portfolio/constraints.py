"""Portfolio constraints (brief section 4, D5, D41).

Measured against a BENCHMARK weight vector b (the derived NASDAQ-100 weights in the full run,
the same-20 index in proto20):
- each company: min_multiple x b_i <= w_i <= max_multiple x b_i (0x-2x; long-only);
- each sector: |sum of w in the sector - sum of b in the sector| <= sector_band_pp / 100;
- weights sum to 1 (no leverage, no cash target).

The benchmark itself always satisfies every constraint when the multiple range includes 1, so
a correctly built constraint set is never empty. If it ever is, ``InfeasibleError`` stops the
run with a clear message: constraints are never loosened automatically (D41).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TOL = 1e-9


class InfeasibleError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConstraintSet:
    companies: tuple[str, ...]
    bench: np.ndarray                 # benchmark weights, sum 1
    sectors: tuple[str, ...]
    lower: np.ndarray                 # per-company bounds
    upper: np.ndarray
    sector_names: tuple[str, ...]
    sector_bench: np.ndarray
    sector_lower: np.ndarray
    sector_upper: np.ndarray

    @classmethod
    def build(cls, bench: pd.Series, sectors: pd.Series, min_multiple: float, max_multiple: float,
              sector_band_pp: float) -> "ConstraintSet":
        b = bench.astype(float)
        if (b < 0).any() or abs(b.sum() - 1) > 1e-6:
            raise ValueError("benchmark weights must be >= 0 and sum to 1")
        b = b / b.sum()
        sec = sectors.reindex(b.index).fillna("Unknown").astype(str)
        names = tuple(sorted(sec.unique()))
        sb = np.array([b[sec == s].sum() for s in names])
        band = sector_band_pp / 100.0
        cs = cls(tuple(b.index), b.to_numpy(), tuple(sec), min_multiple * b.to_numpy(), max_multiple * b.to_numpy(),
                 names, sb, np.maximum(sb - band, 0.0), np.minimum(sb + band, 1.0))
        cs.assert_feasible()
        return cs

    @classmethod
    def from_config(cls, cfg, bench: pd.Series, sectors: pd.Series) -> "ConstraintSet":
        c = cfg.constraints
        return cls.build(bench, sectors, c.min_multiple_of_index, c.max_multiple_of_index, c.sector_band_pp)

    def sector_index(self) -> dict[str, np.ndarray]:
        sec = np.array(self.sectors)
        return {s: np.where(sec == s)[0] for s in self.sector_names}

    def assert_feasible(self) -> None:
        """Clear message if no portfolio can satisfy all constraints at once."""
        problems = []
        lo_tot, hi_tot = 0.0, 0.0
        for k, (s, idx) in enumerate(self.sector_index().items()):
            box_lo, box_hi = self.lower[idx].sum(), self.upper[idx].sum()
            lo, hi = max(self.sector_lower[k], box_lo), min(self.sector_upper[k], box_hi)
            if lo > hi + TOL:
                problems.append(f"sector {s}: band [{self.sector_lower[k]:.4f}, {self.sector_upper[k]:.4f}] does not "
                                f"meet the per-company limits [{box_lo:.4f}, {box_hi:.4f}]")
            lo_tot += lo
            hi_tot += hi
        if not (lo_tot - TOL <= 1.0 <= hi_tot + TOL):
            problems.append(f"weights cannot sum to 1: possible total between {lo_tot:.4f} and {hi_tot:.4f}")
        if problems:
            raise InfeasibleError("No portfolio satisfies the constraints (they are NOT loosened automatically; "
                                  "ask the user, D41): " + "; ".join(problems))

    def violations(self, w: np.ndarray, tol: float = 1e-8) -> list[str]:
        out = []
        if abs(w.sum() - 1) > tol:
            out.append(f"weights sum to {w.sum():.10f}")
        bad = np.where((w < self.lower - tol) | (w > self.upper + tol))[0]
        out += [f"{self.companies[i]}: weight {w[i]:.6f} outside [{self.lower[i]:.6f}, {self.upper[i]:.6f}]" for i in bad]
        for k, (s, idx) in enumerate(self.sector_index().items()):
            t = w[idx].sum()
            if t < self.sector_lower[k] - tol or t > self.sector_upper[k] + tol:
                out.append(f"sector {s}: weight {t:.6f} outside [{self.sector_lower[k]:.6f}, {self.sector_upper[k]:.6f}]")
        return out
