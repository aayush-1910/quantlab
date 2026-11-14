"""Market-data catalog: instrument master, raw objects, snapshots, ingestion runs.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14

Also makes audit_events append-only for row changes: UPDATE and DELETE raise an error.
TRUNCATE and DROP are not blocked; restricting those is a role/privilege decision that
belongs with deployment, not with this migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("exchange", sa.Text, nullable=False),
        sa.Column("instrument_type", sa.Text, nullable=False),
        sa.Column("currency", sa.Text, nullable=False),
        sa.Column("created_at", _TZ, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "instrument_symbols",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("instrument_id", sa.Text, sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("source_id", sa.Text, nullable=False),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("isin", sa.Text, nullable=True),
        # Inclusive on both ends. valid_to NULL means "still in effect".
        sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date, nullable=True),
        sa.UniqueConstraint(
            "instrument_id", "source_id", "valid_from", name="uq_instrument_symbols_period"
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="ck_instrument_symbols_dates"
        ),
    )
    op.create_index("ix_instrument_symbols_symbol", "instrument_symbols", ["symbol"])

    op.create_table(
        "provider_instrument_ids",
        sa.Column("source_id", sa.Text, primary_key=True),
        sa.Column("provider_instrument_id", sa.Text, primary_key=True),
        sa.Column("instrument_id", sa.Text, sa.ForeignKey("instruments.id"), nullable=False),
    )

    op.create_table(
        "raw_objects",
        sa.Column("source_id", sa.Text, primary_key=True),
        sa.Column("kind", sa.Text, primary_key=True),
        sa.Column("sha256", sa.Text, primary_key=True),
        sa.Column("format_id", sa.Text, nullable=False),
        sa.Column("byte_size", sa.BigInteger, nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("retrieved_at", _TZ, nullable=False),
        sa.Column("source_as_of", _TZ, nullable=True),
    )

    op.create_table(
        "dataset_snapshots",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("dataset_id", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("source_id", sa.Text, nullable=False),
        sa.Column("data_classification", sa.Text, nullable=False),
        sa.Column("input_fingerprint", sa.Text, nullable=False),
        sa.Column("content_sha256", sa.Text, nullable=False),
        sa.Column("manifest", postgresql.JSONB, nullable=False),
        sa.Column("created_at", _TZ, nullable=False),
        sa.UniqueConstraint("dataset_id", "version", name="uq_dataset_snapshots_version"),
        sa.UniqueConstraint("input_fingerprint", name="uq_dataset_snapshots_fingerprint"),
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("source_id", sa.Text, nullable=False),
        sa.Column("input_fingerprint", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("started_at", _TZ, nullable=False),
        sa.Column("finished_at", _TZ, nullable=True),
        sa.Column("snapshot_id", sa.Text, sa.ForeignKey("dataset_snapshots.id"), nullable=True),
        sa.Column("record_count", sa.Integer, nullable=True),
        sa.Column("quarantined_count", sa.Integer, nullable=True),
        sa.Column("quarantine_path", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'SUCCEEDED', 'FAILED')", name="ck_ingestion_runs_status"
        ),
    )
    op.create_index("ix_ingestion_runs_started_at", "ingestion_runs", ["started_at"])

    op.execute(
        """
        CREATE FUNCTION audit_events_reject_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION audit_events_reject_change()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION audit_events_reject_change()")
    op.drop_index("ix_ingestion_runs_started_at", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_table("dataset_snapshots")
    op.drop_table("raw_objects")
    op.drop_table("provider_instrument_ids")
    op.drop_index("ix_instrument_symbols_symbol", table_name="instrument_symbols")
    op.drop_table("instrument_symbols")
    op.drop_table("instruments")
