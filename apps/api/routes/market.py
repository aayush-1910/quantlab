from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import Connection

from apps.api.dependencies import DbConnection, Lake
from apps.api.errors import ApiError
from quantlab.data import analytics
from quantlab.data.query import SnapshotLookupError, get_daily_bars, resolve_snapshot
from quantlab.data.schemas import (
    AdjustmentBasis,
    Currency,
    DataClassification,
    Instrument,
    SnapshotManifest,
)
from quantlab.data.storage import catalog
from quantlab.data.storage.lake import LakeIntegrityError

router = APIRouter(tags=["market"])

DatasetId = Annotated[
    str | None, Query(description="Use the latest published snapshot of this dataset")
]
SnapshotId = Annotated[str | None, Query(description="Use exactly this snapshot")]


class SnapshotContext(BaseModel):
    """Provenance every market response carries, so no number is shown without its source.

    `data_as_of` is when the source data was retrieved. This is end-of-day data, not
    real-time.
    """

    snapshot_id: str
    dataset_id: str
    source_id: str
    data_classification: DataClassification
    adjustment_basis: AdjustmentBasis
    data_as_of: datetime
    first_trading_date: date | None
    last_trading_date: date | None
    quality_warnings: list[str]


class InstrumentLabel(BaseModel):
    """Display identity as of a stated date. Null when no symbol period covers that date."""

    instrument_id: str
    symbol: str | None
    name: str | None
    symbol_as_of: date


class Bar(BaseModel):
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    turnover: Decimal | None


class Gap(BaseModel):
    start: date
    end: date
    missing_weekdays: int


class BarsResponse(BaseModel):
    """Daily bars for one instrument from one snapshot.

    Prices and turnover are decimal strings in `currency`; volume is a share count.
    `gaps` lists runs of weekdays with no bar between the returned bars. They include
    exchange holidays, because no trading calendar is integrated.
    """

    instrument_id: str
    frequency: Literal["1d"]
    currency: Currency
    adjustment_basis: AdjustmentBasis
    snapshot_id: str
    dataset_id: str
    source_id: str
    data_classification: DataClassification
    data_as_of: datetime
    requested_start: date | None
    requested_end: date | None
    count: int
    bars: list[Bar]
    gaps: list[Gap]
    quality_warnings: list[str]


class CoverageRow(BaseModel):
    instrument: InstrumentLabel
    first_trading_date: date
    last_trading_date: date
    bar_count: int
    missing_weekdays: int
    days_behind_dataset: int


class CoverageResponse(BaseModel):
    """Which instruments a snapshot holds and how complete each one is."""

    snapshot: SnapshotContext
    instruments: list[CoverageRow]


class ComparisonPoint(BaseModel):
    trading_date: date
    base_index: Decimal
    comparison_index: Decimal


class ComparisonResponse(BaseModel):
    """Two close series rebased to 100 on their first common session.

    Price-only, on the snapshot's adjustment basis. Only sessions both instruments have
    are returned; the `*_only_sessions` counts say how many were left out.
    """

    snapshot: SnapshotContext
    base: InstrumentLabel
    comparison: InstrumentLabel
    base_date: date | None
    base_only_sessions: int
    comparison_only_sessions: int
    points: list[ComparisonPoint]


class ScreenerRow(BaseModel):
    instrument: InstrumentLabel
    bar_date: date
    is_stale: bool
    sessions_available: int
    close: Decimal
    volume: int
    return_1d: Decimal | None
    return_5d: Decimal | None
    return_20d: Decimal | None
    avg_volume_20d: Decimal | None


class ScreenerResponse(BaseModel):
    """Instruments in one snapshot, measured as of `reference_date`.

    Returns are price-only ratios over the instrument's own sessions (0.05 = 5%), on the
    snapshot's adjustment basis. A metric without enough history is null, and a null
    metric never passes a filter on that metric. `universe` says what was screened: every
    instrument with a bar on or before the reference date, not an index membership.
    """

    snapshot: SnapshotContext
    currency: Currency
    requested_as_of: date | None
    reference_date: date | None
    universe: Literal["ALL_INSTRUMENTS_IN_SNAPSHOT"]
    universe_count: int
    matched_count: int
    rows: list[ScreenerRow]


SortKey = Literal[
    "symbol", "close", "volume", "return_1d", "return_5d", "return_20d", "avg_volume_20d"
]


