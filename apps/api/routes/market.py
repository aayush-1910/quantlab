from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from apps.api.dependencies import DbConnection, Lake
from apps.api.errors import ApiError
from quantlab.data.query import SnapshotLookupError, get_daily_bars, resolve_snapshot
from quantlab.data.schemas import AdjustmentBasis, Currency, DataClassification
from quantlab.data.storage import catalog
from quantlab.data.storage.lake import LakeIntegrityError

router = APIRouter(tags=["market"])


class Bar(BaseModel):
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    turnover: Decimal | None


class BarsResponse(BaseModel):
    """Daily bars for one instrument from one snapshot, with the provenance to read them.

    Prices and turnover are decimal strings in `currency`; volume is a share count.
    `data_as_of` is when the source data was retrieved. This is end-of-day data, not
    real-time.
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
    quality_warnings: list[str]


@router.get("/market/bars")
def get_bars(
    conn: DbConnection,
    lake: Lake,
    instrument_id: str,
    dataset_id: Annotated[
        str | None, Query(description="Use the latest published snapshot of this dataset")
    ] = None,
    snapshot_id: Annotated[str | None, Query(description="Use exactly this snapshot")] = None,
    start: Annotated[date | None, Query(description="Inclusive")] = None,
    end: Annotated[date | None, Query(description="Inclusive")] = None,
) -> BarsResponse:
    if start is not None and end is not None and end < start:
        raise ApiError(422, "invalid_date_range", "end must not be before start.")
    if catalog.get_instrument(conn, instrument_id) is None:
        raise ApiError(404, "instrument_not_found", f"Instrument '{instrument_id}' does not exist.")
    try:
        manifest = resolve_snapshot(conn, snapshot_id, dataset_id)
    except SnapshotLookupError as exc:
        status = 422 if snapshot_id is None and dataset_id is None else 404
        raise ApiError(status, "snapshot_not_resolved", str(exc)) from exc
    try:
        bars = get_daily_bars(lake, manifest, instrument_id, start, end)
    except LakeIntegrityError as exc:
        raise ApiError(500, "snapshot_data_unavailable", str(exc)) from exc
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
        quality_warnings=list(manifest.quality_warnings),
    )
