"""Provider boundary (spec section 5.1).

A provider does two separate things:

1. `fetch_*` returns the source payload as bytes, exactly as received. Ingestion stores
   those bytes immutably before anything else happens.
2. A `PayloadParser`, looked up by the payload's `format_id`, turns stored bytes into
   provider-neutral records. Parsing always runs against the stored raw bytes, so a
   snapshot can be rebuilt later without contacting the provider again.

Parsers do not validate market data. Bar fields stay as strings until validation, so a
malformed row is quarantined with its original content instead of failing the parse.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from quantlab.data.schemas import (
    AdjustmentBasis,
    Currency,
    DataClassification,
    Exchange,
    InstrumentType,
)

KIND_INSTRUMENTS = "instruments"
KIND_DAILY_BARS = "daily_bars"

# Field names a parser must use for bar records. `turnover` may be absent or None.
BAR_FIELDS = ("trading_date", "open", "high", "low", "close", "volume", "turnover")


class ProviderDataError(Exception):
    """The payload as a whole is unusable (wrong structure, missing columns)."""


@dataclass(frozen=True)
class ProviderInfo:
    source_id: str
    provider_name: str
    licence_reference: str
    data_classification: DataClassification
    source_dataset_version: str
    adjustment_basis: AdjustmentBasis
    adjustment_methodology: str


@dataclass(frozen=True)
class RawPayload:
    kind: str
    format_id: str
    content: bytes
    file_extension: str
    source_as_of: datetime | None = None


@dataclass(frozen=True)
class ProviderSymbol:
    symbol: str
    name: str | None
    isin: str | None
    valid_from: date
    valid_to: date | None


@dataclass(frozen=True)
class ProviderInstrument:
    provider_instrument_id: str
    exchange: Exchange
    instrument_type: InstrumentType
    currency: Currency
    symbols: tuple[ProviderSymbol, ...]


@dataclass(frozen=True)
class RawBarRecord:
    source_record_id: str
    provider_instrument_id: str | None
    fields: dict[str, str | None]


class PayloadParser(Protocol):
    def parse_instruments(self, content: bytes) -> list[ProviderInstrument]: ...

    def parse_daily_bars(self, content: bytes) -> list[RawBarRecord]: ...


class MarketDataProvider(Protocol):
    @property
    def info(self) -> ProviderInfo: ...

    def fetch_instruments(self) -> RawPayload: ...

    def fetch_daily_bars(self) -> RawPayload: ...