def _context(manifest: SnapshotManifest) -> SnapshotContext:
    return SnapshotContext(
        snapshot_id=manifest.snapshot_id,
        dataset_id=manifest.dataset_id,
        source_id=manifest.source_id,
        data_classification=manifest.data_classification,
        adjustment_basis=manifest.adjustment_basis,
        data_as_of=manifest.extracted_at,
        first_trading_date=manifest.first_trading_date,
        last_trading_date=manifest.last_trading_date,
        quality_warnings=list(manifest.quality_warnings),
    )


def _label(instrument_id: str, instrument: Instrument | None, as_of: date) -> InstrumentLabel:
    mapping = instrument.symbol_as_of(as_of) if instrument else None
    return InstrumentLabel(
        instrument_id=instrument_id,
        symbol=mapping.symbol if mapping else None,
        name=mapping.name if mapping else None,
        symbol_as_of=as_of,
    )


def _resolve(conn: Connection, snapshot_id: str | None, dataset_id: str | None) -> SnapshotManifest:
    try:
        return resolve_snapshot(conn, snapshot_id, dataset_id)
    except SnapshotLookupError as exc:
        status = 422 if snapshot_id is None and dataset_id is None else 404
        raise ApiError(status, "snapshot_not_resolved", str(exc)) from exc


def _require_instrument(conn: Connection, instrument_id: str) -> Instrument:
    instrument = catalog.get_instrument(conn, instrument_id)
    if instrument is None:
        raise ApiError(404, "instrument_not_found", f"Instrument '{instrument_id}' does not exist.")
    return instrument


