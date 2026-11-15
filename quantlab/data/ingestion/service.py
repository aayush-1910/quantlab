"""Daily-bar ingestion, verification and reproduction.

Flow of `ingest_daily_bars`:

1. Fetch the provider payloads and store the bytes in the raw layer (write-once).
2. Compute the input fingerprint: source, declared dataset attributes, schema and
   normalizer versions, and the raw checksums. If a snapshot with that fingerprint is
   already published, return it. This is what makes re-ingestion idempotent.
3. Record an ingestion run, then in one database transaction: parse the stored raw bytes,
   register instruments, validate, write the normalized layer, stage the snapshot files,
   take the dataset publish lock, assign the next version, move the files into place and
   insert the snapshot row.
4. If anything in step 3 fails, the transaction rolls back, the run is marked FAILED with
   the error, and no snapshot row exists. Readers only see snapshots that have a row, so a
   failed ingestion never publishes a partial dataset.
"""

import hashlib
import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import Connection, Engine

from quantlab.data.providers import get_parser
from quantlab.data.providers.base import (
    KIND_DAILY_BARS,
    KIND_INSTRUMENTS,
    MarketDataProvider,
    ProviderInfo,
    ProviderInstrument,
    RawPayload,
)
from quantlab.data.schemas import (
    DAILY_BAR_SCHEMA_VERSION,
    SOURCE_ID_PATTERN,
    Instrument,
    RawObjectRef,
    SnapshotManifest,
)
from quantlab.data.storage import catalog
from quantlab.data.storage.lake import DataLake, content_sha256
from quantlab.data.validation.bars import NORMALIZER_VERSION, ValidationResult, validate_daily_bars

ACTOR = "system:ingestion"
_MAX_ERROR_LENGTH = 2000


class IngestionFailedError(Exception):
    def __init__(self, run_id: str, message: str) -> None:
        super().__init__(f"ingestion run {run_id} failed: {message}")
        self.run_id = run_id


class SnapshotNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class IngestionResult:
    manifest: SnapshotManifest
    run_id: str | None
    # True when the same input had already been published and nothing new was written.
    already_ingested: bool


@dataclass(frozen=True)
class ReproductionReport:
    snapshot_id: str
    matches: bool
    recorded_content_sha256: str
    stored_content_sha256: str | None
    rebuilt_content_sha256: str | None
    problems: tuple[str, ...] = field(default=())


def dataset_id_for(source_id: str) -> str:
    return f"{source_id}.daily_bars"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _fingerprint(info: ProviderInfo, raw_objects: list[RawObjectRef]) -> str:
    document = {
        "source_id": info.source_id,
        "data_classification": info.data_classification.value,
        "licence_reference": info.licence_reference,
        "source_dataset_version": info.source_dataset_version,
        "adjustment_basis": info.adjustment_basis.value,
        "adjustment_methodology": info.adjustment_methodology,
        "schema_version": DAILY_BAR_SCHEMA_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "raw": sorted((ref.kind, ref.format_id, ref.sha256) for ref in raw_objects),
    }
    return hashlib.sha256(json.dumps(document, sort_keys=True).encode("utf-8")).hexdigest()


def _raw_ref(raw_objects: tuple[RawObjectRef, ...] | list[RawObjectRef], kind: str) -> RawObjectRef:
    matches = [ref for ref in raw_objects if ref.kind == kind]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one raw object of kind '{kind}', found {len(matches)}")
    return matches[0]


def _build(
    info: ProviderInfo,
    raw_objects: tuple[RawObjectRef, ...] | list[RawObjectRef],
    lake: DataLake,
    resolve_instruments: Callable[[list[ProviderInstrument]], dict[str, Instrument]],
) -> ValidationResult:
    """Parse and validate from the stored raw bytes. Used by ingestion and reproduction."""
    instruments_ref = _raw_ref(raw_objects, KIND_INSTRUMENTS)
    bars_ref = _raw_ref(raw_objects, KIND_DAILY_BARS)
    provider_instruments = get_parser(instruments_ref.format_id).parse_instruments(
        lake.read_raw(instruments_ref.path, instruments_ref.sha256)
    )
    records = get_parser(bars_ref.format_id).parse_daily_bars(
        lake.read_raw(bars_ref.path, bars_ref.sha256)
    )
    return validate_daily_bars(
        records,
        resolve_instruments(provider_instruments),
        info,
        retrieved_at=bars_ref.retrieved_at,
        source_as_of=bars_ref.source_as_of,
    )


