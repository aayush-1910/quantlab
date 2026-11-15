"""Ingestion against a real PostgreSQL and a temporary lake. All data is SYNTHETIC_TEST_DATA."""

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError

from conftest import BARS_CSV, INSTRUMENTS_CSV
from quantlab.data.ingestion.service import (
    IngestionFailedError,
    ingest_daily_bars,
    reproduce_snapshot,
)
from quantlab.data.providers.csv_file import CsvFileProvider
from quantlab.data.providers.synthetic import SyntheticFixtureProvider
from quantlab.data.schemas import AdjustmentBasis, DataClassification
from quantlab.data.storage import catalog
from quantlab.data.storage import tables as t
from quantlab.data.storage.lake import DataLake

WriteSource = Callable[..., Path]


def _provider(directory: Path, version: str = "delivery-1") -> CsvFileProvider:
    return CsvFileProvider(
        directory,
        source_id="test_csv",
        licence_reference="SYNTHETIC_TEST_DATA written by the test suite",
        source_dataset_version=version,
        adjustment_basis=AdjustmentBasis.UNADJUSTED,
    )


def _count(engine: Engine, table: object) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(table)).scalar_one())  # type: ignore[arg-type]


def _lake_files(lake_root: Path) -> set[str]:
    return {str(p.relative_to(lake_root)) for p in lake_root.rglob("*") if p.is_file()}


def test_ingestion_publishes_a_snapshot_with_provenance(
    db_engine: Engine, lake: DataLake, write_csv_source: WriteSource
) -> None:
    result = ingest_daily_bars(_provider(write_csv_source()), db_engine, lake)

    manifest = result.manifest
    assert not result.already_ingested
    assert manifest.snapshot_id == "test_csv.daily_bars-v1"
    assert manifest.data_classification is DataClassification.USER_SUPPLIED
    assert manifest.licence_reference.startswith("SYNTHETIC_TEST_DATA")
    assert manifest.source_dataset_version == "delivery-1"
    assert manifest.adjustment_basis is AdjustmentBasis.UNADJUSTED
    assert (manifest.record_count, manifest.quarantined_count) == (5, 0)
    assert (manifest.first_trading_date, manifest.last_trading_date) == (
        date(2024, 1, 1),
        date(2024, 1, 3),
    )
    assert len(manifest.instrument_ids) == 2
    assert {ref.kind for ref in manifest.raw_objects} == {"instruments", "daily_bars"}
    assert {f.path for f in manifest.files} == {"bars.parquet", "quarantine.jsonl"}
    assert lake.verify_snapshot_files(manifest) == []

    with db_engine.connect() as conn:
        assert catalog.get_snapshot(conn, manifest.snapshot_id) == manifest
        (run,) = catalog.list_runs(conn)
        assert (run.status, run.snapshot_id) == ("SUCCEEDED", manifest.snapshot_id)
        events = list(
            conn.execute(
                select(t.audit_events.c.event_type).order_by(t.audit_events.c.id)
            ).scalars()
        )
    assert events[0] == "data.ingestion.started"
    assert events[-1] == "data.ingestion.succeeded"
    assert events.count("data.instrument.registered") == 2


def test_stored_bars_keep_exact_decimal_values(
    db_engine: Engine, lake: DataLake, write_csv_source: WriteSource
) -> None:
    manifest = ingest_daily_bars(_provider(write_csv_source()), db_engine, lake).manifest
    with db_engine.connect() as conn:
        (instrument,) = catalog.search_instruments(conn, "TESTONE")

    bars = lake.read_bars(manifest, instrument.instrument_id, date(2024, 1, 2), date(2024, 1, 3))

    assert [bar.trading_date for bar in bars] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert bars[0].high == Decimal("103.50")
    assert bars[0].turnover is None
    assert bars[1].turnover == Decimal("123000.00")
    assert bars[0].source_record_id == "daily_bars.csv:line 3"
    assert bars[0].retrieved_at == manifest.extracted_at


