"""temporal_comparisons.task_id

Link a temporal comparison to the background task that builds it, so the client
can track progress over SSE/WebSocket (same pattern as detection runs). Nullable
and FK-free: the comparison is kept as history even after its task row is pruned.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-17
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE temporal_comparisons ADD COLUMN IF NOT EXISTS task_id UUID")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_temporal_comparisons_task_id "
        "ON temporal_comparisons (task_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_temporal_comparisons_task_id")
    op.execute("ALTER TABLE temporal_comparisons DROP COLUMN IF EXISTS task_id")
