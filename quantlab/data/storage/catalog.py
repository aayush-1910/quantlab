"""Catalog queries: instrument master, raw objects, snapshots, ingestion runs, audit.

Functions take an open SQLAlchemy connection; the caller owns the transaction.
"""

import itertools
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import Connection, and_, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from quantlab.data.providers.base import ProviderInstrument
from quantlab.data.schemas import (
    Currency,
    Exchange,
    Instrument,
    InstrumentType,
    SnapshotManifest,
    SymbolMapping,
)
from quantlab.data.storage import tables as t


class InstrumentConflictError(Exception):
    """Provider instrument data contradicts the instrument master; needs a human decision."""


@dataclass(frozen=True)
class IngestionRun:
    run_id: str
    source_id: str
    input_fingerprint: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    snapshot_id: str | None
    record_count: int | None
    quarantined_count: int | None
    quarantine_path: str | None
    error: str | None


# --- audit ---------------------------------------------------------------------------


def write_audit_event(
    conn: Connection,
    event_type: str,
    actor: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        t.audit_events.insert().values(
            event_type=event_type,
            actor=actor,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload or {},
        )
    )


# --- instrument master ---------------------------------------------------------------


def _load_instruments(conn: Connection, instrument_ids: Sequence[str]) -> dict[str, Instrument]:
    if not instrument_ids:
        return {}
    symbols: dict[str, list[SymbolMapping]] = {}
    for row in conn.execute(
        select(t.instrument_symbols)
        .where(t.instrument_symbols.c.instrument_id.in_(instrument_ids))
        .order_by(t.instrument_symbols.c.valid_from, t.instrument_symbols.c.source_id)
    ).mappings():
        symbols.setdefault(row["instrument_id"], []).append(
            SymbolMapping(
                symbol=row["symbol"],
                name=row["name"],
                isin=row["isin"],
                valid_from=row["valid_from"],
                valid_to=row["valid_to"],
                source_id=row["source_id"],
            )
        )
    return {
        row["id"]: Instrument(
            instrument_id=row["id"],
            exchange=Exchange(row["exchange"]),
            instrument_type=InstrumentType(row["instrument_type"]),
            currency=Currency(row["currency"]),
            symbols=tuple(symbols.get(row["id"], [])),
        )
        for row in conn.execute(
            select(t.instruments).where(t.instruments.c.id.in_(instrument_ids))
        ).mappings()
    }


def get_instrument(conn: Connection, instrument_id: str) -> Instrument | None:
    return _load_instruments(conn, [instrument_id]).get(instrument_id)


def get_instruments(conn: Connection, instrument_ids: Sequence[str]) -> dict[str, Instrument]:
    return _load_instruments(conn, instrument_ids)


def search_instruments(
    conn: Connection,
    query: str | None = None,
    exchange: Exchange | None = None,
    as_of: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Instrument]:
    """Match on symbol or name. With `as_of`, only mappings in effect on that date match."""
    conditions = []
    if query:
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        conditions.append(
            or_(
                t.instrument_symbols.c.symbol.ilike(pattern, escape="\\"),
                t.instrument_symbols.c.name.ilike(pattern, escape="\\"),
            )
        )
    if as_of is not None:
        conditions.append(
            and_(
                t.instrument_symbols.c.valid_from <= as_of,
                or_(
                    t.instrument_symbols.c.valid_to.is_(None),
                    t.instrument_symbols.c.valid_to >= as_of,
                ),
            )
        )
    if exchange is not None:
        conditions.append(t.instruments.c.exchange == exchange.value)

    statement = (
        select(t.instruments.c.id)
        .join(t.instrument_symbols, t.instrument_symbols.c.instrument_id == t.instruments.c.id)
        .where(*conditions)
        .group_by(t.instruments.c.id)
        .order_by(func.min(t.instrument_symbols.c.symbol), t.instruments.c.id)
        .limit(limit)
        .offset(offset)
    )
    ids = list(conn.execute(statement).scalars())
    loaded = _load_instruments(conn, ids)
    return [loaded[instrument_id] for instrument_id in ids]


