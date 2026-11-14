"""Read-side service for published daily bars."""

from datetime import date

from sqlalchemy import Connection

from quantlab.data.schemas import DailyBar, SnapshotManifest
from quantlab.data.storage import catalog
from quantlab.data.storage.lake import DataLake


class SnapshotLookupError(Exception):
    pass


def resolve_snapshot(
    conn: Connection, snapshot_id: str | None, dataset_id: str | None
) -> SnapshotManifest:
    """An explicit snapshot wins; otherwise the latest published version of the dataset.

    There is deliberately no global default: datasets from different sources (and
    synthetic test data in particular) are never merged or picked implicitly.
    """
    if snapshot_id is not None:
        manifest = catalog.get_snapshot(conn, snapshot_id)
        if manifest is None:
            raise SnapshotLookupError(f"snapshot '{snapshot_id}' does not exist")
        if dataset_id is not None and manifest.dataset_id != dataset_id:
            raise SnapshotLookupError(
                f"snapshot '{snapshot_id}' does not belong to dataset '{dataset_id}'"
            )
        return manifest
    if dataset_id is None:
        raise SnapshotLookupError("either snapshot_id or dataset_id is required")
    manifest = catalog.latest_snapshot(conn, dataset_id)
    if manifest is None:
        raise SnapshotLookupError(f"dataset '{dataset_id}' has no published snapshot")
    return manifest


def get_daily_bars(
    lake: DataLake,
    manifest: SnapshotManifest,
    instrument_id: str,
    start: date | None = None,
    end: date | None = None,
) -> list[DailyBar]:
    return lake.read_bars(manifest, instrument_id=instrument_id, start=start, end=end)