def _store_raw(
    conn: Connection,
    lake: DataLake,
    info: ProviderInfo,
    payload: RawPayload,
    retrieved_at: datetime,
) -> RawObjectRef:
    checksum, path = lake.store_raw(info.source_id, payload)
    first_retrieved_at = catalog.record_raw_object(
        conn,
        source_id=info.source_id,
        kind=payload.kind,
        sha256=checksum,
        format_id=payload.format_id,
        byte_size=len(payload.content),
        path=path,
        retrieved_at=retrieved_at,
        source_as_of=payload.source_as_of,
    )
    return RawObjectRef(
        kind=payload.kind,
        format_id=payload.format_id,
        sha256=checksum,
        byte_size=len(payload.content),
        path=path,
        retrieved_at=first_retrieved_at,
        source_as_of=payload.source_as_of,
    )


def ingest_daily_bars(
    provider: MarketDataProvider,
    engine: Engine,
    lake: DataLake,
    *,
    now: Callable[[], datetime] = _utc_now,
) -> IngestionResult:
    info = provider.info
    if not re.fullmatch(SOURCE_ID_PATTERN, info.source_id):
        raise ValueError(
            f"invalid source_id '{info.source_id}': use lowercase letters, digits and "
            "underscores, starting with a letter"
        )
    payloads = [provider.fetch_instruments(), provider.fetch_daily_bars()]
    if [payload.kind for payload in payloads] != [KIND_INSTRUMENTS, KIND_DAILY_BARS]:
        raise ValueError("provider returned payloads of an unexpected kind")
    started_at = now()
    run_id = str(uuid.uuid4())

    with engine.begin() as conn:
        raw_objects = [_store_raw(conn, lake, info, payload, started_at) for payload in payloads]
        fingerprint = _fingerprint(info, raw_objects)
        existing = catalog.find_snapshot_by_fingerprint(conn, fingerprint)
        if existing is not None:
            return IngestionResult(manifest=existing, run_id=None, already_ingested=True)
        catalog.insert_run(conn, run_id, info.source_id, fingerprint, started_at)
        catalog.write_audit_event(
            conn,
            "data.ingestion.started",
            ACTOR,
            "ingestion_run",
            run_id,
            {"source_id": info.source_id, "input_fingerprint": fingerprint},
        )

    progress: dict[str, str | int | None] = {"quarantine_path": None, "quarantined_count": None}
    try:
        with engine.begin() as conn:
            manifest, already_ingested = _validate_and_publish(
                conn, lake, info, raw_objects, fingerprint, run_id, now, progress
            )
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:_MAX_ERROR_LENGTH]
        with engine.begin() as conn:
            catalog.finish_run(
                conn,
                run_id,
                "FAILED",
                finished_at=now(),
                error=message,
                quarantine_path=progress["quarantine_path"],
                quarantined_count=progress["quarantined_count"],
            )
            catalog.write_audit_event(
                conn,
                "data.ingestion.failed",
                ACTOR,
                "ingestion_run",
                run_id,
                {"source_id": info.source_id, "error": message},
            )
        raise IngestionFailedError(run_id, message) from exc
    return IngestionResult(manifest=manifest, run_id=run_id, already_ingested=already_ingested)


