"""User-supplied CSV provider.

Reads two files from a directory the user controls:

`instruments.csv` - one row per symbol period of an instrument:
    provider_instrument_id, exchange, instrument_type, symbol, name, isin, valid_from, valid_to
    (`name`, `isin` and `valid_to` may be empty; dates are ISO `YYYY-MM-DD`, inclusive)

`daily_bars.csv` - one row per instrument per trading date:
    provider_instrument_id, trading_date, open, high, low, close, volume[, turnover]

Prices are assumed to be in INR. The user states the licence reference, dataset version
and adjustment basis; QUANTLAB records those statements, it cannot verify them.
"""

import csv
import io
from datetime import date
from pathlib import Path

from quantlab.data.providers.base import (
    KIND_DAILY_BARS,
    KIND_INSTRUMENTS,
    ProviderDataError,
    ProviderInfo,
    ProviderInstrument,
    ProviderSymbol,
    RawBarRecord,
    RawPayload,
)
from quantlab.data.schemas import (
    AdjustmentBasis,
    Currency,
    DataClassification,
    Exchange,
    InstrumentType,
)

CSV_FORMAT_ID = "quantlab-csv-v1"
INSTRUMENTS_FILE = "instruments.csv"
DAILY_BARS_FILE = "daily_bars.csv"

_INSTRUMENT_COLUMNS = (
    "provider_instrument_id",
    "exchange",
    "instrument_type",
    "symbol",
    "name",
    "isin",
    "valid_from",
    "valid_to",
)
_BAR_REQUIRED_COLUMNS = (
    "provider_instrument_id",
    "trading_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
)


class CsvFileProvider:
    def __init__(
        self,
        directory: Path,
        *,
        source_id: str,
        licence_reference: str,
        source_dataset_version: str,
        adjustment_basis: AdjustmentBasis,
        adjustment_methodology: str = "As declared by the supplier of the files; not verified.",
        data_classification: DataClassification = DataClassification.USER_SUPPLIED,
    ) -> None:
        if data_classification is DataClassification.SYNTHETIC_TEST_DATA:
            raise ValueError("user-supplied files cannot be classified as synthetic test data")
        if not licence_reference.strip():
            raise ValueError("licence_reference is required: state the right to use this data")
        self._directory = directory
        self._info = ProviderInfo(
            source_id=source_id,
            provider_name="User-supplied CSV files",
            licence_reference=licence_reference.strip(),
            data_classification=data_classification,
            source_dataset_version=source_dataset_version,
            adjustment_basis=adjustment_basis,
            adjustment_methodology=adjustment_methodology,
        )

    @property
    def info(self) -> ProviderInfo:
        return self._info

    def _read(self, name: str, kind: str) -> RawPayload:
        path = self._directory / name
        if not path.is_file():
            raise ProviderDataError(f"required file not found: {path}")
        return RawPayload(
            kind=kind, format_id=CSV_FORMAT_ID, content=path.read_bytes(), file_extension="csv"
        )

    def fetch_instruments(self) -> RawPayload:
        return self._read(INSTRUMENTS_FILE, KIND_INSTRUMENTS)

    def fetch_daily_bars(self) -> RawPayload:
        return self._read(DAILY_BARS_FILE, KIND_DAILY_BARS)


def _reader(content: bytes, required: tuple[str, ...], what: str) -> csv.DictReader[str]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProviderDataError(f"{what} is not UTF-8 text: {exc}") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    header = [name.strip() for name in (reader.fieldnames or [])]
    missing = [column for column in required if column not in header]
    if missing:
        raise ProviderDataError(f"{what} is missing columns: {', '.join(missing)}")
    if len(set(header)) != len(header):
        raise ProviderDataError(f"{what} has duplicate column names")
    reader.fieldnames = header
    return reader


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class CsvParser:
    def parse_instruments(self, content: bytes) -> list[ProviderInstrument]:
        what = INSTRUMENTS_FILE
        grouped: dict[str, tuple[Exchange, InstrumentType, list[ProviderSymbol]]] = {}
        try:
            for row in _reader(content, _INSTRUMENT_COLUMNS, what):
                cells = {key: _clean(value) for key, value in row.items() if key is not None}
                line = f"{what} row { ({k: v for k, v in cells.items() if v})!r}"
                pid, symbol, valid_from = (
                    cells["provider_instrument_id"],
                    cells["symbol"],
                    cells["valid_from"],
                )
                if pid is None or symbol is None or valid_from is None:
                    raise ProviderDataError(
                        f"{line}: provider_instrument_id, symbol and valid_from are required"
                    )
                try:
                    exchange = Exchange(cells["exchange"] or "")
                    instrument_type = InstrumentType(cells["instrument_type"] or "")
                    mapping = ProviderSymbol(
                        symbol=symbol,
                        name=cells["name"],
                        isin=cells["isin"],
                        valid_from=date.fromisoformat(valid_from),
                        valid_to=(
                            date.fromisoformat(cells["valid_to"]) if cells["valid_to"] else None
                        ),
                    )
                except ValueError as exc:
                    raise ProviderDataError(f"{line}: {exc}") from exc
                existing = grouped.setdefault(pid, (exchange, instrument_type, []))
                if existing[:2] != (exchange, instrument_type):
                    raise ProviderDataError(
                        f"{line}: {pid} has conflicting exchange or instrument_type"
                    )
                existing[2].append(mapping)
        except csv.Error as exc:
            raise ProviderDataError(f"{what} is not valid CSV: {exc}") from exc
        return [
            ProviderInstrument(
                provider_instrument_id=pid,
                exchange=exchange,
                instrument_type=instrument_type,
                currency=Currency.INR,
                symbols=tuple(sorted(symbols, key=lambda s: s.valid_from)),
            )
            for pid, (exchange, instrument_type, symbols) in grouped.items()
        ]

    def parse_daily_bars(self, content: bytes) -> list[RawBarRecord]:
        what = DAILY_BARS_FILE
        reader = _reader(content, _BAR_REQUIRED_COLUMNS, what)
        records = []
        try:
            for row in reader:
                fields = {key: _clean(value) for key, value in row.items() if key is not None}
                if None in row:  # more cells than header columns
                    fields["_extra_cells"] = ",".join(row[None])
                provider_instrument_id = fields.pop("provider_instrument_id", None)
                records.append(
                    RawBarRecord(
                        source_record_id=f"{what}:line {reader.line_num}",
                        provider_instrument_id=provider_instrument_id,
                        fields=fields,
                    )
                )
        except csv.Error as exc:
            raise ProviderDataError(f"{what} is not valid CSV: {exc}") from exc
        return records
