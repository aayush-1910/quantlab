"""Transaction costs from a versioned, effective-dated schedule (spec section 6.3).

This module contains NO real-world rates. Indian charges (brokerage, STT, exchange
transaction charges, SEBI charges, stamp duty, GST) change over time and differ by broker,
exchange, segment and product, so a schedule must be supplied by whoever runs a backtest,
with a note saying where each set of rates came from. A date no entry covers is an error,
never a silent zero.

Model, per fill of traded value V:
    brokerage        = min(V * brokerage_rate, brokerage_cap_per_order) if a cap is set
    stt              = V * stt_buy_rate or stt_sell_rate
    exchange_charges = V * exchange_rate
    sebi_charges     = V * sebi_rate
    stamp_duty       = V * stamp_duty_buy_rate on buys only
    gst              = gst_rate * (brokerage + exchange_charges + sebi_charges)
Each component is rounded half-even to 0.01. This is a simplification: real contract notes
aggregate per day and apply their own rounding rules.
"""

import itertools
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

from quantlab.backtesting.models import CostBreakdown, Side, round_money

ZERO = Decimal(0)


class CostModelError(Exception):
    pass


@dataclass(frozen=True)
class CostRates:
    brokerage_rate: Decimal = ZERO
    brokerage_cap_per_order: Decimal | None = None
    stt_buy_rate: Decimal = ZERO
    stt_sell_rate: Decimal = ZERO
    exchange_rate: Decimal = ZERO
    sebi_rate: Decimal = ZERO
    stamp_duty_buy_rate: Decimal = ZERO
    gst_rate: Decimal = ZERO

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if value is not None and (not value.is_finite() or value < 0):
                raise CostModelError(f"{name} must be a finite, non-negative number")


def compute_costs(rates: CostRates, side: Side, value: Decimal) -> CostBreakdown:
    brokerage = value * rates.brokerage_rate
    if rates.brokerage_cap_per_order is not None:
        brokerage = min(brokerage, rates.brokerage_cap_per_order)
    brokerage = round_money(brokerage)
    stt = round_money(value * (rates.stt_buy_rate if side is Side.BUY else rates.stt_sell_rate))
    exchange_charges = round_money(value * rates.exchange_rate)
    sebi_charges = round_money(value * rates.sebi_rate)
    stamp_duty = round_money(value * rates.stamp_duty_buy_rate) if side is Side.BUY else ZERO
    gst = round_money(rates.gst_rate * (brokerage + exchange_charges + sebi_charges))
    return CostBreakdown(
        brokerage=brokerage,
        stt=stt,
        exchange_charges=exchange_charges,
        sebi_charges=sebi_charges,
        stamp_duty=stamp_duty,
        gst=gst,
    )


class CostModel(Protocol):
    @property
    def model_id(self) -> str: ...

    def costs(self, side: Side, value: Decimal, on: date) -> CostBreakdown: ...


class ZeroCostModel:
    """No fees at all. Results from it are gross by construction and must be labelled so."""

    model_id = "zero-costs"

    def costs(self, side: Side, value: Decimal, on: date) -> CostBreakdown:
        return compute_costs(CostRates(), side, value)


@dataclass(frozen=True)
class CostScheduleEntry:
    effective_from: date
    # Inclusive. None means still in effect.
    effective_to: date | None
    rates: CostRates
    # Where these rates came from and when they were checked.
    source_note: str


class CostSchedule:
    def __init__(self, schedule_id: str, version: str, entries: list[CostScheduleEntry]) -> None:
        if not entries:
            raise CostModelError("a cost schedule needs at least one entry")
        ordered = sorted(entries, key=lambda entry: entry.effective_from)
        for entry in ordered:
            if not entry.source_note.strip():
                raise CostModelError("every cost schedule entry needs a source_note")
            if entry.effective_to is not None and entry.effective_to < entry.effective_from:
                raise CostModelError("a cost schedule entry ends before it starts")
        for earlier, later in itertools.pairwise(ordered):
            if earlier.effective_to is None or earlier.effective_to >= later.effective_from:
                raise CostModelError("cost schedule entries overlap")
        self.schedule_id = schedule_id
        self.version = version
        self.entries = tuple(ordered)

    @property
    def model_id(self) -> str:
        return f"{self.schedule_id}@{self.version}"

    def rates_on(self, on: date) -> CostRates:
        for entry in self.entries:
            if entry.effective_from <= on and (
                entry.effective_to is None or on <= entry.effective_to
            ):
                return entry.rates
        raise CostModelError(f"cost schedule {self.model_id} has no rates in effect on {on}")

    def costs(self, side: Side, value: Decimal, on: date) -> CostBreakdown:
        return compute_costs(self.rates_on(on), side, value)


def _decimal(document: dict[str, Any], key: str, default: Decimal | None) -> Decimal | None:
    if key not in document or document[key] is None:
        return default
    raw = document[key]
    if not isinstance(raw, str):
        # Rates written as JSON numbers pass through binary floats; require exact strings.
        raise CostModelError(f'{key} must be a decimal written as a string, e.g. "0.001"')
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise CostModelError(f"{key} is not a decimal number: {raw!r}") from exc


def load_cost_schedule(path: Path) -> CostSchedule:
    """Load a schedule from JSON. See docs/research_methodology/backtesting.md for the format."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        entries = [
            CostScheduleEntry(
                effective_from=date.fromisoformat(item["effective_from"]),
                effective_to=(
                    date.fromisoformat(item["effective_to"]) if item.get("effective_to") else None
                ),
                rates=CostRates(
                    brokerage_rate=_decimal(item["rates"], "brokerage_rate", ZERO) or ZERO,
                    brokerage_cap_per_order=_decimal(
                        item["rates"], "brokerage_cap_per_order", None
                    ),
                    stt_buy_rate=_decimal(item["rates"], "stt_buy_rate", ZERO) or ZERO,
                    stt_sell_rate=_decimal(item["rates"], "stt_sell_rate", ZERO) or ZERO,
                    exchange_rate=_decimal(item["rates"], "exchange_rate", ZERO) or ZERO,
                    sebi_rate=_decimal(item["rates"], "sebi_rate", ZERO) or ZERO,
                    stamp_duty_buy_rate=_decimal(item["rates"], "stamp_duty_buy_rate", ZERO)
                    or ZERO,
                    gst_rate=_decimal(item["rates"], "gst_rate", ZERO) or ZERO,
                ),
                source_note=str(item.get("source_note", "")),
            )
            for item in document["entries"]
        ]
        return CostSchedule(str(document["schedule_id"]), str(document["version"]), entries)
    except (KeyError, TypeError, ValueError) as exc:
        raise CostModelError(f"invalid cost schedule file {path}: {exc}") from exc