def test_reingesting_the_same_source_is_idempotent(
    db_engine: Engine, lake: DataLake, write_csv_source: WriteSource, tmp_path: Path
) -> None:
    directory = write_csv_source()
    first = ingest_daily_bars(_provider(directory), db_engine, lake)
    files = _lake_files(tmp_path / "lake")
    counts = {table.name: _count(db_engine, table) for table in t.metadata.sorted_tables}

    second = ingest_daily_bars(_provider(directory), db_engine, lake)

    assert second.already_ingested
    assert second.run_id is None
    assert second.manifest == first.manifest
    assert _lake_files(tmp_path / "lake") == files
    assert {table.name: _count(db_engine, table) for table in t.metadata.sorted_tables} == counts


def test_a_corrected_file_creates_a_new_version_and_keeps_the_old_one(
    db_engine: Engine, lake: DataLake, write_csv_source: WriteSource
) -> None:
    first = ingest_daily_bars(_provider(write_csv_source()), db_engine, lake).manifest
    corrected = BARS_CSV.replace("T1,2024-01-03,103.00,104.00", "T1,2024-01-03,103.00,104.25")

    second = ingest_daily_bars(
        _provider(write_csv_source(bars=corrected)), db_engine, lake
    ).manifest

    assert (second.version, second.snapshot_id) == (2, "test_csv.daily_bars-v2")
    assert second.content_sha256 != first.content_sha256
    assert second.instrument_ids == first.instrument_ids  # internal IDs are stable
    assert _count(db_engine, t.instruments) == 2
    assert reproduce_snapshot(first.snapshot_id, db_engine, lake).matches
    assert reproduce_snapshot(second.snapshot_id, db_engine, lake).matches
    with db_engine.connect() as conn:
        assert catalog.latest_snapshot(conn, "test_csv.daily_bars") == second
        (instrument,) = catalog.search_instruments(conn, "TESTONE")
    old = lake.read_bars(first, instrument.instrument_id, date(2024, 1, 3), date(2024, 1, 3))
    new = lake.read_bars(second, instrument.instrument_id, date(2024, 1, 3), date(2024, 1, 3))
    assert (old[0].high, new[0].high) == (Decimal("104.00"), Decimal("104.25"))


def test_invalid_rows_are_quarantined_and_visible(
    db_engine: Engine, lake: DataLake, write_csv_source: WriteSource
) -> None:
    bars = (
        BARS_CSV
        + "T1,2024-01-04,102.00,101.00,100.00,101.50,900,\n"  # high below open
        + "T2,2024-01-03,51.75,52.00,51.00,abc,700,\n"  # close not a number
        + "T9,2024-01-03,10,10,10,10,10,\n"  # unknown instrument
        + "T2,2024-01-02,50.50,52.00,50.00,51.75,900,46000.00\n"  # identical repeat
    )

    manifest = ingest_daily_bars(_provider(write_csv_source(bars=bars)), db_engine, lake).manifest

    assert (manifest.record_count, manifest.quarantined_count) == (5, 4)
    assert any("4 source record(s) were quarantined" in w for w in manifest.quality_warnings)
    report = lake.read_snapshot_quarantine(manifest)
    assert [r.source_record_id for r in report] == [
        "daily_bars.csv:line 7",
        "daily_bars.csv:line 8",
        "daily_bars.csv:line 9",
        "daily_bars.csv:line 10",
    ]
    assert report[1].raw_fields["close"] == "abc"
    assert reproduce_snapshot(manifest.snapshot_id, db_engine, lake).matches


