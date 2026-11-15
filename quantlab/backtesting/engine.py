"""Event-driven daily backtest (spec section 6.3).

Timeline, for each session D in date order:

1. FILL   Orders decided after the previous session's close are resolved at D's open.
          Sells first, then buys, each in instrument-ID order.
2. VALUE  The portfolio is valued at D's close.
3. DECIDE The strategy sees bars up to and including D and returns target weights.
4. ORDER  Targets become whole-share orders sized with D's close and D's closing equity.
          They are eligible at the next session in the data, never at D's own close.

Execution model:
- Fill price is the session open moved against the order by `slippage_bps`.
- At most `max_participation` of the fill session's volume can be traded per order.
- A buy is cut down to what cash can pay for, fees included. Cash never goes negative.
- Long only: a sell is cut down to the quantity held.
- An instrument with no bar on the eligible session cannot trade; the order is rejected.
- Whatever does not fill is cancelled, not carried forward. Every order, including
  rejected and partially filled ones, is recorded with its reasons.

Not modelled: corporate actions, dividends, settlement lag (proceeds are usable at once),
price bands and circuit limits, intraday price path, market impact beyond the fixed
slippage. Runs on unadjusted data treat split and bonus price jumps as profit and loss.

Determinism: no randomness and no wall-clock input. The same bars, strategy, cost model
and configuration always produce the same result.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_FLOOR, Decimal
from types import MappingProxyType

from quantlab.backtesting.costs import CostModel
from quantlab.backtesting.models import (
    BPS,
    EquityPoint,
    Fill,
    OrderRecord,
    OrderStatus,
    Position,
    PriceBar,
    Side,
    round_money,
    round_price,
)
from quantlab.backtesting.strategy import DecisionContext, Strategy

ZERO = Decimal(0)


class BacktestInputError(Exception):
    """The bars, configuration or strategy output are not usable."""


@dataclass(frozen=True)
class ExecutionConfig:
    # Both are required: there is no implicit "free and unlimited" execution.
    slippage_bps: Decimal
    # Fraction of a session's volume one order may take. None means no limit, stated openly.
    max_participation: Decimal | None

    def __post_init__(self) -> None:
        if not self.slippage_bps.is_finite() or self.slippage_bps < 0:
            raise BacktestInputError("slippage_bps must be a finite, non-negative number")
        if self.max_participation is not None and not 0 < self.max_participation <= 1:
            raise BacktestInputError("max_participation must be in (0, 1] or None")


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: Decimal
    execution: ExecutionConfig

    def __post_init__(self) -> None:
        if not self.initial_cash.is_finite() or self.initial_cash <= 0:
            raise BacktestInputError("initial_cash must be positive")


@dataclass(frozen=True)
class BacktestResult:
    strategy_id: str
    cost_model_id: str
    config: BacktestConfig
    equity_curve: tuple[EquityPoint, ...]
    orders: tuple[OrderRecord, ...]
    fills: tuple[Fill, ...]
    final_cash: Decimal
    final_positions: Mapping[str, Position]


@dataclass
class _Pending:
    order_id: int
    instrument_id: str
    side: Side
    quantity: int
    signal_date: date


def _validate_bars(bars: Mapping[str, Sequence[PriceBar]]) -> None:
    if not any(bars.values()):
        raise BacktestInputError("no bars supplied")
    for instrument_id, series in bars.items():
        previous: date | None = None
        for bar in series:
            if previous is not None and bar.trading_date <= previous:
                raise BacktestInputError(
                    f"{instrument_id}: bars must be in strictly increasing date order"
                )
            previous = bar.trading_date
            prices = (bar.open, bar.high, bar.low, bar.close)
            if any(not price.is_finite() or price <= 0 for price in prices):
                raise BacktestInputError(f"{instrument_id} {bar.trading_date}: invalid price")
            if bar.volume < 0:
                raise BacktestInputError(f"{instrument_id} {bar.trading_date}: negative volume")


class _Simulation:
    def __init__(
        self,
        bars: Mapping[str, Sequence[PriceBar]],
        strategy: Strategy,
        cost_model: CostModel,
        config: BacktestConfig,
    ) -> None:
        self.strategy = strategy
        self.cost_model = cost_model
        self.config = config
        self.instruments = sorted(bars)
        self.by_date: dict[date, dict[str, PriceBar]] = {}
        for instrument_id in self.instruments:
            for bar in bars[instrument_id]:
                self.by_date.setdefault(bar.trading_date, {})[instrument_id] = bar
        self.timeline = sorted(self.by_date)

        self.cash = config.initial_cash
        self.positions: dict[str, Position] = {}
        self.last_close: dict[str, Decimal] = {}
        self.history: dict[str, list[PriceBar]] = {}
        self.pending: list[_Pending] = []
        self.orders: list[OrderRecord] = []
        self.fills: list[Fill] = []
        self.equity_curve: list[EquityPoint] = []
        self.fees = ZERO
        self.slippage = ZERO
        self.next_order_id = 1

    # --- step 1: fills ---------------------------------------------------------------

    def _affordable(self, quantity: int, price: Decimal, on: date) -> int:
        """Largest quantity <= `quantity` whose value plus fees fits in cash."""

        def total(q: int) -> Decimal:
            value = round_money(price * q)
            return value + self.cost_model.costs(Side.BUY, value, on).total

        if total(quantity) <= self.cash:
            return quantity
        low, high = 0, quantity  # total(low) fits, total(high) does not
        while high - low > 1:
            middle = (low + high) // 2
            if total(middle) <= self.cash:
                low = middle
            else:
                high = middle
        return low

    def _resolve(self, order: _Pending, today: date) -> None:
        bar = self.by_date[today].get(order.instrument_id)
        reasons: list[str] = []
        quantity = order.quantity
        if bar is None:
            self._record(order, today, 0, ["no bar on the eligible session"])
            return

        sign = 1 if order.side is Side.BUY else -1
        slip = self.config.execution.slippage_bps / BPS
        price = round_price(bar.open * (1 + sign * slip))

        if order.side is Side.SELL:
            held = self.positions.get(order.instrument_id, Position(0, ZERO)).quantity
            if quantity > held:
                quantity = held
                reasons.append("reduced to the quantity held")
        participation = self.config.execution.max_participation
        if participation is not None:
            cap = int((Decimal(bar.volume) * participation).to_integral_value(ROUND_FLOOR))
            if quantity > cap:
                quantity = cap
                reasons.append(
                    f"limited to {participation:%} of session volume ({bar.volume} shares)"
                )
        if order.side is Side.BUY:
            affordable = self._affordable(quantity, price, today)
            if affordable < quantity:
                quantity = affordable
                reasons.append("limited by available cash")
        if quantity == 0:
            self._record(order, today, 0, reasons)
            return

        value = round_money(price * quantity)
        costs = self.cost_model.costs(order.side, value, today)
        position = self.positions.get(order.instrument_id, Position(0, ZERO))
        realized: Decimal | None = None
        if order.side is Side.BUY:
            self.cash -= value + costs.total
            new_quantity = position.quantity + quantity
            basis = position.average_cost * position.quantity + value + costs.total
            self.positions[order.instrument_id] = Position(new_quantity, basis / new_quantity)
        else:
            self.cash += value - costs.total
            realized = round_money(value - costs.total - position.average_cost * quantity)
            remaining = position.quantity - quantity
            if remaining:
                self.positions[order.instrument_id] = Position(remaining, position.average_cost)
            else:
                del self.positions[order.instrument_id]
        slippage_cost = round_money(abs(price - bar.open) * quantity)
        self.fees += costs.total
        self.slippage += slippage_cost
        self.fills.append(
            Fill(
                order_id=order.order_id,
                instrument_id=order.instrument_id,
                side=order.side,
                quantity=quantity,
                reference_price=bar.open,
                price=price,
                fill_date=today,
                costs=costs,
                slippage_cost=slippage_cost,
                realized_pnl=realized,
            )
        )
        self._record(order, today, quantity, reasons)

    def _record(
        self, order: _Pending, eligible: date | None, filled: int, reasons: list[str]
    ) -> None:
        if eligible is None:
            status = OrderStatus.UNFILLED_NO_LATER_SESSION
        elif filled == 0:
            status = OrderStatus.REJECTED
        elif filled < order.quantity:
            status = OrderStatus.PARTIALLY_FILLED
        else:
            status = OrderStatus.FILLED
        self.orders.append(
            OrderRecord(
                order_id=order.order_id,
                instrument_id=order.instrument_id,
                side=order.side,
                quantity=order.quantity,
                signal_date=order.signal_date,
                eligible_date=eligible,
                status=status,
                filled_quantity=filled,
                reasons=tuple(reasons),
            )
        )

    # --- step 2: valuation -----------------------------------------------------------

    def _value(self, today: date) -> EquityPoint:
        positions_value = ZERO
        largest = ZERO
        stale = 0
        for instrument_id in sorted(self.positions):
            if instrument_id not in self.by_date[today]:
                stale += 1
            close = self.last_close[instrument_id]
            value = round_money(close * self.positions[instrument_id].quantity)
            positions_value += value
            largest = max(largest, value)
        point = EquityPoint(
            trading_date=today,
            cash=self.cash,
            positions_value=positions_value,
            equity=self.cash + positions_value,
            cumulative_fees=self.fees,
            cumulative_slippage=self.slippage,
            stale_valuations=stale,
            largest_position_value=largest,
        )
        self.equity_curve.append(point)
        return point

    # --- steps 3 and 4: decision and orders ------------------------------------------

    def _decide(self, today: date, point: EquityPoint) -> None:
        context = DecisionContext(
            decision_date=today,
            history=MappingProxyType(self.history),
            holdings=MappingProxyType({k: p.quantity for k, p in self.positions.items()}),
            cash=self.cash,
            equity=point.equity,
        )
        targets = self.strategy.decide(context)
        if not targets:
            return
        total = ZERO
        for instrument_id, weight in targets.items():
            if instrument_id not in self.history and instrument_id not in self.instruments:
                raise BacktestInputError(f"strategy targeted unknown instrument {instrument_id}")
            if not weight.is_finite() or weight < 0:
                raise BacktestInputError(f"target weight for {instrument_id} is invalid: {weight}")
            total += weight
        if total > 1:
            raise BacktestInputError(f"target weights sum to {total}, above 1 (no leverage)")

        for instrument_id in sorted(targets):
            held = self.positions.get(instrument_id, Position(0, ZERO)).quantity
            bar = self.by_date[today].get(instrument_id)
            if bar is None:
                # No close on the signal date, so the order cannot be sized without
                # borrowing a stale or future price.
                if targets[instrument_id] > 0 or held > 0:
                    self._create(instrument_id, Side.BUY, 0, today, unsizable=True)
                continue
            target_quantity = int(
                (targets[instrument_id] * point.equity / bar.close).to_integral_value(ROUND_FLOOR)
            )
            delta = target_quantity - held
            if delta > 0:
                self._create(instrument_id, Side.BUY, delta, today)
            elif delta < 0:
                self._create(instrument_id, Side.SELL, -delta, today)

    def _create(
        self, instrument_id: str, side: Side, quantity: int, today: date, unsizable: bool = False
    ) -> None:
        order = _Pending(self.next_order_id, instrument_id, side, quantity, today)
        self.next_order_id += 1
        if unsizable:
            self.orders.append(
                OrderRecord(
                    order_id=order.order_id,
                    instrument_id=instrument_id,
                    side=side,
                    quantity=0,
                    signal_date=today,
                    eligible_date=None,
                    status=OrderStatus.REJECTED,
                    filled_quantity=0,
                    reasons=("no close on the signal date to size the order",),
                )
            )
        else:
            self.pending.append(order)

    # --- main loop -------------------------------------------------------------------

    def run(self) -> BacktestResult:
        for today in self.timeline:
            pending, self.pending = self.pending, []
            pending.sort(key=lambda o: (o.side is Side.BUY, o.instrument_id, o.order_id))
            for order in pending:
                self._resolve(order, today)

            for instrument_id, bar in self.by_date[today].items():
                self.last_close[instrument_id] = bar.close
                self.history.setdefault(instrument_id, []).append(bar)
            point = self._value(today)
            self._decide(today, point)

        for order in self.pending:
            self._record(order, None, 0, ["the data ended before the order became eligible"])
        self.orders.sort(key=lambda record: record.order_id)
        return BacktestResult(
            strategy_id=self.strategy.strategy_id,
            cost_model_id=self.cost_model.model_id,
            config=self.config,
            equity_curve=tuple(self.equity_curve),
            orders=tuple(self.orders),
            fills=tuple(self.fills),
            final_cash=self.cash,
            final_positions=MappingProxyType(dict(sorted(self.positions.items()))),
        )


def run_backtest(
    bars: Mapping[str, Sequence[PriceBar]],
    strategy: Strategy,
    cost_model: CostModel,
    config: BacktestConfig,
) -> BacktestResult:
    """`bars` maps instrument ID to that instrument's bars, oldest first."""
    _validate_bars(bars)
    return _Simulation(bars, strategy, cost_model, config).run()
