"""Performance metrics for a backtest (spec section 6.6).

Accounting inside the engine is exact (`Decimal`). The statistics here are descriptive and
use floats.

Definitions and assumptions:
- Returns are simple session-to-session returns of the equity curve. The first return is
  measured from initial cash to the first session's closing equity.
- Annualization uses 252 sessions per year. CAGR uses calendar days / 365.25 between the
  first and last session and is None for a single session.
- Volatility is the sample standard deviation of session returns times sqrt(252).
- Sharpe = (mean return - risk-free per session) / sample standard deviation * sqrt(252).
  The risk-free rate is an explicit annual input; per session it is rate / 252.
- Sortino uses downside deviation: sqrt(mean(min(return - risk-free, 0)^2)) over all
  sessions.
- Maximum drawdown is the largest peak-to-trough fall of equity, as a negative fraction.
  Its duration is the longest run of sessions spent below a previous peak, including a
  drawdown still open at the end.
- Calmar = CAGR / |maximum drawdown|.
- Win statistics are per closing (sell) fill, using profit net of all fees against the
  average cost of the position, buy fees included.
- Holding period is matched first-in first-out per instrument, weighted by shares, in
  calendar days. Shares still held at the end are not counted.
- Turnover = total traded value / average closing equity.
- Exposure = positions value / equity, averaged over sessions. Concentration is the
  largest single position / equity, at its maximum over sessions.
- "Gross" equity adds back the fees and slippage paid so far. It does not re-run the
  strategy without costs, so it ignores what that money would have earned if invested.

A ratio whose denominator is zero, or that needs more observations than exist, is None.
None of these numbers is a forecast.
"""

import math
import statistics
from collections import deque
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from quantlab.backtesting.engine import BacktestResult
from quantlab.backtesting.models import OrderStatus, Side

SESSIONS_PER_YEAR = 252
DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class PerformanceMetrics:
    start_date: date
    end_date: date
    sessions: int
    initial_equity: Decimal
    final_equity: Decimal
    cumulative_return: float
    cagr: float | None
    annualized_volatility: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    max_drawdown: float
    max_drawdown_duration_sessions: int
    calmar_ratio: float | None


@dataclass(frozen=True)
class TradingMetrics:
    orders: int
    fills: int
    rejected_orders: int
    partially_filled_orders: int
    unfilled_at_end_orders: int
    closing_fills: int
    win_rate: float | None
    average_win: Decimal | None
    average_loss: Decimal | None
    profit_factor: float | None
    average_holding_days: float | None
    traded_value: Decimal
    turnover: float
    annualized_turnover: float | None
    average_exposure: float
    max_position_weight: float
    total_fees: Decimal
    total_slippage: Decimal
    # Fees and slippage as a fraction of profit before them. None when that profit is <= 0.
    costs_share_of_gross_profit: float | None
    sessions_with_stale_valuation: int


@dataclass(frozen=True)
class RelativeMetrics:
    """Strategy against benchmark, on the sessions both have."""

    sessions: int
    active_return: float
    beta: float | None
    annualized_alpha: float | None
    correlation: float | None


def session_returns(initial: Decimal, equities: list[Decimal]) -> list[float]:
    returns = []
    previous = initial
    for equity in equities:
        returns.append(float(equity / previous) - 1.0)
        previous = equity
    return returns


def max_drawdown(initial: Decimal, equities: list[Decimal]) -> tuple[float, int]:
    """(largest fall from a peak as a negative fraction, longest sessions below a peak)."""
    peak = initial
    worst = 0.0
    duration = longest = 0
    for equity in equities:
        if equity >= peak:
            peak = equity
            duration = 0
        else:
            duration += 1
            longest = max(longest, duration)
            worst = min(worst, float(equity / peak) - 1.0)
    return worst, longest


def performance(
    initial: Decimal,
    dates: list[date],
    equities: list[Decimal],
    risk_free_rate: float = 0.0,
) -> PerformanceMetrics:
    if not dates or len(dates) != len(equities):
        raise ValueError("dates and equities must be non-empty and the same length")
    returns = session_returns(initial, equities)
    final = equities[-1]
    cumulative = float(final / initial) - 1.0
    days = (dates[-1] - dates[0]).days
    cagr = (float(final / initial) ** (DAYS_PER_YEAR / days) - 1.0) if days > 0 else None

    risk_free = risk_free_rate / SESSIONS_PER_YEAR
    deviation = statistics.stdev(returns) if len(returns) >= 2 else None
    volatility = deviation * math.sqrt(SESSIONS_PER_YEAR) if deviation is not None else None
    excess = statistics.fmean(returns) - risk_free
    sharpe = excess / deviation * math.sqrt(SESSIONS_PER_YEAR) if deviation else None
    downside = math.sqrt(statistics.fmean(min(r - risk_free, 0.0) ** 2 for r in returns))
    sortino = (
        excess / downside * math.sqrt(SESSIONS_PER_YEAR)
        if downside > 0 and len(returns) >= 2
        else None
    )
    drawdown, duration = max_drawdown(initial, equities)
    calmar = cagr / abs(drawdown) if cagr is not None and drawdown < 0 else None
    return PerformanceMetrics(
        start_date=dates[0],
        end_date=dates[-1],
        sessions=len(dates),
        initial_equity=initial,
        final_equity=final,
        cumulative_return=cumulative,
        cagr=cagr,
        annualized_volatility=volatility,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown=drawdown,
        max_drawdown_duration_sessions=duration,
        calmar_ratio=calmar,
    )


