"""File-based data lake with three layers (spec section 5.3).

    raw/<source_id>/<kind>/<sha256>.<ext>        source bytes, content-addressed, write-once
    normalized/<source_id>/<run_id>/             typed records and quarantine of one run
    curated/<dataset_id>/v<version>/             published, immutable snapshot + manifest

Nothing here decides whether a snapshot is published. A curated directory only counts
once the catalog (PostgreSQL) has a row for it; see quantlab.data.ingestion.service.
"""

import hashlib
import json
import os
import shutil
import stat
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path

import polars as pl

from quantlab.data.providers.base import RawPayload
from quantlab.data.schemas import (
    PRICE_DECIMAL_PLACES,
    TURNOVER_DECIMAL_PLACES,
    DailyBar,
    FileChecksum,
    QuarantinedRecord,
    SnapshotManifest,
)

BARS_FILE = "bars.parquet"
QUARANTINE_FILE = "quarantine.jsonl"
MANIFEST_FILE = "manifest.json"

_PRICE = pl.Decimal(20, PRICE_DECIMAL_PLACES)
_TIMESTAMP = pl.Datetime("us", "UTC")
_BAR_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "instrument_id": pl.String,
    "exchange": pl.String,
    "trading_date": pl.Date,
    "open": _PRICE,
    "high": _PRICE,
    "low": _PRICE,
    "close": _PRICE,
    "volume": pl.Int64,
    "turnover": pl.Decimal(24, TURNOVER_DECIMAL_PLACES),
    "source_id": pl.String,
    "source_record_id": pl.String,
    "retrieved_at": _TIMESTAMP,
    "source_as_of": _TIMESTAMP,
    "currency": pl.String,
    "adjustment_basis": pl.String,
    "schema_version": pl.String,
}


