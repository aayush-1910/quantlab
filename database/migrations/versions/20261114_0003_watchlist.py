"""Watchlist: one shared list of instruments.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14

There is no authentication yet, so there is exactly one watchlist. When users exist this
table gains an owner column; until then it must not be mistaken for per-user data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("instrument_id", sa.Text, sa.ForeignKey("instruments.id"), primary_key=True),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("watchlist_items")