def _validate_and_publish(
    conn: Connection,
    lake: DataLake,
    info: ProviderInfo,
    raw_objects: list[RawObjectRef],
    fingerprint: str,
    run_id: str,
    now: Callable[[], datetime],
    progress: dict[str, str | int | None],
) -> tuple[SnapshotManifest, bool]:
    result = _build(
        info,
        raw_objects,
        lake,
        lambda provider_instruments: catalog.register_instruments(
            conn, info.source_id, provider_instruments
        ),
    )
    quarantine_path = lake.write_normalized(
        info.source_id, run_id, result.accepted, result.quarantined
    )
    progress["quarantine_path"] = quarantine_path
    progress["quarantined_count"] = len(result.quarantined)
    if not result.accepted:
        raise ValueError(
            f"no valid records: all {len(result.quarantined)} source record(s) were "
            f"quarantined (see {quarantine_path})"
        )

    dataset_id = dataset_id_for(info.source_id)
    staging, files = lake.stage_snapshot(dataset_id, run_id, result.accepted, result.quarantined)
    try:
        catalog.lock_dataset_for_publish(conn, dataset_id)
        # Another run may have published the same input while this one was validating.
        existing = catalog.find_snapshot_by_fingerprint(conn, fingerprint)
        if existing is not None:
            lake.discard_staging(staging)
            catalog.finish_run(
                conn,
                run_id,
                "SUCCEEDED",
                finished_at=now(),
                snapshot_id=existing.snapshot_id,
                record_count=existing.record_count,
                quarantined_count=existing.quarantined_count,
                quarantine_path=quarantine_path,
            )
            return existing, True

        version = catalog.next_snapshot_version(conn, dataset_id)
        dates = [bar.trading_date for bar in result.accepted]
        manifest = SnapshotManifest(
            snapshot_id=f"{dataset_id}-v{version}",
            dataset_id=dataset_id,
            version=version,
            source_id=info.source_id,
            provider_name=info.provider_name,
            licence_reference=info.licence_reference,
            data_classification=info.data_classification,
            source_dataset_version=info.source_dataset_version,
            extracted_at=_raw_ref(raw_objects, KIND_DAILY_BARS).retrieved_at,
            created_at=now(),
            first_trading_date=min(dates),
            last_trading_date=max(dates),
            instrument_ids=tuple(sorted({bar.instrument_id for bar in result.accepted})),
            record_count=len(result.accepted),
            quarantined_count=len(result.quarantined),
            schema_version=DAILY_BAR_SCHEMA_VERSION,
            normalizer_version=NORMALIZER_VERSION,
            adjustment_basis=info.adjustment_basis,
            adjustment_methodology=info.adjustment_methodology,
            input_fingerprint=fingerprint,
            content_sha256=content_sha256(result.accepted),
            files=files,
            raw_objects=tuple(raw_objects),
            weekday_gaps=result.weekday_gaps,
            quality_warnings=result.quality_warnings,
        )
        lake.promote_snapshot(staging, manifest)
        catalog.insert_snapshot(conn, manifest)
        catalog.finish_run(
            conn,
            run_id,
            "SUCCEEDED",
            finished_at=now(),
            snapshot_id=manifest.snapshot_id,
            record_count=manifest.record_count,
            quarantined_count=manifest.quarantined_count,
            quarantine_path=quarantine_path,
        )
        catalog.write_audit_event(
            conn,
            "data.ingestion.succeeded",
            ACTOR,
            "dataset_snapshot",
            manifest.snapshot_id,
            {
                "run_id": run_id,
                "source_id": info.source_id,
                "data_classification": info.data_classification.value,
                "record_count": manifest.record_count,
                "quarantined_count": manifest.quarantined_count,
                "content_sha256": manifest.content_sha256,
            },
        )
        return manifest, False
    except Exception:
        lake.discard_staging(staging)
        raise


def reproduce_snapshot(snapshot_id: str, engine: Engine, lake: DataLake) -> ReproductionReport:
    """Rebuild a snapshot from its raw objects and compare with what was published.

    Three checksums must agree: the one recorded in the manifest, the one computed from
    the stored Parquet file, and the one computed by re-running parsing and validation on
    the raw bytes. Nothing is written.
    """
    with engine.connect() as conn:
        manifest = catalog.get_snapshot(conn, snapshot_id)
        if manifest is None:
            raise SnapshotNotFoundError(snapshot_id)
        problems = lake.verify_snapshot_files(manifest)

        stored: str | None = None
        try:
            stored = content_sha256(lake.read_bars(manifest))
        except Exception as exc:
            problems.append(f"stored data unreadable: {type(exc).__name__}: {exc}")

        if manifest.normalizer_version != NORMALIZER_VERSION:
            problems.append(
                f"snapshot was built with normalizer version {manifest.normalizer_version}; "
                f"this code is version {NORMALIZER_VERSION}, so a rebuild may legitimately differ"
            )
        info = ProviderInfo(
            source_id=manifest.source_id,
            provider_name=manifest.provider_name,
            licence_reference=manifest.licence_reference,
            data_classification=manifest.data_classification,
            source_dataset_version=manifest.source_dataset_version,
            adjustment_basis=manifest.adjustment_basis,
            adjustment_methodology=manifest.adjustment_methodology,
        )
        rebuilt: str | None = None
        try:
            result = _build(
                info,
                manifest.raw_objects,
                lake,
                lambda provider_instruments: catalog.lookup_provider_instruments(
                    conn,
                    manifest.source_id,
                    [p.provider_instrument_id for p in provider_instruments],
                ),
            )
            rebuilt = content_sha256(result.accepted)
        except Exception as exc:
            problems.append(f"rebuild from raw failed: {type(exc).__name__}: {exc}")

    if stored is not None and stored != manifest.content_sha256:
        problems.append("stored data does not match the manifest content checksum")
    if rebuilt is not None and rebuilt != manifest.content_sha256:
        problems.append("rebuild from raw does not match the manifest content checksum")
    matches = (
        stored == manifest.content_sha256 and rebuilt == manifest.content_sha256 and not problems
    )
    return ReproductionReport(
        snapshot_id=snapshot_id,
        matches=matches,
        recorded_content_sha256=manifest.content_sha256,
        stored_content_sha256=stored,
        rebuilt_content_sha256=rebuilt,
        problems=tuple(problems),
    )
