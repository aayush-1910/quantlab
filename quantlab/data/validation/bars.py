"""Daily-bar validation (spec section 5.2).

Every source record ends up in exactly one place: the accepted list or the quarantine
list. Nothing is dropped, rounded or repaired.

Rules that quarantine a record:
- unknown or missing instrument;
- missing or unparseable trading_date, price, volume or turnover;
- non-finite or non-positive price; negative volume or turnover;
- more decimal places than the storage precision allows;
- `low <= min(open, close)` or `max(open, close) <= high` violated (tolerance: zero);
- trading_date later than the retrieval date;
- duplicate `(instrument, trading_date)` within the source: identical repeats keep the
  first copy and quarantine the rest; repeats that disagree are all quarantined, because
  there is no basis for choosing one.

Trading-calendar rule: no licensed exchange calendar is integrated yet, so holidays cannot
be checked. Saturday/Sunday bars are accepted and reported as a quality warning, because
NSE does hold occasional weekend sessions (for example Muhurat trading).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from quantlab.data.providers.base import ProviderInfo, RawBarRecord
from quantlab.data.schemas import (
    DAILY_BAR_SCHEMA_VERSION,
    PRICE_DECIMAL_PLACES,
    TURNOVER_DECIMAL_PLACES,
    DailyBar,
    Instrument,
    InstrumentGap,
    QuarantinedRecord,
)

# Bump when validation or normalization behaviour changes. Part of the ingestion
# fingerprint, so changed rules produce a new snapshot version instead of a silent rewrite.
NORMALIZER_VERSION = "1"

_MAX_PRICE = Decimal(10) ** (20 - PRICE_DECIMAL_PLACES)
_MAX_TURNOVER = Decimal(10) ** (24 - TURNOVER_DECIMAL_PLACES)
_MAX_VOLUME = 2**63 - 1
_PRICE_FIELDS = ("open", "high", "low", "close")


@dataclass(frozen=True)
class ValidationResult:
    accepted: tuple[DailyBar, ...]
    quarantined: tuple[QuarantinedRecord, ...]
    quality_warnings: tuple[str, ...]
    weekday_gaps: tuple[InstrumentGap, ...]


def _decimal(
    name: str, text: str | None, places: int, limit: Decimal, reasons: list[str]
) -> Decimal | None:
    if text is None:
        reasons.append(f"{name}: missing")
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        reasons.append(f"{name}: not a number")
        return None
    if not value.is_finite():
        reasons.append(f"{name}: not finite")
        return None
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and -exponent > places:
        reasons.append(f"{name}: more than {places} decimal places")
        return None
    if abs(value) >= limit:
        reasons.append(f"{name}: out of range")
        return None
    return value


def _volume(text: str | None, reasons: list[str]) -> int | None:
    if text is None:
        reasons.append("volume: missing")
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        reasons.append("volume: not a number")
        return None
    if not value.is_finite() or value != value.to_integral_value():
        reasons.append("volume: not a whole number")
        return None
    if value < 0:
        reasons.append("volume: negative")
        return None
    if value > _MAX_VOLUME:
        reasons.append("volume: out of range")
        return None
    return int(value)


def _to_bar(
    record: RawBarRecord,
    instruments: dict[str, Instrument],
    info: ProviderInfo,
    retrieved_at: datetime,
    source_as_of: datetime | None,
) -> DailyBar | list[str]:
    reasons: list[str] = []
    fields = record.fields

    instrument = None
    if record.provider_instrument_id is None:
        reasons.append("provider_instrument_id: missing")
    else:
        instrument = instruments.get(record.provider_instrument_id)
        if instrument is None:
            reasons.append("provider_instrument_id: not in the provider's instrument list")

    trading_date: date | None = None
    date_text = fields.get("trading_date")
    if date_text is None:
        reasons.append("trading_date: missing")
    else:
        try:
            trading_date = date.fromisoformat(date_text)
        except ValueError:
            reasons.append("trading_date: not an ISO date (YYYY-MM-DD)")
    if trading_date is not None and trading_date > retrieved_at.date():
        reasons.append("trading_date: later than the retrieval date")

    prices: dict[str, Decimal] = {}
    for name in _PRICE_FIELDS:
        price = _decimal(name, fields.get(name), PRICE_DECIMAL_PLACES, _MAX_PRICE, reasons)
        if price is None:
            continue
        if price <= 0:
            reasons.append(f"{name}: not positive")
            continue
        prices[name] = price

    volume = _volume(fields.get("volume"), reasons)

    turnover: Decimal | None = None
    if fields.get("turnover") is not None:
        turnover = _decimal(
            "turnover", fields["turnover"], TURNOVER_DECIMAL_PLACES, _MAX_TURNOVER, reasons
        )
        if turnover is not None and turnover < 0:
            reasons.append("turnover: negative")

    if len(prices) == len(_PRICE_FIELDS):
        if prices["low"] > min(prices["open"], prices["close"]):
            reasons.append("ohlc: low is above open or close")
        if prices["high"] < max(prices["open"], prices["close"]):
            reasons.append("ohlc: high is below open or close")

    unexpected = sorted(name for name in fields if name.startswith("_"))
    if unexpected:
        reasons.append("row has more cells than the header has columns")

    if reasons or instrument is None or trading_date is None or volume is None:
        return reasons
    return DailyBar(
        instrument_id=instrument.instrument_id,
        exchange=instrument.exchange,
        trading_date=trading_date,
        open=prices["open"],
        high=prices["high"],
        low=prices["low"],
        close=prices["close"],
        volume=volume,
        turnover=turnover,
        source_id=info.source_id,
        source_record_id=record.source_record_id,
        retrieved_at=retrieved_at,
        source_as_of=source_as_of,
        currency=instrument.currency,
        adjustment_basis=info.adjustment_basis,
        schema_version=DAILY_BAR_SCHEMA_VERSION,
    )


def _quarantine(record: RawBarRecord, reasons: list[str]) -> QuarantinedRecord:
    return QuarantinedRecord(
        source_record_id=record.source_record_id,
        provider_instrument_id=record.provider_instrument_id,
        reasons=tuple(reasons),
        raw_fields=dict(record.fields),
    )


def _values(bar: DailyBar) -> tuple[object, ...]:
    return (bar.open, bar.high, bar.low, bar.close, bar.volume, bar.turnover)


def _weekday_gaps(bars: list[DailyBar]) -> tuple[InstrumentGap, ...]:
    dates: dict[str, set[date]] = {}
    for bar in bars:
        dates.setdefault(bar.instrument_id, set()).add(bar.trading_date)
    gaps = []
    for instrument_id, seen in sorted(dates.items()):
        day, last, missing = min(seen), max(seen), 0
        while day <= last:
            if day.weekday() < 5 and day not in seen:
                missing += 1
            day += timedelta(days=1)
        if missing:
            gaps.append(InstrumentGap(instrument_id=instrument_id, missing_weekdays=missing))
    return tuple(gaps)


def validate_daily_bars(
    records: list[RawBarRecord],
    instruments: dict[str, Instrument],
    info: ProviderInfo,
    retrieved_at: datetime,
    source_as_of: datetime | None = None,
) -> ValidationResult:
    """`instruments` maps provider instrument IDs to registered internal instruments."""
    quarantined: list[QuarantinedRecord] = []
    candidates: dict[tuple[str, date], list[tuple[RawBarRecord, DailyBar]]] = {}

    for record in records:
        outcome = _to_bar(record, instruments, info, retrieved_at, source_as_of)
        if isinstance(outcome, DailyBar):
            candidates.setdefault((outcome.instrument_id, outcome.trading_date), []).append(
                (record, outcome)
            )
        else:
            quarantined.append(_quarantine(record, outcome))

    accepted: list[DailyBar] = []
    for group in candidates.values():
        first_record, first_bar = group[0]
        if len(group) == 1:
            accepted.append(first_bar)
        elif all(_values(bar) == _values(first_bar) for _, bar in group):
            accepted.append(first_bar)
            reason = f"duplicate: identical repeat of {first_record.source_record_id}"
            quarantined.extend(_quarantine(record, [reason]) for record, _ in group[1:])
        else:
            ids = ", ".join(record.source_record_id for record, _ in group)
            reason = f"duplicate: conflicting records for the same instrument and date ({ids})"
            quarantined.extend(_quarantine(record, [reason]) for record, _ in group)

    accepted.sort(key=lambda bar: (bar.instrument_id, bar.trading_date))

    warnings: list[str] = []
    weekend = sum(1 for bar in accepted if bar.trading_date.weekday() >= 5)
    if weekend:
        warnings.append(
            f"{weekend} accepted bar(s) fall on a Saturday or Sunday. No exchange calendar "
            "is integrated, so these could not be checked against real special sessions."
        )
    gaps = _weekday_gaps(accepted)
    if gaps:
        warnings.append(
            f"{len(gaps)} instrument(s) have weekdays without a bar inside their date range. "
            "This count includes exchange holidays, which cannot yet be told apart from "
            "missing data."
        )
    if info.adjustment_basis.value == "UNKNOWN":
        warnings.append(
            "Adjustment basis is UNKNOWN. Returns computed across corporate actions may be wrong."
        )
    if quarantined:
        warnings.append(f"{len(quarantined)} source record(s) were quarantined.")

    return ValidationResult(
        accepted=tuple(accepted),
        quarantined=tuple(quarantined),
        quality_warnings=tuple(warnings),
        weekday_gaps=gaps,
    )