def lookup_provider_instruments(
    conn: Connection, source_id: str, provider_instrument_ids: Sequence[str]
) -> dict[str, Instrument]:
    """Provider ID -> registered instrument, for IDs already known. Read-only."""
    if not provider_instrument_ids:
        return {}
    mapping = {
        row.provider_instrument_id: row.instrument_id
        for row in conn.execute(
            select(t.provider_instrument_ids).where(
                t.provider_instrument_ids.c.source_id == source_id,
                t.provider_instrument_ids.c.provider_instrument_id.in_(provider_instrument_ids),
            )
        )
    }
    loaded = _load_instruments(conn, list(mapping.values()))
    return {provider_id: loaded[instrument_id] for provider_id, instrument_id in mapping.items()}


def register_instruments(
    conn: Connection, source_id: str, provider_instruments: Sequence[ProviderInstrument]
) -> dict[str, Instrument]:
    """Map provider instruments to stable internal IDs, creating them on first sight.

    Symbol periods are keyed by (instrument, source, valid_from). A new period is added.
    A known period may only gain an end date or fill in a missing name/ISIN; anything
    else (a different symbol, a different end date) raises InstrumentConflictError.
    """
    seen: set[str] = set()
    for provider_instrument in provider_instruments:
        if provider_instrument.provider_instrument_id in seen:
            raise InstrumentConflictError(
                f"provider instrument listed twice: {provider_instrument.provider_instrument_id}"
            )
        seen.add(provider_instrument.provider_instrument_id)
        periods = sorted(provider_instrument.symbols, key=lambda s: s.valid_from)
        if not periods:
            raise InstrumentConflictError(
                f"{provider_instrument.provider_instrument_id}: no symbol period supplied"
            )
        for earlier, later in itertools.pairwise(periods):
            if earlier.valid_to is None or earlier.valid_to >= later.valid_from:
                raise InstrumentConflictError(
                    f"{provider_instrument.provider_instrument_id}: symbol periods overlap "
                    f"({earlier.symbol} and {later.symbol})"
                )
        for period in periods:
            if period.valid_to is not None and period.valid_to < period.valid_from:
                raise InstrumentConflictError(
                    f"{provider_instrument.provider_instrument_id}: {period.symbol} ends "
                    "before it starts"
                )

    known = lookup_provider_instruments(conn, source_id, sorted(seen))

    for provider_instrument in provider_instruments:
        pid = provider_instrument.provider_instrument_id
        existing = known.get(pid)
        if existing is None:
            instrument_id = str(uuid.uuid4())
            conn.execute(
                t.instruments.insert().values(
                    id=instrument_id,
                    exchange=provider_instrument.exchange.value,
                    instrument_type=provider_instrument.instrument_type.value,
                    currency=provider_instrument.currency.value,
                )
            )
            conn.execute(
                t.provider_instrument_ids.insert().values(
                    source_id=source_id, provider_instrument_id=pid, instrument_id=instrument_id
                )
            )
            write_audit_event(
                conn,
                "data.instrument.registered",
                actor="system:ingestion",
                entity_type="instrument",
                entity_id=instrument_id,
                payload={"source_id": source_id, "provider_instrument_id": pid},
            )
            current: dict[date, SymbolMapping] = {}
        else:
            instrument_id = existing.instrument_id
            if (existing.exchange, existing.instrument_type, existing.currency) != (
                provider_instrument.exchange,
                provider_instrument.instrument_type,
                provider_instrument.currency,
            ):
                raise InstrumentConflictError(
                    f"{pid}: exchange, type or currency differs from the registered instrument"
                )
            current = {m.valid_from: m for m in existing.symbols if m.source_id == source_id}

        for period in provider_instrument.symbols:
            stored = current.get(period.valid_from)
            if stored is None:
                conn.execute(
                    t.instrument_symbols.insert().values(
                        instrument_id=instrument_id,
                        source_id=source_id,
                        symbol=period.symbol,
                        name=period.name,
                        isin=period.isin,
                        valid_from=period.valid_from,
                        valid_to=period.valid_to,
                    )
                )
                continue
            conflict = (
                stored.symbol != period.symbol
                or (stored.valid_to is not None and stored.valid_to != period.valid_to)
                or (stored.name is not None and period.name not in (None, stored.name))
                or (stored.isin is not None and period.isin not in (None, stored.isin))
            )
            if conflict:
                raise InstrumentConflictError(
                    f"{pid}: symbol period starting {period.valid_from} is already recorded "
                    f"as {stored.symbol} (until {stored.valid_to}) and the new data disagrees"
                )
            changes = {
                "valid_to": period.valid_to if stored.valid_to is None else stored.valid_to,
                "name": stored.name or period.name,
                "isin": stored.isin or period.isin,
            }
            if changes != {"valid_to": stored.valid_to, "name": stored.name, "isin": stored.isin}:
                conn.execute(
                    t.instrument_symbols.update()
                    .where(
                        t.instrument_symbols.c.instrument_id == instrument_id,
                        t.instrument_symbols.c.source_id == source_id,
                        t.instrument_symbols.c.valid_from == period.valid_from,
                    )
                    .values(**changes)
                )
                write_audit_event(
                    conn,
                    "data.instrument.symbol_period_updated",
                    actor="system:ingestion",
                    entity_type="instrument",
                    entity_id=instrument_id,
                    payload={
                        "source_id": source_id,
                        "symbol": stored.symbol,
                        "valid_from": period.valid_from.isoformat(),
                        "valid_to": None
                        if changes["valid_to"] is None
                        else str(changes["valid_to"]),
                    },
                )

    registered = lookup_provider_instruments(conn, source_id, sorted(seen))
    for pid, instrument in registered.items():
        recorded = sorted(
            (m for m in instrument.symbols if m.source_id == source_id), key=lambda m: m.valid_from
        )
        for before, after in itertools.pairwise(recorded):
            if before.valid_to is None or before.valid_to >= after.valid_from:
                raise InstrumentConflictError(
                    f"{pid}: recorded symbol recorded would overlap "
                    f"({before.symbol} and {after.symbol})"
                )
    return registered


