import json
from datetime import date
from pathlib import Path

import pytest

from quantlab.data.providers import get_parser
from quantlab.data.providers.base import ProviderDataError
from quantlab.data.providers.csv_file import CSV_FORMAT_ID, CsvFileProvider, CsvParser
from quantlab.data.providers.synthetic import (
    SYNTHETIC_FORMAT_ID,
    SYNTHETIC_LABEL,
    SyntheticFixtureProvider,
    SyntheticParser,
)
from quantlab.data.schemas import AdjustmentBasis, DataClassification


def test_synthetic_payloads_are_deterministic_for_the_same_arguments() -> None:
    first, second = SyntheticFixtureProvider(seed=3), SyntheticFixtureProvider(seed=3)

    assert first.fetch_daily_bars().content == second.fetch_daily_bars().content
    assert first.fetch_instruments().content == second.fetch_instruments().content
    assert (
        first.fetch_daily_bars().content
        != SyntheticFixtureProvider(seed=4).fetch_daily_bars().content
    )


def test_synthetic_data_is_labelled_everywhere() -> None:
    provider = SyntheticFixtureProvider()

    assert provider.info.data_classification is DataClassification.SYNTHETIC_TEST_DATA
    assert SYNTHETIC_LABEL in provider.info.provider_name
    assert json.loads(provider.fetch_daily_bars().content)["label"] == SYNTHETIC_LABEL
    instruments = SyntheticParser().parse_instruments(provider.fetch_instruments().content)
    assert all(SYNTHETIC_LABEL in (i.symbols[0].name or "") for i in instruments)
    assert all(i.symbols[0].symbol.startswith("SYNTH") for i in instruments)


def test_synthetic_bars_cover_weekdays_only() -> None:
    provider = SyntheticFixtureProvider(date(2024, 1, 1), date(2024, 1, 14), instrument_count=2)

    records = SyntheticParser().parse_daily_bars(provider.fetch_daily_bars().content)

    assert len(records) == 2 * 10
    assert all(date.fromisoformat(r.fields["trading_date"] or "").weekday() < 5 for r in records)


def test_synthetic_parser_rejects_unlabelled_payload() -> None:
    with pytest.raises(ProviderDataError, match="label"):
        SyntheticParser().parse_daily_bars(b'{"bars": []}')


def test_parser_registry_resolves_formats_and_rejects_unknown() -> None:
    assert isinstance(get_parser(SYNTHETIC_FORMAT_ID), SyntheticParser)
    assert isinstance(get_parser(CSV_FORMAT_ID), CsvParser)
    with pytest.raises(ProviderDataError):
        get_parser("nope")


def _csv_provider(directory: Path, **overrides: object) -> CsvFileProvider:
    arguments: dict[str, object] = {
        "source_id": "test_csv",
        "licence_reference": "SYNTHETIC_TEST_DATA written by the test suite",
        "source_dataset_version": "t1",
        "adjustment_basis": AdjustmentBasis.UNADJUSTED,
    }
    arguments.update(overrides)
    return CsvFileProvider(directory, **arguments)  # type: ignore[arg-type]


def test_csv_provider_returns_file_bytes_unchanged(tmp_path: Path) -> None:
    content = (
        b"provider_instrument_id,trading_date,open,high,low,close,volume\r\n"
        b"T1,2024-01-01,1,1,1,1,1\r\n"
    )
    (tmp_path / "daily_bars.csv").write_bytes(content)

    assert _csv_provider(tmp_path).fetch_daily_bars().content == content


def test_csv_provider_requires_files_and_a_licence_reference(tmp_path: Path) -> None:
    with pytest.raises(ProviderDataError, match="not found"):
        _csv_provider(tmp_path).fetch_instruments()
    with pytest.raises(ValueError, match="licence_reference"):
        _csv_provider(tmp_path, licence_reference="  ")
    with pytest.raises(ValueError, match="synthetic"):
        _csv_provider(tmp_path, data_classification=DataClassification.SYNTHETIC_TEST_DATA)


def test_csv_instruments_group_symbol_periods_per_instrument() -> None:
    content = (
        b"provider_instrument_id,exchange,instrument_type,symbol,name,isin,valid_from,valid_to\n"
        b"T1,NSE,EQUITY,NEWNAME,New Name Ltd,,2024-06-01,\n"
        b"T1,NSE,EQUITY,OLDNAME,Old Name Ltd,,2020-01-01,2024-05-31\n"
    )

    (instrument,) = CsvParser().parse_instruments(content)

    assert [s.symbol for s in instrument.symbols] == ["OLDNAME", "NEWNAME"]
    assert instrument.symbols[0].valid_to == date(2024, 5, 31)
    assert instrument.symbols[1].valid_to is None


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"provider_instrument_id,symbol\nT1,X\n", "missing columns"),
        (
            b"provider_instrument_id,exchange,instrument_type,symbol,name,isin,valid_from,valid_to\n"
            b"T1,NYSE,EQUITY,X,,,2024-01-01,\n",
            "NYSE",
        ),
        (
            b"provider_instrument_id,exchange,instrument_type,symbol,name,isin,valid_from,valid_to\n"
            b"T1,NSE,EQUITY,X,,,01/01/2024,\n",
            "Invalid isoformat",
        ),
        (
            b"provider_instrument_id,exchange,instrument_type,symbol,name,isin,valid_from,valid_to\n"
            b"T1,NSE,EQUITY,,,,2024-01-01,\n",
            "required",
        ),
    ],
)
def test_csv_instruments_reject_malformed_files(content: bytes, message: str) -> None:
    with pytest.raises(ProviderDataError, match=message):
        CsvParser().parse_instruments(content)


def test_csv_bars_keep_bad_rows_for_validation_instead_of_failing() -> None:
    content = (
        b"provider_instrument_id,trading_date,open,high,low,close,volume\n"
        b"T1,2024-01-01,abc,1,1,1,1\n"
        b"T1,2024-01-02,1,1\n"
        b"T1,2024-01-03,1,1,1,1,1,9,9\n"
    )

    records = CsvParser().parse_daily_bars(content)

    assert [r.source_record_id for r in records] == [
        "daily_bars.csv:line 2",
        "daily_bars.csv:line 3",
        "daily_bars.csv:line 4",
    ]
    assert records[0].fields["open"] == "abc"
    assert records[1].fields["close"] is None
    assert "_extra_cells" in records[2].fields


def test_csv_bars_reject_file_without_required_columns() -> None:
    with pytest.raises(ProviderDataError, match="missing columns: close, volume"):
        CsvParser().parse_daily_bars(b"provider_instrument_id,trading_date,open,high,low\n")
