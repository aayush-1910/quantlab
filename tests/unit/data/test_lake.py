from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from quantlab.data.providers.base import RawPayload
from quantlab.data.schemas import (
    AdjustmentBasis,
    Currency,
    DailyBar,
    Exchange,
    QuarantinedRecord,
)
from quantlab.data.storage.lake import (
    DataLake,
    LakeIntegrityError,
    content_sha256,
    sha256_bytes,
)


def _bar(**overrides: object) -> DailyBar:
    values: dict[str, object] = {
        "instrument_id": "internal-1",
        "exchange": Exchange.NSE,
        "trading_date": date(2024, 1, 1),
        "open": Decimal("100.05"),
        "high": Decimal("102.123456"),
        "low": Decimal("99"),
        "close": Decimal("101.5"),
        "volume": 3_000_000_000,
        "turnover": Decimal("123456789012.3456"),
        "source_id": "test_src",
        "source_record_id": "r1",
        "retrieved_at": datetime(2024, 6, 1, 12, 0, tzinfo=UTC),
        "source_as_of": None,
        "currency": Currency.INR,
        "adjustment_basis": AdjustmentBasis.UNADJUSTED,
        "schema_version": "1",
    }
    values.update(overrides)
    return DailyBar.model_validate(values)


def _payload(content: bytes = b"abc") -> RawPayload:
    return RawPayload(kind="daily_bars", format_id="f", content=content, file_extension="csv")


def test_raw_objects_are_content_addressed_and_write_once(lake: DataLake, tmp_path: Path) -> None:
    checksum, path = lake.store_raw("test_src", _payload())
    again = lake.store_raw("test_src", _payload())

    assert checksum == sha256_bytes(b"abc")
    assert path == f"raw/test_src/daily_bars/{checksum}.csv"
    assert again == (checksum, path)
    assert lake.read_raw(path, checksum) == b"abc"
    assert lake.store_raw("test_src", _payload(b"abd"))[1] != path


def test_modified_raw_object_is_detected(lake: DataLake, tmp_path: Path) -> None:
    checksum, path = lake.store_raw("test_src", _payload())
    stored = tmp_path / "lake" / path
    stored.chmod(0o644)
    stored.write_bytes(b"tampered")

    with pytest.raises(LakeIntegrityError, match="does not match"):
        lake.read_raw(path, checksum)
    with pytest.raises(LakeIntegrityError, match="corrupt"):
        lake.store_raw("test_src", _payload())


def test_paths_cannot_escape_the_lake(lake: DataLake) -> None:
    with pytest.raises(LakeIntegrityError, match="escapes"):
        lake.read_raw("../outside.txt", "0" * 64)


def test_content_checksum_ignores_decimal_formatting_but_not_values() -> None:
    base = content_sha256([_bar()])

    assert content_sha256([_bar(close=Decimal("101.500000"))]) == base
    assert content_sha256([_bar(close=Decimal("101.500001"))]) != base
    assert content_sha256([_bar(turnover=None)]) != base
    assert content_sha256([_bar(volume=3_000_000_001)]) != base


def test_quarantine_report_round_trips(lake: DataLake) -> None:
    record = QuarantinedRecord(
        source_record_id="r9",
        provider_instrument_id="T1",
        reasons=("close: not a number",),
        raw_fields={"close": "abc", "turnover": None},
    )

    path = lake.write_normalized("test_src", "run-1", [_bar()], [record])

    assert lake.read_quarantine_report(path) == [record]