def net_performance(result: BacktestResult, risk_free_rate: float = 0.0) -> PerformanceMetrics:
    curve = result.equity_curve
    return performance(
        result.config.initial_cash,
        [point.trading_date for point in curve],
        [point.equity for point in curve],
        risk_free_rate,
    )


def gross_performance(result: BacktestResult, risk_free_rate: float = 0.0) -> PerformanceMetrics:
    curve = result.equity_curve
    return performance(
        result.config.initial_cash,
        [point.trading_date for point in curve],
        [point.equity + point.cumulative_fees + point.cumulative_slippage for point in curve],
        risk_free_rate,
    )


def _average_holding_days(result: BacktestResult) -> float | None:
    lots: dict[str, deque[tuple[date, int]]] = {}
    share_days = 0
    shares = 0
    for fill in result.fills:
        queue = lots.setdefault(fill.instrument_id, deque())
        if fill.side is Side.BUY:
            queue.append((fill.fill_date, fill.quantity))
            continue
        remaining = fill.quantity
        while remaining:
            bought, quantity = queue[0]
            matched = min(quantity, remaining)
            share_days += matched * (fill.fill_date - bought).days
            shares += matched
            remaining -= matched
            if matched == quantity:
                queue.popleft()
            else:
                queue[0] = (bought, quantity - matched)
    return share_days / shares if shares else None


def trading(result: BacktestResult) -> TradingMetrics:
    curve = result.equity_curve
    closing = [fill.realized_pnl for fill in result.fills if fill.realized_pnl is not None]
    wins = [pnl for pnl in closing if pnl > 0]
    losses = [pnl for pnl in closing if pnl < 0]
    traded = sum((fill.value for fill in result.fills), Decimal(0))
    average_equity = sum((point.equity for point in curve), Decimal(0)) / len(curve)
    turnover = float(traded / average_equity)
    days = (curve[-1].trading_date - curve[0].trading_date).days
    fees, slippage = curve[-1].cumulative_fees, curve[-1].cumulative_slippage
    gross_profit = curve[-1].equity + fees + slippage - result.config.initial_cash
    return TradingMetrics(
        orders=len(result.orders),
        fills=len(result.fills),
        rejected_orders=sum(1 for o in result.orders if o.status is OrderStatus.REJECTED),
        partially_filled_orders=sum(
            1 for o in result.orders if o.status is OrderStatus.PARTIALLY_FILLED
        ),
        unfilled_at_end_orders=sum(
            1 for o in result.orders if o.status is OrderStatus.UNFILLED_NO_LATER_SESSION
        ),
        closing_fills=len(closing),
        win_rate=len(wins) / len(closing) if closing else None,
        average_win=sum(wins, Decimal(0)) / len(wins) if wins else None,
        average_loss=sum(losses, Decimal(0)) / len(losses) if losses else None,
        profit_factor=float(sum(wins, Decimal(0)) / -sum(losses, Decimal(0))) if losses else None,
        average_holding_days=_average_holding_days(result),
        traded_value=traded,
        turnover=turnover,
        annualized_turnover=turnover * DAYS_PER_YEAR / days if days > 0 else None,
        average_exposure=statistics.fmean(
            float(point.positions_value / point.equity) for point in curve
        ),
        max_position_weight=max(
            float(point.largest_position_value / point.equity) for point in curve
        ),
        total_fees=fees,
        total_slippage=slippage,
        costs_share_of_gross_profit=(
            float((fees + slippage) / gross_profit) if gross_profit > 0 else None
        ),
        sessions_with_stale_valuation=sum(1 for point in curve if point.stale_valuations),
    )


def relative(strategy: BacktestResult, benchmark: BacktestResult) -> RelativeMetrics:
    """Compare session returns on the dates both curves share, in date order."""

    def by_date(result: BacktestResult) -> dict[date, float]:
        dates = [point.trading_date for point in result.equity_curve]
        returns = session_returns(
            result.config.initial_cash, [point.equity for point in result.equity_curve]
        )
        return dict(zip(dates, returns, strict=True))

    ours, theirs = by_date(strategy), by_date(benchmark)
    common = sorted(ours.keys() & theirs.keys())
    xs = [theirs[day] for day in common]
    ys = [ours[day] for day in common]
    active = math.prod(1 + y for y in ys) - math.prod(1 + x for x in xs) if common else 0.0
    beta = alpha = correlation = None
    if len(common) >= 3 and statistics.variance(xs) > 0:
        beta = statistics.covariance(xs, ys) / statistics.variance(xs)
        alpha = (statistics.fmean(ys) - beta * statistics.fmean(xs)) * SESSIONS_PER_YEAR
        if statistics.variance(ys) > 0:
            correlation = statistics.correlation(xs, ys)
    return RelativeMetrics(
        sessions=len(common),
        active_return=active,
        beta=beta,
        annualized_alpha=alpha,
        correlation=correlation,
    )
