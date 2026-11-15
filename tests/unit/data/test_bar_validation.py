from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from quantlab.data.providers.base import ProviderInfo, RawBarRecord
from quantlab.data.schemas import (
    AdjustmentBasis,
    Currency,
    DataClassification,
    Exchange,
    Instrument,
    InstrumentType,
)
from quantlab.data.validation.bars import validate_daily_bars

RETRIEVED_AT = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
INSTRUMENTS = {
    "T1": Instrument(
        instrument_id="internal-1",
        exchange=Exchange.NSE,
        instrument_type=InstrumentType.EQUITY,
        currency=Currency.INR,
    )
}


def _info(basis: AdjustmentBasis = AdjustmentBasis.UNADJUSTED) -> ProviderInfo:
    return ProviderInfo(
        source_id="test_src",
        provider_name="SYNTHETIC_TEST_DATA",
        licence_reference="n/a",
        data_classification=DataClassification.SYNTHETIC_TEST_DATA,
        source_dataset_version="1",
        adjustment_basis=basis,
        adjustment_methodology="none",
    )


def _record(n: int = 1, pid: str | None = "T1", **overrides: str | None) -> RawBarRecord:
    fields: dict[str, str | None] = {
        "trading_date": "2024-01-01",
        "open": "100.00",
        "high": "102.00",
        "low": "99.00",
        "close": "101.00",
        "volume": "1000",
        "turnover": "100500.00",
    }
    fields.update(overrides)
    return RawBarRecord(source_record_id=f"r{n}", provider_instrument_id=pid, fields=fields)


def _validate(*records: RawBarRecord, basis: AdjustmentBasis = AdjustmentBasis.UNADJUSTED):  # type: ignore[no-untyped-def]
    return validate_daily_bars(list(records), INSTRUMENTS, _info(basis), RETRIEVED_AT)


def test_valid_record_becomes_a_canonical_bar() -> None:
    result = _validate(_record())

    (bar,) = result.accepted
    assert bar.instrument_id == "internal-1"
    assert bar.exchange is Exchange.NSE
    assert bar.trading_date == date(2024, 1, 1)
    assert (bar.open, bar.high, bar.low, bar.close) == (
        Decimal("100.00"),
        Decimal("102.00"),
        Decimal("99.00"),
        Decimal("101.00"),
    )
    assert bar.volume == 1000
    assert bar.turnover == Decimal("100500.00")
    assert bar.source_id == "test_src"
    assert bar.source_record_id == "r1"
    assert bar.retrieved_at == RETRIEVED_AT
    assert bar.adjustment_basis is AdjustmentBasis.UNADJUSTED
    assert result.quarantined == ()
    assert result.quality_warnings == ()


def test_missing_turnover_is_an_explicit_null() -> None:
    (bar,) = _validate(_record(turnover=None)).accepted

    assert bar.turnover is None


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"trading_date": None}, "trading_date: missing"),
        ({"trading_date": "01-01-2024"}, "trading_date: not an ISO date"),
        ({"trading_date": "2024-06-02"}, "trading_date: later than the retrieval date"),
        ({"open": None}, "open: missing"),
        ({"close": "abc"}, "close: not a number"),
        ({"high": "NaN"}, "high: not finite"),
        ({"high": "Infinity"}, "high: not finite"),
        ({"low": "0"}, "low: not positive"),
        ({"low": "-1"}, "low: not positive"),
        ({"open": "100.1234567"}, "open: more than 6 decimal places"),
        ({"close": "1e20"}, "close: out of range"),
        ({"volume": None}, "volume: missing"),
        ({"volume": "-5"}, "volume: negative"),
        ({"volume": "10.5"}, "volume: not a whole number"),
        ({"volume": "many"}, "volume: not a number"),
        ({"turnover": "-1"}, "turnover: negative"),
        ({"turnover": "1.00001"}, "turnover: more than 4 decimal places"),
        ({"low": "100.50"}, "ohlc: low is above open or close"),
        ({"high": "100.50"}, "ohlc: high is below open or close"),
        ({"_extra_cells": "9"}, "row has more cells"),
    ],
)
def test_invalid_record_is_quarantined_with_its_reason(
    overrides: dict[str, str | None], reason: str
) -> None:
    result = _validate(_record(1, "T1", **overrides))

    assert result.accepted == ()
    (bad,) = result.quarantined
    assert any(reason in r for r in bad.reasons), bad.reasons
    assert bad.source_record_id == "r1"
    assert bad.raw_fields["volume"] == _record(1, "T1", **overrides).fields["volume"]