# --- raw objects ---------------------------------------------------------------------


def record_raw_object(
    conn: Connection,
    *,
    source_id: str,
    kind: str,
    sha256: str,
    format_id: str,
    byte_size: int,
    path: str,
    retrieved_at: datetime,
    source_as_of: datetime | None,
) -> datetime:
    """Record a raw object once. Returns the time it was first retrieved."""
    conn.execute(
        pg_insert(t.raw_objects)
        .values(
            source_id=source_id,
            kind=kind,
            sha256=sha256,
            format_id=format_id,
            byte_size=byte_size,
            path=path,
            retrieved_at=retrieved_at,
            source_as_of=source_as_of,
        )
        .on_conflict_do_nothing()
    )
    first: datetime = conn.execute(
        select(t.raw_objects.c.retrieved_at).where(
            t.raw_objects.c.source_id == source_id,
            t.raw_objects.c.kind == kind,
            t.raw_objects.c.sha256 == sha256,
        )
    ).scalar_one()
    return first


# --- snapshots -----------------------------------------------------------------------


def lock_dataset_for_publish(conn: Connection, dataset_id: str) -> None:
    """Serialize publishes of one dataset until the surrounding transaction ends."""
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": dataset_id})


def next_snapshot_version(conn: Connection, dataset_id: str) -> int:
    current = conn.execute(
        select(func.max(t.dataset_snapshots.c.version)).where(
            t.dataset_snapshots.c.dataset_id == dataset_id
        )
    ).scalar_one()
    return int(current or 0) + 1


def insert_snapshot(conn: Connection, manifest: SnapshotManifest) -> None:
    conn.execute(
        t.dataset_snapshots.insert().values(
            id=manifest.snapshot_id,
            dataset_id=manifest.dataset_id,
            version=manifest.version,
            source_id=manifest.source_id,
            data_classification=manifest.data_classification.value,
            input_fingerprint=manifest.input_fingerprint,
            content_sha256=manifest.content_sha256,
            manifest=manifest.model_dump(mode="json"),
            created_at=manifest.created_at,
        )
    )


