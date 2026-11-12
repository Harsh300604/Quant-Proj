"""Load and validate YAML config files.

A config may start with ``extends: other.yaml``; the other file is loaded first and this
file's values are merged on top (nested dictionaries merge, everything else replaces).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "configs"

# Only these model IDs may be used (brief section 8). Older generations are not allowed.
ALLOWED_MODELS = {"claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"}
# The API rejects these since 21 Oct 2026; they must never appear in config.
FORBIDDEN_SAMPLING_KEYS = {"temperature", "top_p", "top_k"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Storage(Strict):
    root: str


class Dates(Strict):
    warmup_start: date
    start: date
    end: date

    @model_validator(mode="after")
    def _order(self) -> "Dates":
        if not (self.warmup_start <= self.start < self.end):
            raise ValueError("dates must satisfy warmup_start <= start < end")
        return self


class Universe(Strict):
    """Which companies a run uses (D45: nothing hard-coded to 20 stocks or a date).

    - index_members: the historical index members on each date (default; the full run)
    - tickers: a fixed list (the 5-stock pilot); also chosen automatically when ``tickers`` is set
    - top_n_by_cap: the ``top_n`` largest members by derived cap weight at the close of
      ``chosen_at`` (D39); held for the whole period when ``keep_fixed``, else re-ranked each rebalance
    """
    index: Literal["NDX"] = "NDX"
    mode: Literal["index_members", "tickers", "top_n_by_cap"] = "index_members"
    tickers: list[str] | None = None
    top_n: int | None = Field(default=None, ge=1)
    chosen_at: date | None = None
    keep_fixed: bool = True
    add_removed_member: bool = False

    @model_validator(mode="before")
    @classmethod
    def _default_mode(cls, data):
        if isinstance(data, dict) and not data.get("mode"):
            data = {**data, "mode": "tickers" if data.get("tickers") else "index_members"}
        return data

    @field_validator("tickers")
    @classmethod
    def _upper(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else [t.strip().upper() for t in v]

    @model_validator(mode="after")
    def _needs(self) -> "Universe":
        if self.mode == "tickers" and not self.tickers:
            raise ValueError("universe.mode 'tickers' needs universe.tickers")
        if self.mode == "top_n_by_cap" and (self.top_n is None or self.chosen_at is None):
            raise ValueError("universe.mode 'top_n_by_cap' needs universe.top_n and universe.chosen_at")
        if self.mode != "tickers" and self.tickers:
            raise ValueError(f"universe.tickers is only used with mode 'tickers' (mode is {self.mode!r})")
        return self


class Benchmark(Strict):
    """What constraints and active metrics are measured against (D41).

    - index: the derived NASDAQ-100 cap weights of the run's universe dates (full run)
    - custom_cap_index: cap weights renormalised over the run's own companies (proto20)
    QQQ and ^NDX are always shown as reference rows."""
    mode: Literal["index", "custom_cap_index"] = "index"


class Constraints(Strict):
    min_multiple_of_index: float = Field(ge=0.0)
    max_multiple_of_index: float = Field(gt=0.0)
    sector_band_pp: float = Field(gt=0.0, le=100.0)
    long_only: Literal[True] = True
    # optimizer distance (baseline_opt.project): relative = in multiplier units (D50, default);
    # absolute = D49 as built in P3 (kept for comparison)
    projection: Literal["absolute", "relative"] = "relative"

    @model_validator(mode="after")
    def _range(self) -> "Constraints":
        if self.max_multiple_of_index < self.min_multiple_of_index:
            raise ValueError("max_multiple_of_index must be >= min_multiple_of_index")
        if self.min_multiple_of_index > 1.0 or self.max_multiple_of_index < 1.0:
            raise ValueError("the range of multiples must include 1.0 (index weight)")
        return self


class Selection(Strict):
    max_views: int = Field(ge=1, le=20)
    max_per_sector: int | None = Field(default=None, ge=1)   # null = no per-sector cap (proto20, D42)


RATINGS = ("strong_sell", "sell", "hold", "buy", "strong_buy")


class Views(Strict):
    horizon_months: int = Field(ge=1)
    rating_to_excess_return: dict[str, float]

    @field_validator("rating_to_excess_return")
    @classmethod
    def _ratings(cls, v: dict[str, float]) -> dict[str, float]:
        if set(v) != set(RATINGS):
            raise ValueError(f"rating_to_excess_return must have exactly {RATINGS}")
        values = [v[r] for r in RATINGS]
        if values != sorted(values):
            raise ValueError("ratings must map to increasing returns (strong_sell lowest)")
        return v


class BlackLitterman(Strict):
    delta: float = Field(gt=0)
    tau: float = Field(gt=0)
    omega: Literal["idzorek"] = "idzorek"
    cov: Literal["ledoit_wolf_252d"] = "ledoit_wolf_252d"


class TierModels(Strict):
    memo: str
    committee: str

    @field_validator("memo", "committee")
    @classmethod
    def _allowed(cls, v: str) -> str:
        if v not in ALLOWED_MODELS:
            raise ValueError(f"model {v!r} is not allowed; use one of {sorted(ALLOWED_MODELS)}")
        return v


class MemoSettings(Strict):
    effort: Literal["low", "medium", "high"]
    max_tokens: int = Field(ge=64, le=8000)


class CommitteeSettings(Strict):
    # between_tools = thinking off (brief section 8); default = model's own default (thinking on)
    thinking: Literal["between_tools", "default"]
    effort: Literal["low", "medium", "high"]
    max_tokens: int = Field(ge=64, le=16000)


class Models(Strict):
    tier: Literal["dev", "paper", "robustness"]
    tiers: dict[str, TierModels]
    memo: MemoSettings
    committee: CommitteeSettings

    @model_validator(mode="after")
    def _tier_exists(self) -> "Models":
        if self.tier not in self.tiers:
            raise ValueError(f"tier {self.tier!r} is not defined under models.tiers")
        return self

    @property
    def active(self) -> TierModels:
        return self.tiers[self.tier]


class RiskScore(Strict):
    """Weights of the paper's risk score for Dave (D33). Each term is scaled so the benchmark
    scores 1 on beta, illiquidity and volatility and 0 on sector (so the benchmark's R = 0.75)."""
    beta: float = Field(default=0.25, ge=0)
    illiquidity: float = Field(default=0.25, ge=0)
    sector: float = Field(default=0.25, ge=0)
    volatility: float = Field(default=0.25, ge=0)


class Agents(Strict):
    """Agent-graph settings (P4)."""
    memo_concurrency: int = Field(default=4, ge=1, le=16)   # memo calls in flight at once
    sim_trading_months: int = Field(default=12, ge=3)        # Bob's look-back (D32)
    track_record_rebalances: int = Field(default=3, ge=1)    # how many past decisions the track record lists (D34)


class Budget(Strict):
    key_label: str
    stage: str = "stage0"
    run_budget_usd: float = Field(gt=0)
    inr_per_usd: float = Field(gt=0)


class Downloads(Strict):
    wikipedia_requests_per_second: float = Field(gt=0, le=5)
    sec_requests_per_second: float = Field(gt=0, le=10)
    alpaca_requests_per_minute: float = Field(gt=0, le=200)
    membership_snapshot_days: list[int] = [1, 15]


class Config(Strict):
    run_id: str
    variant: Literal["baseline", "enhanced"]
    names_hidden: bool
    replicate: int = Field(ge=0)
    storage: Storage
    dates: Dates
    universe: Universe
    benchmark: Benchmark = Benchmark()
    rebalance: Literal["monthly_first_trading_day"]
    decision_time: Literal["close"]
    execution: Literal["next_open"]
    cost_bps: float = Field(ge=0)
    constraints: Constraints
    selection: Selection
    views: Views
    black_litterman: BlackLitterman
    risk_score: RiskScore = RiskScore()
    agents: Agents = Agents()
    models: Models
    budget: Budget
    downloads: Downloads
    source_file: str | None = None


class KeyBudget(Strict):
    budget_usd: float = Field(gt=0)
    stop_fraction: float = Field(gt=0, le=1)

    @property
    def stop_at_usd(self) -> float:
        return round(self.budget_usd * self.stop_fraction, 6)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _find_forbidden(obj: Any, path: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else str(k)
            if str(k).lower() in FORBIDDEN_SAMPLING_KEYS:
                hits.append(here)
            hits.extend(_find_forbidden(v, here))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(_find_forbidden(v, f"{path}[{i}]"))
    return hits


def _read_yaml(path: Path, seen: tuple[Path, ...] = ()) -> dict[str, Any]:
    path = path.resolve()
    if path in seen:
        raise ValueError(f"circular 'extends' in {path}")
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    parent = data.pop("extends", None)
    if parent:
        base = _read_yaml(path.parent / parent, seen + (path,))
        data = _deep_merge(base, data)
    return data


def load_config(path: str | Path = CONFIG_DIR / "base.yaml") -> Config:
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        path = REPO_ROOT / path
    data = _read_yaml(path)
    bad = _find_forbidden(data)
    if bad:
        raise ValueError(f"sampling parameters are not allowed in config: {bad}")
    data["source_file"] = str(path)
    cfg = Config.model_validate(data)
    load_key_budgets()[cfg.budget.key_label]  # unknown label -> KeyError below
    stage = load_stage_budgets()[cfg.budget.stage]
    if stage.key_label != cfg.budget.key_label:
        raise ValueError(f"funding stage {cfg.budget.stage!r} is for key_label {stage.key_label!r}, "
                         f"but the config uses key_label {cfg.budget.key_label!r}")
    return cfg


class StageBudget(Strict):
    key_label: str
    budget_usd: float = Field(gt=0)
    stop_fraction: float = Field(gt=0, le=1)
    buys: str = ""

    @property
    def stop_at_usd(self) -> float:
        return round(self.budget_usd * self.stop_fraction, 6)


PROJECT_CAP_USD = 150.0


def load_stage_budgets(path: str | Path = CONFIG_DIR / "stages.yaml") -> dict[str, StageBudget]:
    """Funding stages. The student-key stages must add up to no more than the $150 cap."""
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    stages = {name: StageBudget.model_validate(v) for name, v in raw.items()}
    student_total = sum(st.budget_usd for st in stages.values() if st.key_label == "student")
    if student_total > PROJECT_CAP_USD + 1e-9:
        raise ValueError(f"student-key stages total ${student_total:.2f}, above the ${PROJECT_CAP_USD:.0f} cap")
    keys = load_key_budgets()
    for name, st in stages.items():
        keys[st.key_label]  # unknown key label -> KeyError
        if st.budget_usd > keys[st.key_label].budget_usd:
            raise ValueError(f"stage {name!r} budget exceeds the {st.key_label!r} key budget")

    class _Stages(dict):
        def __missing__(self, key: str):
            raise KeyError(f"funding stage {key!r} is not defined in configs/stages.yaml "
                           f"(known: {sorted(self)})")

    return _Stages(stages)


def load_key_budgets(path: str | Path = CONFIG_DIR / "keys.yaml") -> dict[str, KeyBudget]:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    budgets = {label: KeyBudget.model_validate(v) for label, v in raw.items()}

    class _Budgets(dict):
        def __missing__(self, key: str):
            raise KeyError(f"key_label {key!r} is not defined in configs/keys.yaml "
                           f"(known: {sorted(self)})")

    return _Budgets(budgets)