def test_unknown_and_missing_instruments_are_quarantined() -> None:
    result = _validate(_record(1, pid="NOPE"), _record(2, pid=None))

    assert result.accepted == ()
    assert "not in the provider's instrument list" in result.quarantined[0].reasons[0]
    assert "provider_instrument_id: missing" in result.quarantined[1].reasons[0]


def test_every_reason_is_reported_for_a_record() -> None:
    (bad,) = _validate(_record(open="x", volume="-1", trading_date="bad")).quarantined

    assert len(bad.reasons) == 3


def test_ohlc_boundaries_are_inclusive_and_whole_number_volume_text_is_accepted() -> None:
    result = _validate(_record(open="5", high="5", low="5", close="5", volume="1000.0"))

    assert len(result.accepted) == 1
    assert result.accepted[0].volume == 1000


def test_identical_duplicates_keep_the_first_and_quarantine_the_rest() -> None:
    result = _validate(_record(1), _record(2, open="100.0"), _record(3))

    assert [bar.source_record_id for bar in result.accepted] == ["r1"]
    assert [bad.source_record_id for bad in result.quarantined] == ["r2", "r3"]
    assert all("identical repeat of r1" in bad.reasons[0] for bad in result.quarantined)


def test_conflicting_duplicates_are_all_quarantined() -> None:
    result = _validate(_record(1), _record(2, close="101.50"))

    assert result.accepted == ()
    assert [bad.source_record_id for bad in result.quarantined] == ["r1", "r2"]
    assert all("conflicting" in bad.reasons[0] for bad in result.quarantined)


def test_no_record_is_silently_dropped() -> None:
    records = [
        _record(1),
        _record(2),
        _record(3, trading_date="2024-01-02", close="bad"),
        _record(4, trading_date="2024-01-03"),
        _record(5, pid="NOPE"),
    ]

    result = _validate(*records)

    assert len(result.accepted) + len(result.quarantined) == len(records)
    assert any("quarantined" in warning for warning in result.quality_warnings)


def test_accepted_bars_are_sorted_by_instrument_and_date() -> None:
    result = _validate(_record(1, trading_date="2024-01-03"), _record(2, trading_date="2024-01-02"))

    assert [bar.trading_date for bar in result.accepted] == [date(2024, 1, 2), date(2024, 1, 3)]


def test_weekend_bars_are_accepted_with_a_warning() -> None:
    result = _validate(_record(trading_date="2024-01-06"))  # a Saturday

    assert len(result.accepted) == 1
    assert any("Saturday or Sunday" in warning for warning in result.quality_warnings)


def test_missing_weekdays_inside_the_range_are_counted() -> None:
    # Mon 1 Jan and Fri 5 Jan present; Tue-Thu missing. The weekend after is not counted.
    result = _validate(
        _record(1, trading_date="2024-01-01"),
        _record(2, trading_date="2024-01-05"),
        _record(3, trading_date="2024-01-08"),
    )

    (gap,) = result.weekday_gaps
    assert (gap.instrument_id, gap.missing_weekdays) == ("internal-1", 3)
    assert any("holidays" in warning for warning in result.quality_warnings)


def test_unknown_adjustment_basis_raises_a_warning() -> None:
    result = _validate(_record(), basis=AdjustmentBasis.UNKNOWN)

    assert result.accepted[0].adjustment_basis is AdjustmentBasis.UNKNOWN
    assert any("UNKNOWN" in warning for warning in result.quality_warnings)
