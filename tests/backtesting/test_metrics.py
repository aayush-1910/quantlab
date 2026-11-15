"""Metric formulas checked against values worked out by hand."""

import math
from datetime import date
from decimal import Decimal

import pytest

from quantlab.backtesting.costs import ZeroCostModel
from quantlab.backtesting.engine import BacktestResult, run_backtest
from quantlab.backtesting.metrics import (
    gross_performance,
    max_drawdown,
    net_performance,
    performance,
    relative,
    session_returns,
    trading,
)
from quantlab.backtesting.strategy import BuyAndHold
from tests.backtesting.helpers import D, Scripted, bar, config, day

DATES = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
EQUITY = [D("1100"), D("990"), D("1089")]  # from 1000: +10%, -10%, +10%
ROOT_252 = math.sqrt(252)


def test_session_returns_start_from_initial_equity() -> None:
    assert session_returns(D("1000"), EQUITY) == pytest.approx([0.1, -0.1, 0.1])


def test_performance_matches_hand_calculation() -> None:
    metrics = performance(D("1000"), DATES, EQUITY)

    assert metrics.sessions == 3
    assert (metrics.start_date, metrics.end_date) == (DATES[0], DATES[2])
    assert metrics.cumulative_return == pytest.approx(0.089)
    # Two calendar days: 1.089 ** (365.25 / 2) - 1.
    assert metrics.cagr == pytest.approx(1.089 ** (365.25 / 2) - 1)
    # Mean 1/30. Deviations 1/15, -2/15, 1/15: sum of squares 6/225, sample variance 3/225.
    deviation = math.sqrt(3 / 225)
    assert metrics.annualized_volatility == pytest.approx(deviation * ROOT_252)
    assert metrics.sharpe_ratio == pytest.approx((1 / 30) / deviation * ROOT_252)
    assert metrics.sharpe_ratio == pytest.approx(4.5826, abs=1e-4)
    # Downside deviation sqrt((0 + 0.01 + 0) / 3).
    assert metrics.sortino_ratio == pytest.approx((1 / 30) / math.sqrt(0.01 / 3) * ROOT_252)
    # Peak 1100, trough 990: -10%. Sessions 2 and 3 are both below the peak.
    assert metrics.max_drawdown == pytest.approx(-0.1)
    assert metrics.max_drawdown_duration_sessions == 2
    assert metrics.calmar_ratio == pytest.approx(metrics.cagr / 0.1)  # type: ignore[operator]


def test_risk_free_rate_lowers_sharpe_by_the_per_session_rate() -> None:
    with_rate = performance(D("1000"), DATES, EQUITY, risk_free_rate=0.0504)

    deviation = math.sqrt(3 / 225)
    assert with_rate.sharpe_ratio == pytest.approx((1 / 30 - 0.0504 / 252) / deviation * ROOT_252)


def test_drawdown_counts_from_initial_equity_and_tracks_the_longest_spell() -> None:
    # Falls straight away from 1000; recovers at 1000; second, shorter drawdown after 1200.
    equities = [D("900"), D("800"), D("950"), D("1000"), D("1200"), D("1100"), D("1300")]

    worst, longest = max_drawdown(D("1000"), equities)

    assert worst == pytest.approx(-0.2)
    assert longest == 3


def test_ratios_are_none_when_they_cannot_be_computed() -> None:
    single = performance(D("1000"), DATES[:1], [D("1010")])
    flat = performance(D("1000"), DATES, [D("1000"), D("1000"), D("1000")])
    only_up = performance(D("1000"), DATES, [D("1010"), D("1030"), D("1040")])

    assert (single.cagr, single.annualized_volatility, single.sharpe_ratio) == (None, None, None)
    assert single.cumulative_return == pytest.approx(0.01)
    assert flat.annualized_volatility == 0
    assert (flat.sharpe_ratio, flat.sortino_ratio, flat.calmar_ratio) == (None, None, None)
    assert flat.max_drawdown == 0
    assert only_up.sortino_ratio is None  # no downside to divide by
    assert only_up.calmar_ratio is None  # no drawdown to divide by
    with pytest.raises(ValueError, match="same length"):
        performance(D("1000"), DATES, EQUITY[:2])


def _round_trip() -> BacktestResult:
    # Same toy run as the engine test: buy 90 at 11, sell 90 at 14, cash 1000, no costs.
    bars = [bar(1, "10", "10"), bar(2, "11", "12"), bar(3, "12", "13"), bar(4, "14", "15")]
    return run_backtest(
        {"X": bars}, Scripted({1: {"X": "1"}, 3: {"X": "0"}}), ZeroCostModel(), config("1000")
    )