def test_failed_ingestion_publishes_nothing_and_stays_recorded(
    db_engine: Engine, lake: DataLake, write_csv_source: WriteSource, tmp_path: Path
) -> None:
    bars = (
        "provider_instrument_id,trading_date,open,high,low,close,volume\nT1,2024-01-01,x,1,1,1,1\n"
    )

    with pytest.raises(IngestionFailedError, match="no valid records") as raised:
        ingest_daily_bars(_provider(write_csv_source(bars=bars)), db_engine, lake)

    assert _count(db_engine, t.dataset_snapshots) == 0
    assert _count(db_engine, t.instruments) == 0  # rolled back with the failed publish
    assert not (tmp_path / "lake" / "curated" / "test_csv.daily_bars" / "v1").exists()
    assert not list((tmp_path / "lake" / "curated").rglob(".staging-*"))
    with db_engine.connect() as conn:
        run = catalog.get_run(conn, raised.value.run_id)
        assert run is not None
        assert run.status == "FAILED"
        assert run.error is not None and "no valid records" in run.error
        assert run.quarantined_count == 1
        assert run.quarantine_path is not None
        assert len(lake.read_quarantine_report(run.quarantine_path)) == 1
        failed = conn.execute(
            select(func.count()).where(t.audit_events.c.event_type == "data.ingestion.failed")
        ).scalar_one()
    assert failed == 1

    # The same input is not treated as already ingested; a retry runs again.
    with pytest.raises(IngestionFailedError):
        ingest_daily_bars(_provider(write_csv_source(bars=bars)), db_engine, lake)
    assert _count(db_engine, t.ingestion_runs) == 2


def test_malformed_instrument_file_fails_the_run(
    db_engine: Engine, lake: DataLake, write_csv_source: WriteSource
) -> None:
    directory = write_csv_source(instruments="provider_instrument_id,symbol\nT1,X\n")

    with pytest.raises(IngestionFailedError, match="missing columns"):
        ingest_daily_bars(_provider(directory), db_engine, lake)

    assert _count(db_engine, t.dataset_snapshots) == 0


def test_leftover_directory_from_an_uncommitted_publish_is_replaced(
    db_engine: Engine, lake: DataLake, write_csv_source: WriteSource, tmp_path: Path
) -> None:
    orphan = tmp_path / "lake" / "curated" / "test_csv.daily_bars" / "v1"
    orphan.mkdir(parents=True)
    (orphan / "bars.parquet").write_bytes(b"garbage from a crashed publish")

    manifest = ingest_daily_bars(_provider(write_csv_source()), db_engine, lake).manifest

    assert manifest.version == 1
    assert lake.verify_snapshot_files(manifest) == []


def test_reproduction_detects_tampering(
    db_engine: Engine, lake: DataLake, write_csv_source: WriteSource, tmp_path: Path
) -> None:
    manifest = ingest_daily_bars(_provider(write_csv_source()), db_engine, lake).manifest
    assert reproduce_snapshot(manifest.snapshot_id, db_engine, lake).matches

    other = ingest_daily_bars(SyntheticFixtureProvider(), db_engine, lake).manifest
    curated = tmp_path / "lake" / "curated"
    (curated / "test_csv.daily_bars" / "v1" / "bars.parquet").write_bytes(
        (curated / other.dataset_id / "v1" / "bars.parquet").read_bytes()
    )

    report = reproduce_snapshot(manifest.snapshot_id, db_engine, lake)

    assert not report.matches
    assert report.rebuilt_content_sha256 == manifest.content_sha256
    assert report.stored_content_sha256 != manifest.content_sha256
    assert any("bars.parquet: checksum mismatch" in p for p in report.problems)


def test_synthetic_snapshot_is_classified_and_kept_in_its_own_dataset(
    db_engine: Engine, lake: DataLake, write_csv_source: WriteSource
) -> None:
    synthetic = ingest_daily_bars(SyntheticFixtureProvider(), db_engine, lake).manifest
    supplied = ingest_daily_bars(_provider(write_csv_source()), db_engine, lake).manifest

    assert synthetic.data_classification is DataClassification.SYNTHETIC_TEST_DATA
    assert synthetic.dataset_id == "synthetic_fixture.daily_bars"
    assert set(synthetic.instrument_ids).isdisjoint(supplied.instrument_ids)
    assert reproduce_snapshot(synthetic.snapshot_id, db_engine, lake).matches


