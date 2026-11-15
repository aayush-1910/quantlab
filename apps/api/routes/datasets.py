"""Dataset provenance: snapshots, manifests, quarantine reports and ingestion runs.

Not in the spec's initial route list (section 11); added so Phase 1's exit criterion
"source and retrieval provenance can be inspected" holds over HTTP. See ADR 0004.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from apps.api.dependencies import DbConnection, Lake
from apps.api.errors import ApiError
from quantlab.data.schemas import QuarantinedRecord, SnapshotManifest
from quantlab.data.storage import catalog
from quantlab.data.storage.lake import LakeIntegrityError

router = APIRouter(tags=["datasets"])


class SnapshotList(BaseModel):
    snapshots: list[SnapshotManifest]


class QuarantineReport(BaseModel):
    total: int
    limit: int
    offset: int
    records: list[QuarantinedRecord]


class IngestionRunView(BaseModel):
    run_id: str
    source_id: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    snapshot_id: str | None
    record_count: int | None
    quarantined_count: int | None
    error: str | None


class IngestionRunList(BaseModel):
    runs: list[IngestionRunView]


def _page(records: list[QuarantinedRecord], limit: int, offset: int) -> QuarantineReport:
    return QuarantineReport(
        total=len(records), limit=limit, offset=offset, records=records[offset : offset + limit]
    )


@router.get("/datasets/snapshots")
def list_snapshots(conn: DbConnection, dataset_id: str | None = None) -> SnapshotList:
    return SnapshotList(snapshots=catalog.list_snapshots(conn, dataset_id))


@router.get("/datasets/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: str, conn: DbConnection) -> SnapshotManifest:
    manifest = catalog.get_snapshot(conn, snapshot_id)
    if manifest is None:
        raise ApiError(404, "snapshot_not_found", f"Snapshot '{snapshot_id}' does not exist.")
    return manifest


@router.get("/datasets/snapshots/{snapshot_id}/quarantine")
def get_snapshot_quarantine(
    snapshot_id: str,
    conn: DbConnection,
    lake: Lake,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QuarantineReport:
    manifest = get_snapshot(snapshot_id, conn)
    try:
        return _page(lake.read_snapshot_quarantine(manifest), limit, offset)
    except LakeIntegrityError as exc:
        raise ApiError(500, "quarantine_report_unavailable", str(exc)) from exc


@router.get("/datasets/ingestion-runs")
def list_ingestion_runs(
    conn: DbConnection, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> IngestionRunList:
    """Most recent first. Failed runs stay listed with their error."""
    runs = [
        IngestionRunView.model_validate(run, from_attributes=True)
        for run in catalog.list_runs(conn, limit)
    ]
    return IngestionRunList(runs=runs)


@router.get("/datasets/ingestion-runs/{run_id}/quarantine")
def get_run_quarantine(
    run_id: str,
    conn: DbConnection,
    lake: Lake,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> QuarantineReport:
    """Quarantine report of a run, including runs that failed before publishing."""
    run = catalog.get_run(conn, run_id)
    if run is None:
        raise ApiError(404, "ingestion_run_not_found", f"Ingestion run '{run_id}' does not exist.")
    if run.quarantine_path is None:
        raise ApiError(
            404, "quarantine_report_not_found", "This run did not reach validation; no report."
        )
    try:
        return _page(lake.read_quarantine_report(run.quarantine_path), limit, offset)
    except LakeIntegrityError as exc:
        raise ApiError(500, "quarantine_report_unavailable", str(exc)) from exc
