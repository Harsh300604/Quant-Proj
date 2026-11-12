"""Hand-computed 3-stock example for the accounting rules (brief section 4)."""
import pandas as pd
import pytest

from quantagents.engine.accounting import Book, simulate

D = pd.DatetimeIndex(["2021-01-04", "2021-01-05", "2021-01-06", "2021-01-07", "2021-01-08"])


def tables():
    open_ = pd.DataFrame({"A": [10.0, 10.0, 11.0, 12.0, 12.0], "B": [20.0, 20.0, 19.0, 19.0, 18.0],
                          "C": [5.0, 5.0, 5.0, float("nan"), float("nan")]}, index=D)
    close = pd.DataFrame({"A": [10.0, 10.5, 11.5, 12.0, 12.6], "B": [20.0, 19.0, 19.0, 18.5, 18.0],
                          "C": [5.0, 5.5, 6.0, float("nan"), float("nan")]}, index=D)
    divs = pd.DataFrame(0.0, index=D, columns=list("ABC"))
    return open_, close, divs


def test_next_open_fill_cost_and_nav_to_the_cent():
    """Decision at the close of 4 Jan -> trade at the open of 5 Jan: 50% A, 50% B, 10 bps cost."""
    o, c, d = tables()
    nav, book, log = simulate(D[1:], o, c, d, {D[1]: {"A": 0.5, "B": 0.5}}, cost_bps=10.0, book=Book(cash=10_000.0))
    # 5 Jan open: buy $10,000 of stock -> cost $10.00; $4,995 in each
    assert log[0]["cost"] == pytest.approx(10.0) and log[0]["turnover"] == pytest.approx(1.0)
    # 5 Jan close: A 10 -> 10.5 (+5%), B 20 -> 19 (-5%): 4995 x 1.05 + 4995 x 0.95 = 9990
    assert nav[D[1]] == pytest.approx(9990.00, abs=0.005)
    # 6 Jan: A 10.5 -> 11.5, B 19 -> 19
    a6, b6 = 4995 * 11.5 / 10, 4995 * 19 / 20
    assert nav[D[2]] == pytest.approx(a6 + b6, abs=0.005)
    assert nav[D[4]] == pytest.approx(4995 * 12.6 / 10 + 4995 * 18 / 20, abs=0.005)


def test_dividend_is_added_at_the_open():
    o, c, d = tables()
    d.loc[D[2], "B"] = 1.0                      # $1 dividend, ex-date 6 Jan (open already lower)
    nav, _, _ = simulate(D[1:], o, c, d, {D[1]: {"B": 1.0}}, cost_bps=0.0, book=Book(cash=1000.0))
    # 5 Jan: 1000 x 19/20 = 950; 6 Jan open: 950 x (19 + 1)/19 = 1000; close 19 -> 19: 1000
    assert nav[D[1]] == pytest.approx(950.0) and nav[D[2]] == pytest.approx(1000.0)


def test_split_changes_nothing():
    """Yahoo prices are split-adjusted: one consistent scale, so a 2-for-1 split is not a move."""
    o, c, d = tables()
    o2, c2 = o.copy(), c.copy()
    o2["A"] /= 2
    c2["A"] /= 2                                 # the whole series rescaled, as after a later split
    n1, _, _ = simulate(D[1:], o, c, d, {D[1]: {"A": 1.0}}, 0.0, Book(cash=100.0))
    n2, _, _ = simulate(D[1:], o2, c2, d, {D[1]: {"A": 1.0}}, 0.0, Book(cash=100.0))
    pd.testing.assert_series_equal(n1, n2)


def test_delisting_mid_month_is_sold_at_last_close_and_held_as_cash():
    o, c, d = tables()
    nav, book, log = simulate(D[1:], o, c, d, {D[1]: {"A": 0.5, "C": 0.5}}, cost_bps=0.0, book=Book(cash=1000.0))
    # C: 500 at 5.0 -> 5.5 -> 6.0 (last close 6 Jan) = 600; sold on 7 Jan, then cash
    assert book.cash == pytest.approx(600.0) and "C" not in book.holdings
    assert any(e.get("event") == "sold (no more prices)" for e in log)
    assert nav[D[4]] == pytest.approx(500 * 12.6 / 10 + 600.0)


def test_missing_day_waits_for_the_next_price():
    o, c, d = tables()
    o.loc[D[2], "A"], c.loc[D[2], "A"] = float("nan"), float("nan")   # A not traded on 6 Jan
    nav, _, _ = simulate(D[1:], o, c, d, {D[1]: {"A": 1.0}}, 0.0, Book(cash=100.0))
    assert nav[D[2]] == pytest.approx(105.0)                          # unchanged from 5 Jan close
    assert nav[D[3]] == pytest.approx(100 * 12.0 / 10)                # catches up on 7 Jan


def test_rebalance_with_existing_holdings_charges_only_the_trades():
    o, c, d = tables()
    nav, book, log = simulate(D[1:], o, c, d, {D[1]: {"A": 1.0}, D[3]: {"A": 0.5, "B": 0.5}}, 10.0,
                              Book(cash=1000.0))
    second = [e for e in log if e.get("event") == "rebalance"][1]
    assert second["turnover"] == pytest.approx(1.0, rel=1e-9)        # sell half of A, buy B: 2 x 0.5
    assert book.nav == pytest.approx(nav.iloc[-1])