def _manifest(value: Any) -> SnapshotManifest:
    return SnapshotManifest.model_validate(value)


def get_snapshot(conn: Connection, snapshot_id: str) -> SnapshotManifest | None:
    value = conn.execute(
        select(t.dataset_snapshots.c.manifest).where(t.dataset_snapshots.c.id == snapshot_id)
    ).scalar_one_or_none()
    return None if value is None else _manifest(value)


def find_snapshot_by_fingerprint(conn: Connection, fingerprint: str) -> SnapshotManifest | None:
    value = conn.execute(
        select(t.dataset_snapshots.c.manifest).where(
            t.dataset_snapshots.c.input_fingerprint == fingerprint
        )
    ).scalar_one_or_none()
    return None if value is None else _manifest(value)


def latest_snapshot(conn: Connection, dataset_id: str) -> SnapshotManifest | None:
    value = conn.execute(
        select(t.dataset_snapshots.c.manifest)
        .where(t.dataset_snapshots.c.dataset_id == dataset_id)
        .order_by(t.dataset_snapshots.c.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    return None if value is None else _manifest(value)


def list_snapshots(conn: Connection, dataset_id: str | None = None) -> list[SnapshotManifest]:
    statement = select(t.dataset_snapshots.c.manifest).order_by(
        t.dataset_snapshots.c.dataset_id, t.dataset_snapshots.c.version.desc()
    )
    if dataset_id is not None:
        statement = statement.where(t.dataset_snapshots.c.dataset_id == dataset_id)
    return [_manifest(value) for value in conn.execute(statement).scalars()]


# --- ingestion runs ------------------------------------------------------------------


def insert_run(
    conn: Connection, run_id: str, source_id: str, fingerprint: str, started_at: datetime
) -> None:
    conn.execute(
        t.ingestion_runs.insert().values(
            id=run_id,
            source_id=source_id,
            input_fingerprint=fingerprint,
            status="RUNNING",
            started_at=started_at,
        )
    )


def finish_run(conn: Connection, run_id: str, status: str, **values: Any) -> None:
    conn.execute(
        t.ingestion_runs.update()
        .where(t.ingestion_runs.c.id == run_id)
        .values(status=status, **values)
    )


def _run(row: Any) -> IngestionRun:
    return IngestionRun(
        run_id=row["id"],
        source_id=row["source_id"],
        input_fingerprint=row["input_fingerprint"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        snapshot_id=row["snapshot_id"],
        record_count=row["record_count"],
        quarantined_count=row["quarantined_count"],
        quarantine_path=row["quarantine_path"],
        error=row["error"],
    )


def get_run(conn: Connection, run_id: str) -> IngestionRun | None:
    row = (
        conn.execute(select(t.ingestion_runs).where(t.ingestion_runs.c.id == run_id))
        .mappings()
        .one_or_none()
    )
    return None if row is None else _run(row)


def list_runs(conn: Connection, limit: int = 50) -> list[IngestionRun]:
    rows = conn.execute(
        select(t.ingestion_runs).order_by(t.ingestion_runs.c.started_at.desc()).limit(limit)
    ).mappings()
    return [_run(row) for row in rows]


# --- watchlist -----------------------------------------------------------------------


def add_to_watchlist(conn: Connection, instrument_id: str) -> None:
    conn.execute(
        pg_insert(t.watchlist_items).values(instrument_id=instrument_id).on_conflict_do_nothing()
    )


def remove_from_watchlist(conn: Connection, instrument_id: str) -> None:
    conn.execute(
        t.watchlist_items.delete().where(t.watchlist_items.c.instrument_id == instrument_id)
    )


def list_watchlist(conn: Connection) -> list[tuple[Instrument, datetime]]:
    rows = conn.execute(
        select(t.watchlist_items).order_by(
            t.watchlist_items.c.added_at, t.watchlist_items.c.instrument_id
        )
    ).all()
    loaded = _load_instruments(conn, [row.instrument_id for row in rows])
    return [(loaded[row.instrument_id], row.added_at) for row in rows]
