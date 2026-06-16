"""measurements.geometry nullable

Area/perimeter measurements are scalar (no geometry), but some databases were
created with a NOT NULL geometry column (from an older schema), which made every
area/perimeter insert fail. Drop the NOT NULL so value-only measurements persist.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-14
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE measurements ALTER COLUMN geometry DROP NOT NULL")


def downgrade() -> None:
    # Only re-add NOT NULL if no NULLs exist (otherwise leave as-is).
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM measurements WHERE geometry IS NULL) THEN "
        "ALTER TABLE measurements ALTER COLUMN geometry SET NOT NULL; "
        "END IF; END $$;"
    )