def test_symbol_change_is_effective_dated(
    db_engine: Engine, lake: DataLake, write_csv_source: WriteSource
) -> None:
    ingest_daily_bars(_provider(write_csv_source()), db_engine, lake)
    renamed = (
        INSTRUMENTS_CSV.replace(
            "T1,NSE,EQUITY,TESTONE,Synthetic Test One Ltd,,2024-01-01,",
            "T1,NSE,EQUITY,TESTONE,Synthetic Test One Ltd,,2024-01-01,2024-01-02",
        )
        + "T1,NSE,EQUITY,TESTUNO,Synthetic Test Uno Ltd,,2024-01-03,\n"
    )

    ingest_daily_bars(
        _provider(write_csv_source(instruments=renamed), "delivery-2"), db_engine, lake
    )

    with db_engine.connect() as conn:
        (by_new,) = catalog.search_instruments(conn, "TESTUNO")
        (by_old,) = catalog.search_instruments(conn, "TESTONE")
        assert by_new.instrument_id == by_old.instrument_id
        assert catalog.search_instruments(conn, "TESTONE", as_of=date(2024, 1, 3)) == []
        assert catalog.search_instruments(conn, "TESTUNO", as_of=date(2024, 1, 2)) == []
    old, new = by_new.symbol_as_of(date(2024, 1, 2)), by_new.symbol_as_of(date(2024, 1, 3))
    assert old is not None and new is not None
    assert (old.symbol, new.symbol) == ("TESTONE", "TESTUNO")
    assert by_new.symbol_as_of(date(2023, 12, 31)) is None


def test_contradicting_instrument_history_fails_instead_of_overwriting(
    db_engine: Engine, lake: DataLake, write_csv_source: WriteSource
) -> None:
    ingest_daily_bars(_provider(write_csv_source()), db_engine, lake)
    contradicting = INSTRUMENTS_CSV.replace("TESTONE", "OTHERSYM")

    with pytest.raises(IngestionFailedError, match="already recorded as TESTONE"):
        ingest_daily_bars(_provider(write_csv_source(instruments=contradicting)), db_engine, lake)

    with db_engine.connect() as conn:
        assert catalog.search_instruments(conn, "OTHERSYM") == []


def test_instrument_search_escapes_wildcards(
    db_engine: Engine, lake: DataLake, write_csv_source: WriteSource
) -> None:
    ingest_daily_bars(_provider(write_csv_source()), db_engine, lake)

    with db_engine.connect() as conn:
        assert len(catalog.search_instruments(conn, "test")) == 2
        assert len(catalog.search_instruments(conn, "two ltd")) == 1
        assert catalog.search_instruments(conn, "%") == []
        assert catalog.search_instruments(conn, "TEST_NE") == []


def test_invalid_source_id_is_rejected_before_anything_is_written(
    db_engine: Engine, lake: DataLake, write_csv_source: WriteSource, tmp_path: Path
) -> None:
    provider = CsvFileProvider(
        write_csv_source(),
        source_id="../escape",
        licence_reference="SYNTHETIC_TEST_DATA",
        source_dataset_version="1",
        adjustment_basis=AdjustmentBasis.UNADJUSTED,
    )

    with pytest.raises(ValueError, match="invalid source_id"):
        ingest_daily_bars(provider, db_engine, lake)

    assert not (tmp_path / "lake").exists()
    assert _count(db_engine, t.raw_objects) == 0


def test_audit_events_reject_update_and_delete(db_engine: Engine) -> None:
    with db_engine.begin() as conn:
        catalog.write_audit_event(conn, "test.event", "test")

    for statement in ("UPDATE audit_events SET actor = 'x'", "DELETE FROM audit_events"):
        with pytest.raises(DBAPIError, match="append-only"), db_engine.begin() as conn:
            conn.execute(text(statement))

    assert _count(db_engine, t.audit_events) == 1
