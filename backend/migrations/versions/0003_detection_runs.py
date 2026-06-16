"""detection runs (history per AOI)

Each AOI keeps a HISTORY of detection runs instead of overwriting. A run holds
the parameters + summary; every Detection row links to the run that produced it.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-14
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "detection_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aoi_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("classes", postgresql.JSONB(), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name="fk_detection_runs_session_id"),
        sa.ForeignKeyConstraint(
            ["aoi_id"], ["aoi.id"], name="fk_detection_runs_aoi_id", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_detection_runs_aoi_id", "detection_runs", ["aoi_id"])

    op.add_column("detections", sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_detections_run_id", "detections", "detection_runs",
        ["run_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_detections_run_id", "detections", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_detections_run_id", table_name="detections")
    op.drop_constraint("fk_detections_run_id", "detections", type_="foreignkey")
    op.drop_column("detections", "run_id")
    op.drop_index("ix_detection_runs_aoi_id", table_name="detection_runs")
    op.drop_table("detection_runs")