def test_trading_metrics_match_hand_calculation() -> None:
    metrics = trading(_round_trip())

    assert (metrics.orders, metrics.fills) == (2, 2)
    assert (metrics.partially_filled_orders, metrics.rejected_orders) == (1, 0)
    assert (metrics.closing_fills, metrics.win_rate) == (1, 1.0)
    assert (metrics.average_win, metrics.average_loss, metrics.profit_factor) == (
        Decimal("270.00"),
        None,
        None,
    )
    assert metrics.average_holding_days == 2.0  # bought session 2, sold session 4
    assert metrics.traded_value == Decimal("2250.00")  # 990 + 1260
    # Average equity (1000 + 1090 + 1180 + 1270) / 4 = 1135.
    assert metrics.turnover == pytest.approx(2250 / 1135)
    assert metrics.annualized_turnover == pytest.approx(2250 / 1135 * 365.25 / 3)
    # Exposure 0, 1080/1090, 1170/1180, 0.
    assert metrics.average_exposure == pytest.approx((1080 / 1090 + 1170 / 1180) / 4)
    assert metrics.max_position_weight == pytest.approx(1170 / 1180)
    assert (metrics.total_fees, metrics.total_slippage) == (Decimal("0"), Decimal("0"))
    assert metrics.costs_share_of_gross_profit == 0


def test_win_and_loss_statistics_and_fifo_holding_period() -> None:
    # Buy 10 at 10 (session 2), buy 10 more at 20 (session 3): average cost 15.
    # Sell 10 at 12 (session 5): loss (12 - 15) * 10 = -30, held 3 days (FIFO lot from 2).
    # Sell 10 at 30 (session 7): win (30 - 15) * 10 = 150, held 4 days (lot from 3).
    bars = [
        bar(1, "10", "10"),
        bar(2, "10", "20"),
        bar(3, "20", "20"),
        bar(4, "20", "12"),
        bar(5, "12", "12"),
        bar(6, "12", "30"),
        bar(7, "30", "30"),
    ]
    # Weights chosen so the share counts come out whole:
    #   session 1: floor(0.10 * 1000 / 10) = 10
    #   session 2: equity 900 + 10*20 = 1100, floor(0.37 * 1100 / 20) = 20
    #   session 4: equity 700 + 20*12 = 940, floor(0.13 * 940 / 12) = 10
    script = {1: {"X": "0.1"}, 2: {"X": "0.37"}, 4: {"X": "0.13"}, 6: {"X": "0"}}

    result = run_backtest({"X": bars}, Scripted(script), ZeroCostModel(), config("1000"))
    metrics = trading(result)

    assert [(f.side.value, f.quantity, f.price) for f in result.fills] == [
        ("BUY", 10, D("10")),
        ("BUY", 10, D("20")),
        ("SELL", 10, D("12")),
        ("SELL", 10, D("30")),
    ]
    assert [f.realized_pnl for f in result.fills] == [None, None, D("-30.00"), D("150.00")]
    assert (metrics.closing_fills, metrics.win_rate) == (2, 0.5)
    assert (metrics.average_win, metrics.average_loss) == (D("150.00"), D("-30.00"))
    assert metrics.profit_factor == 5.0
    assert metrics.average_holding_days == 3.5


def test_gross_adds_back_fees_and_slippage() -> None:
    bars = [bar(1, "100", "100"), bar(2, "100", "100"), bar(3, "100", "100")]

    result = run_backtest(
        {"X": bars},
        Scripted({1: {"X": "0.5"}}),
        ZeroCostModel(),
        config("10000", slippage_bps="100"),
    )
    net, gross = net_performance(result), gross_performance(result)

    # 50 shares at 101 instead of 100: 50 lost to slippage, flat prices otherwise.
    assert net.final_equity == D("9950.00")
    assert gross.final_equity == D("10000.00")
    assert trading(result).total_slippage == D("50.00")
    assert trading(result).costs_share_of_gross_profit is None  # no profit to take a share of


def test_relative_metrics_against_a_benchmark() -> None:
    x = [
        bar(1, "10", "10"),
        bar(2, "10", "11"),
        bar(3, "11", "12"),
        bar(4, "12", "11"),
        bar(5, "11", "13"),
    ]
    # Strategy holds half of what the benchmark holds, so its returns are about half as large.
    half = run_backtest({"X": x}, BuyAndHold({"X": D("0.5")}), ZeroCostModel(), config("1000"))
    full = run_backtest({"X": x}, BuyAndHold({"X": D("1")}), ZeroCostModel(), config("1000"))

    against_itself = relative(full, full)
    against_full = relative(half, full)

    assert against_itself.sessions == 5
    assert against_itself.active_return == pytest.approx(0)
    assert against_itself.beta == pytest.approx(1)
    assert against_itself.annualized_alpha == pytest.approx(0, abs=1e-9)
    assert against_itself.correlation == pytest.approx(1)
    # Full: 100 shares, 1000 -> 1300. Half: 50 shares, 1000 -> 1150.
    assert against_full.active_return == pytest.approx(0.15 - 0.30)
    assert 0.4 < against_full.beta < 0.6  # type: ignore[operator]
    assert against_full.correlation == pytest.approx(1, abs=0.01)


def test_relative_metrics_need_enough_common_sessions() -> None:
    x = [bar(1, "10", "10"), bar(2, "10", "11")]
    result = run_backtest({"X": x}, BuyAndHold({"X": D("1")}), ZeroCostModel(), config("1000"))

    metrics = relative(result, result)

    assert metrics.sessions == 2
    assert (metrics.beta, metrics.annualized_alpha, metrics.correlation) == (None, None, None)
    assert day(1) == date(2024, 1, 1)