def _check_range(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and end < start:
        raise ApiError(422, "invalid_date_range", "end must not be before start.")


@router.get("/market/bars")
def get_bars(
    conn: DbConnection,
    lake: Lake,
    instrument_id: str,
    dataset_id: DatasetId = None,
    snapshot_id: SnapshotId = None,
    start: Annotated[date | None, Query(description="Inclusive")] = None,
    end: Annotated[date | None, Query(description="Inclusive")] = None,
) -> BarsResponse:
    _check_range(start, end)
    _require_instrument(conn, instrument_id)
    manifest = _resolve(conn, snapshot_id, dataset_id)
    try:
        bars = get_daily_bars(lake, manifest, instrument_id, start, end)
    except LakeIntegrityError as exc:
        raise ApiError(500, "snapshot_data_unavailable", str(exc)) from exc
    gaps = analytics.weekday_gap_ranges([bar.trading_date for bar in bars])
    return BarsResponse(
        instrument_id=instrument_id,
        frequency="1d",
        currency=bars[0].currency if bars else Currency.INR,
        adjustment_basis=manifest.adjustment_basis,
        snapshot_id=manifest.snapshot_id,
        dataset_id=manifest.dataset_id,
        source_id=manifest.source_id,
        data_classification=manifest.data_classification,
        data_as_of=manifest.extracted_at,
        requested_start=start,
        requested_end=end,
        count=len(bars),
        bars=[Bar.model_validate(bar, from_attributes=True) for bar in bars],
        gaps=[Gap.model_validate(gap, from_attributes=True) for gap in gaps],
        quality_warnings=list(manifest.quality_warnings),
    )


@router.get("/market/coverage")
def get_coverage(
    conn: DbConnection, lake: Lake, dataset_id: DatasetId = None, snapshot_id: SnapshotId = None
) -> CoverageResponse:
    manifest = _resolve(conn, snapshot_id, dataset_id)
    try:
        coverage = analytics.snapshot_coverage(lake, manifest)
    except LakeIntegrityError as exc:
        raise ApiError(500, "snapshot_data_unavailable", str(exc)) from exc
    instruments = catalog.get_instruments(conn, [row.instrument_id for row in coverage])
    rows = [
        CoverageRow(
            instrument=_label(
                row.instrument_id, instruments.get(row.instrument_id), row.last_trading_date
            ),
            first_trading_date=row.first_trading_date,
            last_trading_date=row.last_trading_date,
            bar_count=row.bar_count,
            missing_weekdays=row.missing_weekdays,
            days_behind_dataset=row.days_behind_dataset,
        )
        for row in coverage
    ]
    rows.sort(key=lambda row: (row.instrument.symbol or "", row.instrument.instrument_id))
    return CoverageResponse(snapshot=_context(manifest), instruments=rows)


@router.get("/market/compare")
def get_comparison(
    conn: DbConnection,
    lake: Lake,
    instrument_id: str,
    comparison_instrument_id: str,
    dataset_id: DatasetId = None,
    snapshot_id: SnapshotId = None,
    start: Annotated[date | None, Query(description="Inclusive")] = None,
    end: Annotated[date | None, Query(description="Inclusive")] = None,
) -> ComparisonResponse:
    _check_range(start, end)
    if instrument_id == comparison_instrument_id:
        raise ApiError(422, "invalid_comparison", "Choose two different instruments.")
    base = _require_instrument(conn, instrument_id)
    other = _require_instrument(conn, comparison_instrument_id)
    manifest = _resolve(conn, snapshot_id, dataset_id)
    try:
        base_bars = get_daily_bars(lake, manifest, instrument_id, start, end)
        other_bars = get_daily_bars(lake, manifest, comparison_instrument_id, start, end)
    except LakeIntegrityError as exc:
        raise ApiError(500, "snapshot_data_unavailable", str(exc)) from exc
    result = analytics.rebased_comparison(
        [(bar.trading_date, bar.close) for bar in base_bars],
        [(bar.trading_date, bar.close) for bar in other_bars],
    )
    label_date = (
        result.points[-1].trading_date
        if result.points
        else (manifest.last_trading_date or manifest.extracted_at.date())
    )
    return ComparisonResponse(
        snapshot=_context(manifest),
        base=_label(instrument_id, base, label_date),
        comparison=_label(comparison_instrument_id, other, label_date),
        base_date=result.base_date,
        base_only_sessions=result.base_only_sessions,
        comparison_only_sessions=result.comparison_only_sessions,
        points=[ComparisonPoint.model_validate(p, from_attributes=True) for p in result.points],
    )


def _passes(value: Decimal | None, minimum: Decimal | None, maximum: Decimal | None) -> bool:
    if minimum is None and maximum is None:
        return True
    if value is None:
        return False
    return (minimum is None or value >= minimum) and (maximum is None or value <= maximum)


@router.get("/market/screener")
def get_screener(
    conn: DbConnection,
    lake: Lake,
    dataset_id: DatasetId = None,
    snapshot_id: SnapshotId = None,
    as_of: Annotated[date | None, Query(description="Use only bars on or before this date")] = None,
    min_close: Annotated[Decimal | None, Query(ge=0)] = None,
    max_close: Annotated[Decimal | None, Query(ge=0)] = None,
    min_avg_volume_20d: Annotated[Decimal | None, Query(ge=0)] = None,
    min_return_20d: Annotated[Decimal | None, Query(description="Ratio, e.g. 0.05")] = None,
    max_return_20d: Annotated[Decimal | None, Query(description="Ratio, e.g. 0.05")] = None,
    include_stale: Annotated[
        bool, Query(description="Include instruments with no bar on the reference date")
    ] = True,
    sort: SortKey = "symbol",
    order: Literal["asc", "desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> ScreenerResponse:
    manifest = _resolve(conn, snapshot_id, dataset_id)
    try:
        result = analytics.screen_snapshot(lake, manifest, as_of)
    except LakeIntegrityError as exc:
        raise ApiError(500, "snapshot_data_unavailable", str(exc)) from exc

    matched = [
        row
        for row in result.rows
        if _passes(row.close, min_close, max_close)
        and _passes(row.avg_volume_20d, min_avg_volume_20d, None)
        and _passes(row.return_20d, min_return_20d, max_return_20d)
        and (include_stale or not row.is_stale)
    ]
    instruments = catalog.get_instruments(conn, [row.instrument_id for row in matched])
    rows = [
        ScreenerRow(
            instrument=_label(row.instrument_id, instruments.get(row.instrument_id), row.bar_date),
            bar_date=row.bar_date,
            is_stale=row.is_stale,
            sessions_available=row.sessions_available,
            close=row.close,
            volume=row.volume,
            return_1d=row.return_1d,
            return_5d=row.return_5d,
            return_20d=row.return_20d,
            avg_volume_20d=row.avg_volume_20d,
        )
        for row in matched
    ]

    def _identity(row: ScreenerRow) -> tuple[str, str]:
        return (row.instrument.symbol or "", row.instrument.instrument_id)

    # Nulls always sort last; ties break on symbol so the order is deterministic.
    rows.sort(key=_identity)
    if sort != "symbol":
        present = [row for row in rows if getattr(row, sort) is not None]
        absent = [row for row in rows if getattr(row, sort) is None]
        present.sort(key=lambda row: getattr(row, sort), reverse=order == "desc")
        rows = present + absent
    elif order == "desc":
        rows.reverse()

    return ScreenerResponse(
        snapshot=_context(manifest),
        currency=Currency.INR,
        requested_as_of=as_of,
        reference_date=result.reference_date,
        universe="ALL_INSTRUMENTS_IN_SNAPSHOT",
        universe_count=len(result.rows),
        matched_count=len(rows),
        rows=rows[:limit],
    )