class LakeIntegrityError(Exception):
    """Stored bytes do not match their recorded checksum, or a file is missing."""


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_sha256(bars: Iterable[DailyBar]) -> str:
    """Checksum of the logical content, independent of Parquet encoding or library version.

    Bars must already be sorted by (instrument_id, trading_date).
    """
    digest = hashlib.sha256()
    for bar in bars:
        row = [
            bar.instrument_id,
            bar.exchange.value,
            bar.trading_date.isoformat(),
            f"{bar.open:.{PRICE_DECIMAL_PLACES}f}",
            f"{bar.high:.{PRICE_DECIMAL_PLACES}f}",
            f"{bar.low:.{PRICE_DECIMAL_PLACES}f}",
            f"{bar.close:.{PRICE_DECIMAL_PLACES}f}",
            bar.volume,
            None if bar.turnover is None else f"{bar.turnover:.{TURNOVER_DECIMAL_PLACES}f}",
            bar.source_id,
            bar.source_record_id,
            bar.retrieved_at.isoformat(),
            None if bar.source_as_of is None else bar.source_as_of.isoformat(),
            bar.currency.value,
            bar.adjustment_basis.value,
            bar.schema_version,
        ]
        digest.update(json.dumps(row, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _write_bars(path: Path, bars: Sequence[DailyBar]) -> None:
    rows = [bar.model_dump() for bar in bars]
    pl.DataFrame(rows, schema=_BAR_SCHEMA, orient="row").write_parquet(path)


def _write_quarantine(path: Path, quarantined: Sequence[QuarantinedRecord]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in quarantined:
            handle.write(record.model_dump_json() + "\n")


def _read_quarantine(path: Path) -> list[QuarantinedRecord]:
    if not path.is_file():
        raise LakeIntegrityError(f"quarantine report is missing: {path}")
    with path.open(encoding="utf-8") as handle:
        return [QuarantinedRecord.model_validate_json(line) for line in handle if line.strip()]


def _remove_tree(path: Path) -> None:
    def _make_writable(function, target, _exc):  # type: ignore[no-untyped-def]
        os.chmod(target, stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onexc=_make_writable)


class DataLake:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _resolve(self, relative_path: str) -> Path:
        path = (self._root / relative_path).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise LakeIntegrityError(f"path escapes the data lake: {relative_path}")
        return path

    # --- raw layer -------------------------------------------------------------------

    def store_raw(self, source_id: str, payload: RawPayload) -> tuple[str, str]:
        """Store source bytes write-once. Returns (sha256, path relative to the lake root)."""
        checksum = sha256_bytes(payload.content)
        relative = f"raw/{source_id}/{payload.kind}/{checksum}.{payload.file_extension}"
        path = self._resolve(relative)
        if path.exists():
            if sha256_file(path) != checksum:
                raise LakeIntegrityError(f"raw object is corrupt: {relative}")
            return checksum, relative
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_bytes(payload.content)
        os.chmod(temporary, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
        os.replace(temporary, path)
        return checksum, relative

    def read_raw(self, relative_path: str, expected_sha256: str) -> bytes:
        path = self._resolve(relative_path)
        if not path.is_file():
            raise LakeIntegrityError(f"raw object is missing: {relative_path}")
        content = path.read_bytes()
        if sha256_bytes(content) != expected_sha256:
            raise LakeIntegrityError(f"raw object does not match its checksum: {relative_path}")
        return content

    # --- normalized layer ------------------------------------------------------------

    def write_normalized(
        self,
        source_id: str,
        run_id: str,
        bars: Sequence[DailyBar],
        quarantined: Sequence[QuarantinedRecord],
    ) -> str:
        """Returns the quarantine report path relative to the lake root."""
        relative = f"normalized/{source_id}/{run_id}"
        directory = self._resolve(relative)
        directory.mkdir(parents=True, exist_ok=True)
        _write_bars(directory / BARS_FILE, bars)
        _write_quarantine(directory / QUARANTINE_FILE, quarantined)
        return f"{relative}/{QUARANTINE_FILE}"

    def read_quarantine_report(self, relative_path: str) -> list[QuarantinedRecord]:
        return _read_quarantine(self._resolve(relative_path))

    # --- curated layer ---------------------------------------------------------------

    def _snapshot_dir(self, dataset_id: str, version: int) -> Path:
        return self._resolve(f"curated/{dataset_id}/v{version}")

    def stage_snapshot(
        self,
        dataset_id: str,
        run_id: str,
        bars: Sequence[DailyBar],
        quarantined: Sequence[QuarantinedRecord],
    ) -> tuple[Path, tuple[FileChecksum, ...]]:
        """Write snapshot data files to a staging directory that no reader looks at."""
        staging = self._resolve(f"curated/{dataset_id}/.staging-{run_id}")
        if staging.exists():
            _remove_tree(staging)
        staging.mkdir(parents=True)
        _write_bars(staging / BARS_FILE, bars)
        _write_quarantine(staging / QUARANTINE_FILE, quarantined)
        files = tuple(
            FileChecksum(
                path=name,
                sha256=sha256_file(staging / name),
                byte_size=(staging / name).stat().st_size,
            )
            for name in (BARS_FILE, QUARANTINE_FILE)
        )
        return staging, files

    def promote_snapshot(self, staging: Path, manifest: SnapshotManifest) -> None:
        """Move a staged snapshot to its final location.

        The caller must hold the dataset's publish lock and must have confirmed that the
        catalog has no row for this version. A directory already at the target is therefore
        left over from a publish that never committed, and is replaced.
        """
        (staging / MANIFEST_FILE).write_text(
            manifest.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        target = self._snapshot_dir(manifest.dataset_id, manifest.version)
        if target.exists():
            _remove_tree(target)
        os.replace(staging, target)

    def discard_staging(self, staging: Path) -> None:
        if staging.exists():
            _remove_tree(staging)

    def verify_snapshot_files(self, manifest: SnapshotManifest) -> list[str]:
        """Returns a list of problems; empty means every file matches the manifest."""
        directory = self._snapshot_dir(manifest.dataset_id, manifest.version)
        problems = []
        for expected in manifest.files:
            path = directory / expected.path
            if not path.is_file():
                problems.append(f"{expected.path}: missing")
            elif sha256_file(path) != expected.sha256:
                problems.append(f"{expected.path}: checksum mismatch")
        return problems

    def read_bars(
        self,
        manifest: SnapshotManifest,
        instrument_id: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> list[DailyBar]:
        path = self._snapshot_dir(manifest.dataset_id, manifest.version) / BARS_FILE
        if not path.is_file():
            raise LakeIntegrityError(f"snapshot data file is missing: {manifest.snapshot_id}")
        frame = pl.scan_parquet(path)
        if instrument_id is not None:
            frame = frame.filter(pl.col("instrument_id") == instrument_id)
        if start is not None:
            frame = frame.filter(pl.col("trading_date") >= start)
        if end is not None:
            frame = frame.filter(pl.col("trading_date") <= end)
        rows = frame.sort("instrument_id", "trading_date").collect().to_dicts()
        return [DailyBar.model_validate(row) for row in rows]

    def read_snapshot_quarantine(self, manifest: SnapshotManifest) -> list[QuarantinedRecord]:
        directory = self._snapshot_dir(manifest.dataset_id, manifest.version)
        return _read_quarantine(directory / QUARANTINE_FILE)
