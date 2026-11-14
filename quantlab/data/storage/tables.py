"""SQLAlchemy Core table definitions for the market-data catalog.

Migrations stay hand-written (database/migrations); these definitions are for queries.
`tests/integration/test_migrations.py` checks the two agree on table and column names.
"""

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    MetaData,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

audit_events = Table(
    "audit_events",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("event_type", Text, nullable=False),
    Column("actor", Text, nullable=False),
    Column("entity_type", Text),
    Column("entity_id", Text),
    Column("payload", JSONB, nullable=False),
)

instruments = Table(
    "instruments",
    metadata,
    Column("id", Text, primary_key=True),
    Column("exchange", Text, nullable=False),
    Column("instrument_type", Text, nullable=False),
    Column("currency", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

instrument_symbols = Table(
    "instrument_symbols",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("instrument_id", Text, ForeignKey("instruments.id"), nullable=False),
    Column("source_id", Text, nullable=False),
    Column("symbol", Text, nullable=False),
    Column("name", Text),
    Column("isin", Text),
    Column("valid_from", Date, nullable=False),
    Column("valid_to", Date),
)

provider_instrument_ids = Table(
    "provider_instrument_ids",
    metadata,
    Column("source_id", Text, primary_key=True),
    Column("provider_instrument_id", Text, primary_key=True),
    Column("instrument_id", Text, ForeignKey("instruments.id"), nullable=False),
)

raw_objects = Table(
    "raw_objects",
    metadata,
    Column("source_id", Text, primary_key=True),
    Column("kind", Text, primary_key=True),
    Column("sha256", Text, primary_key=True),
    Column("format_id", Text, nullable=False),
    Column("byte_size", BigInteger, nullable=False),
    Column("path", Text, nullable=False),
    Column("retrieved_at", DateTime(timezone=True), nullable=False),
    Column("source_as_of", DateTime(timezone=True)),
)

dataset_snapshots = Table(
    "dataset_snapshots",
    metadata,
    Column("id", Text, primary_key=True),
    Column("dataset_id", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("data_classification", Text, nullable=False),
    Column("input_fingerprint", Text, nullable=False),
    Column("content_sha256", Text, nullable=False),
    Column("manifest", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

ingestion_runs = Table(
    "ingestion_runs",
    metadata,
    Column("id", Text, primary_key=True),
    Column("source_id", Text, nullable=False),
    Column("input_fingerprint", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("snapshot_id", Text, ForeignKey("dataset_snapshots.id")),
    Column("record_count", Integer),
    Column("quarantined_count", Integer),
    Column("quarantine_path", Text),
    Column("error", Text),
)
