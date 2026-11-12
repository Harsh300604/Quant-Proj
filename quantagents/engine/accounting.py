"""Portfolio accounting, as a pure function of prices and target weights (brief section 4).

Rules:
- a decision made at the close of day t is executed at the OPEN of the next trading day;
- trading cost = cost_bps / 10,000 x turnover, where turnover = sum of |trade| / portfolio value;
  fractional shares are allowed;
- holdings are marked to market with total returns: every holding remembers the last price it
  was valued at ("mark"); each new price (an open, then a close) moves its value from there, and a
  dividend paid on a day is added at that day's open. A missing day simply waits for the next price;
- a company with no more prices (acquired / delisted) is sold at its last close and the money is
  held as cash (earning nothing) until the next rebalance;
- prices are Yahoo split-adjusted (one consistent scale per series), so a split changes nothing.

Inputs are wide tables (index = trading days, columns = companies): ``open``, ``close``,
``dividends``. Weights are fractions of the portfolio value.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Book:
    """Dollars per company, plus cash; ``marks`` = the price each holding was last valued at."""
    holdings: dict[str, float] = field(default_factory=dict)
    marks: dict[str, float] = field(default_factory=dict)
    cash: float = 1.0

    @property
    def nav(self) -> float:
        return self.cash + sum(self.holdings.values())

    def weights(self) -> dict[str, float]:
        n = self.nav
        return {c: v / n for c, v in self.holdings.items()} if n else {}

    def to_json(self) -> dict:
        return {"holdings": self.holdings, "marks": self.marks, "cash": self.cash}

    @classmethod
    def from_json(cls, d: dict) -> "Book":
        return cls({k: float(v) for k, v in d["holdings"].items()}, {k: float(v) for k, v in d["marks"].items()},
                   float(d["cash"]))


def _px(tbl: pd.DataFrame, day, company) -> float:
    if company not in tbl.columns or day not in tbl.index:
        return float("nan")
    v = tbl.at[day, company]
    return float(v) if pd.notna(v) else float("nan")


def _move(book: Book, c: str, price: float, dividend: float = 0.0) -> None:
    if np.isnan(price) or c not in book.marks or book.marks[c] <= 0:
        return
    book.holdings[c] *= (price + dividend) / book.marks[c]
    book.marks[c] = price


def rebalance(book: Book, day, target: dict[str, float], cost_bps: float,
              open_prices: dict[str, float]) -> tuple[float, float]:
    """Trade to ``target`` weights at today's open. A company with no open price today cannot be
    traded and is left as it is. Returns (turnover, cost)."""
    nav = book.nav
    tradable = {c for c, p in open_prices.items() if not np.isnan(p) and p > 0}
    fixed = {c: v for c, v in book.holdings.items() if c not in tradable}
    want = {c: w * nav for c, w in target.items() if w > 0 and c in tradable}
    names = set(want) | (set(book.holdings) - set(fixed))
    traded = sum(abs(want.get(c, 0.0) - book.holdings.get(c, 0.0)) for c in names)
    cost = cost_bps / 10_000.0 * traded
    investable = nav - cost - sum(fixed.values())
    total_want = sum(want.values())
    scale = investable / total_want if total_want > 0 else 0.0
    book.holdings = {**fixed, **{c: v * scale for c, v in want.items()}}
    book.marks = {**{c: book.marks[c] for c in fixed}, **{c: open_prices[c] for c in want}}
    book.cash = nav - cost - sum(book.holdings.values())
    if abs(book.cash) < 1e-12:
        book.cash = 0.0
    return (traded / nav if nav else 0.0), cost


def simulate(days: pd.DatetimeIndex, open_: pd.DataFrame, close: pd.DataFrame, divs: pd.DataFrame,
             targets: dict[pd.Timestamp, dict[str, float]], cost_bps: float,
             book: Book | None = None) -> tuple[pd.Series, Book, list[dict]]:
    """Run the book through ``days``. ``targets`` maps an EXECUTION day to target weights.
    Returns (portfolio value at each close, final book, log of rebalances and delisting sales)."""
    book = book or Book()
    last_bar = {c: close[c].last_valid_index() for c in close.columns}
    navs, log = [], []
    for d in days:
        sold = [c for c in list(book.holdings) if last_bar.get(c) is None or last_bar[c] < d]
        for c in sold:                                       # no prices any more: sold at the last close
            book.cash += book.holdings.pop(c)
            book.marks.pop(c, None)
        if sold:
            log.append({"date": d, "event": "sold (no more prices)", "companies": ",".join(sorted(sold))})
        for c in list(book.holdings):                        # overnight: last mark -> open (+ dividend)
            div = _px(divs, d, c)
            _move(book, c, _px(open_, d, c), 0.0 if np.isnan(div) else div)
        if d in targets:
            opens = {c: _px(open_, d, c) for c in set(targets[d]) | set(book.holdings)}
            turnover, cost = rebalance(book, d, targets[d], cost_bps, opens)
            log.append({"date": d, "event": "rebalance", "turnover": turnover, "cost": cost, "nav": book.nav})
        for c in list(book.holdings):                        # intraday: open -> close
            _move(book, c, _px(close, d, c))
        navs.append(book.nav)
    return pd.Series(navs, index=days, name="nav"), book, log
