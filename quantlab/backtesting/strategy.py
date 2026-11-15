"""Strategy interface and the baseline strategies.

A strategy is asked once per session, after that session's close, what the portfolio
should hold. It answers with target weights. It never places orders or sees fills
directly, and the history it is given physically ends at the decision date, so it cannot
read a later bar even by mistake.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from quantlab.backtesting.models import PriceBar


@dataclass(frozen=True)
class DecisionContext:
    # The session that just closed. Every bar in `history` is dated on or before it.
    decision_date: date
    # Bars per instrument, oldest first. Instruments with no bar yet are absent.
    history: Mapping[str, Sequence[PriceBar]]
    # Shares currently held per instrument (only non-zero positions).
    holdings: Mapping[str, int]
    cash: Decimal
    equity: Decimal


class Strategy(Protocol):
    @property
    def strategy_id(self) -> str: ...

    def decide(self, context: DecisionContext) -> Mapping[str, Decimal] | None:
        """Target weight of equity per instrument, or None to leave the portfolio alone.

        Weights are fractions of current equity, each >= 0, summing to at most 1 (long
        only, no leverage). An instrument left out of the mapping is not traded.
        """
        ...


def simple_moving_average(closes: Sequence[Decimal], window: int) -> Decimal | None:
    """Mean of the last `window` closes; None when there are fewer than `window`."""
    if window < 1:
        raise ValueError("window must be at least 1")
    if len(closes) < window:
        return None
    return sum(closes[-window:], Decimal(0)) / Decimal(window)


class MovingAverageCrossover:
    """Trend-following baseline (spec section 2.3, family 1).

    Signal, per instrument: "in" while the fast simple moving average of closes is
    strictly above the slow one, "out" otherwise, including while there is not yet enough
    history for the slow average.

    Trades happen only when the signal and the holding disagree: an "in" instrument that
    is not held is bought to a fixed weight of 1 / (universe size); an "out" instrument
    that is held is sold completely. A position is not topped up or trimmed in between,
    so there is no daily rebalancing churn, and a buy that only partly filled stays at
    the size it got. Cash is held for instruments that are out.
    """

    def __init__(self, universe: Sequence[str], fast_window: int, slow_window: int) -> None:
        if not universe:
            raise ValueError("universe must not be empty")
        if len(set(universe)) != len(universe):
            raise ValueError("universe contains duplicates")
        if not 1 <= fast_window < slow_window:
            raise ValueError("windows must satisfy 1 <= fast_window < slow_window")
        self._universe = tuple(sorted(universe))
        self._fast = fast_window
        self._slow = slow_window

    @property
    def strategy_id(self) -> str:
        return f"ma-crossover(fast={self._fast},slow={self._slow},n={len(self._universe)})"

    def signal(self, closes: Sequence[Decimal]) -> bool:
        """True when the instrument should be held, given closes up to the decision date."""
        fast = simple_moving_average(closes, self._fast)
        slow = simple_moving_average(closes, self._slow)
        return fast is not None and slow is not None and fast > slow

    def decide(self, context: DecisionContext) -> Mapping[str, Decimal]:
        weight = Decimal(1) / Decimal(len(self._universe))
        targets: dict[str, Decimal] = {}
        for instrument_id in self._universe:
            bars = context.history.get(instrument_id, ())
            # No bar on the decision date: no fresh signal, leave the position as it is.
            if not bars or bars[-1].trading_date != context.decision_date:
                continue
            wanted = self.signal([bar.close for bar in bars])
            held = context.holdings.get(instrument_id, 0) > 0
            if wanted and not held:
                targets[instrument_id] = weight
            elif held and not wanted:
                targets[instrument_id] = Decimal(0)
        return targets


class BuyAndHold:
    """Benchmark: buy fixed weights at the first opportunity and never rebalance.

    Stateless: an instrument is targeted on any session where it has a bar and none of it
    is held, so a buy that could not fill is retried, and a filled one is never touched.
    """

    def __init__(self, weights: Mapping[str, Decimal]) -> None:
        if not weights:
            raise ValueError("weights must not be empty")
        self._weights = dict(sorted(weights.items()))

    @property
    def strategy_id(self) -> str:
        parts = ",".join(f"{key}={value}" for key, value in self._weights.items())
        return f"buy-and-hold({parts})"

    def decide(self, context: DecisionContext) -> Mapping[str, Decimal] | None:
        targets = {}
        for instrument_id, weight in self._weights.items():
            bars = context.history.get(instrument_id, ())
            if context.holdings.get(instrument_id, 0) > 0 or not bars:
                continue
            if bars[-1].trading_date == context.decision_date:
                targets[instrument_id] = weight
        return targets or None
