"""Shared builders for backtesting tests. Every price here is SYNTHETIC_TEST_DATA."""

from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal

from quantlab.backtesting.engine import BacktestConfig, ExecutionConfig
from quantlab.backtesting.models import PriceBar
from quantlab.backtesting.strategy import DecisionContext

D = Decimal
START = date(2024, 1, 1)


def day(n: int) -> date:
    """Session n (1-based) of a toy calendar with one session per calendar day."""
    return START + timedelta(days=n - 1)


def bar(n: int, open_: str, close: str, volume: int = 1_000_000) -> PriceBar:
    o, c = D(open_), D(close)
    return PriceBar(day(n), o, max(o, c), min(o, c), c, volume)


def config(
    cash: str = "1000", slippage_bps: str = "0", participation: str | None = None
) -> BacktestConfig:
    return BacktestConfig(
        initial_cash=D(cash),
        execution=ExecutionConfig(D(slippage_bps), D(participation) if participation else None),
    )


class Scripted:
    """Returns pre-written targets on given session numbers; nothing on other sessions."""

    strategy_id = "scripted"

    def __init__(self, script: Mapping[int, Mapping[str, str]]) -> None:
        self._script = {day(n): {k: D(v) for k, v in t.items()} for n, t in script.items()}
        self.seen: list[tuple[date, date]] = []

    def decide(self, context: DecisionContext) -> Mapping[str, Decimal] | None:
        latest = max(bars[-1].trading_date for bars in context.history.values())
        self.seen.append((context.decision_date, latest))
        return self._script.get(context.decision_date)
