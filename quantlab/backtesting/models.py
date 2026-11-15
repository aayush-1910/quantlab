"""Value types of the backtesting engine.

Money and prices are `Decimal`. Quantities are whole shares. Rounding is explicit:
prices to 4 decimal places, money to 2, both half-even.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum

PRICE_QUANTUM = Decimal("0.0001")
MONEY_QUANTUM = Decimal("0.01")
BPS = Decimal(10000)


def round_price(value: Decimal) -> Decimal:
    return value.quantize(PRICE_QUANTUM, rounding=ROUND_HALF_EVEN)


def round_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    # Created on the last session of the data; there was no later session to fill it in.
    UNFILLED_NO_LATER_SESSION = "UNFILLED_NO_LATER_SESSION"


@dataclass(frozen=True)
class PriceBar:
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class CostBreakdown:
    brokerage: Decimal
    stt: Decimal
    exchange_charges: Decimal
    sebi_charges: Decimal
    stamp_duty: Decimal
    gst: Decimal

    @property
    def total(self) -> Decimal:
        return (
            self.brokerage
            + self.stt
            + self.exchange_charges
            + self.sebi_charges
            + self.stamp_duty
            + self.gst
        )


@dataclass(frozen=True)
class Fill:
    order_id: int
    instrument_id: str
    side: Side
    quantity: int
    # Session open before slippage, and the price actually paid or received.
    reference_price: Decimal
    price: Decimal
    fill_date: date
    costs: CostBreakdown
    # quantity * |price - reference_price|: what slippage cost on this fill.
    slippage_cost: Decimal
    # Net profit of the closed quantity after all fees. None for buys.
    realized_pnl: Decimal | None

    @property
    def value(self) -> Decimal:
        return round_money(self.price * self.quantity)


@dataclass(frozen=True)
class OrderRecord:
    """The full life of one order: when it was decided, when and how it was resolved."""

    order_id: int
    instrument_id: str
    side: Side
    quantity: int
    # The session whose close the decision was based on.
    signal_date: date
    # The first session the order could fill in. None if the data ended first.
    eligible_date: date | None
    status: OrderStatus
    filled_quantity: int
    # Why some or all of the quantity did not fill. Empty for a complete fill.
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class EquityPoint:
    trading_date: date
    cash: Decimal
    positions_value: Decimal
    equity: Decimal
    # Fees and slippage paid up to and including this session.
    cumulative_fees: Decimal
    cumulative_slippage: Decimal
    # Held instruments valued at an earlier close because they have no bar this session.
    stale_valuations: int
    # Value of the single largest position, for concentration.
    largest_position_value: Decimal


@dataclass(frozen=True)
class Position:
    quantity: int
    # Average cost per share including buy-side fees.
    average_cost: Decimal
