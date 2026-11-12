"""Strategies: what the engine asks for at each rebalance (brief section 6: the AI is a pure
function; the engine is a loop around it). The agent graph (P4) will use the same signature.

    decide(ctx) -> Decision(weights, report)

``ctx.gateway`` is frozen at ``ctx.as_of``: a strategy cannot read anything later.
These two need no AI and cost $0:
- hold_benchmark: every multiplier 1, i.e. the benchmark weights;
- random: deterministic random multipliers in [0, 2] (seed + date), projected onto the constraints.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quantagents.portfolio.baseline_opt import weights_from_multipliers
from quantagents.portfolio.constraints import ConstraintSet


@dataclass
class Context:
    as_of: pd.Timestamp
    rebalance_day: pd.Timestamp
    gateway: object
    cfg: object
    companies: list[str]
    bench: pd.Series                     # benchmark weights at as_of (sum 1)
    sectors: pd.Series
    constraints: ConstraintSet
    holdings: dict[str, float]           # current weights (before trading)
    prior_report: dict | None = None


@dataclass
class Decision:
    weights: pd.Series
    report: dict = field(default_factory=dict)


class HoldBenchmark:
    name = "hold_benchmark"

    def decide(self, ctx: Context) -> Decision:
        return Decision(weights_from_multipliers(ctx.constraints), {"multipliers": "all 1.0"})


class RandomTilts:
    name = "random"

    def __init__(self, seed: int = 0):
        self.seed = seed

    def decide(self, ctx: Context) -> Decision:
        rng = np.random.default_rng([self.seed, ctx.rebalance_day.toordinal()])
        m = pd.Series(rng.uniform(0.0, 2.0, len(ctx.companies)), index=list(ctx.constraints.companies))
        return Decision(weights_from_multipliers(ctx.constraints, m), {"multipliers": m.round(4).to_dict()})


STRATEGIES = {"hold_benchmark": HoldBenchmark, "index": HoldBenchmark, "random": RandomTilts}


def make_strategy(name: str, seed: int = 0):
    if name not in STRATEGIES:
        raise ValueError(f"unknown strategy {name!r}; choose from {sorted(STRATEGIES)}")
    return STRATEGIES[name](seed) if name == "random" else STRATEGIES[name]()
