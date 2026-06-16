"""initial application schema

Creates the application tables (public.*) that were previously built by
scripts/init_db.py via Base.metadata.create_all. The PgSTAC catalog (pgstac.*)
is NOT created here — it is managed by pypgstac / stac-fastapi-pgstac.

NOTE: temporal_comparisons.left_item_id / right_item_id are plain strings with
NO foreign key to public.items — STAC item ids are opaque identifiers from the
PgSTAC schema or a remote catalog (Earth Search) that this app does not own.

Revision ID: 0001
Revises:
Create Date: 2026-06-13
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# GEOMETRY(4326). spatial_index=False here — the GIST indexes are created
# explicitly below with the same names GeoAlchemy2 uses (idx_<table>_geometry),
# so there is exactly one index per geometry column.
_GEOM = Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # ---- sessions ----------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("last_accessed", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", name="uq_sessions_session_id"),
    )

    # ---- collections -------------------------------------------------------
    op.create_table(
        "collections",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("data", postgresql.JSONB(), nullable=False),
    )

    # ---- aoi ---------------------------------------------------------------
    op.create_table(
        "aoi",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("geometry", _GEOM, nullable=False),
        sa.Column("properties", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name="fk_aoi_session_id"),
    )
    op.create_index("ix_aoi_session_id", "aoi", ["session_id"])
    op.execute("CREATE INDEX idx_aoi_geometry ON aoi USING gist (geometry)")

    # ---- measurements ------------------------------------------------------
    op.create_table(
        "measurements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aoi_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("geometry", _GEOM, nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name="fk_measurements_session_id"),
        sa.ForeignKeyConstraint(
            ["aoi_id"], ["aoi.id"], name="fk_measurements_aoi_id", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_measurements_aoi_id", "measurements", ["aoi_id"])
    op.execute("CREATE INDEX idx_measurements_geometry ON measurements USING gist (geometry)")

    # ---- items (optional fallback catalog) ---------------------------------
    op.create_table(
        "items",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("collection_id", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("geometry", _GEOM, nullable=False),
        sa.Column("datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], name="fk_items_collection_id"),
    )
    op.create_index("ix_items_collection_id", "items", ["collection_id"])
    op.create_index("ix_items_datetime", "items", ["datetime"])
    op.execute("CREATE INDEX idx_items_geometry ON items USING gist (geometry)")

    # ---- tasks -------------------------------------------------------------
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name="fk_tasks_session_id"),
    )
    op.create_index("ix_tasks_session_id", "tasks", ["session_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])

    # ---- temporal_comparisons (no FK to items by design) -------------------
    op.create_table(
        "temporal_comparisons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aoi_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("left_item_id", sa.String(), nullable=False),
        sa.Column("right_item_id", sa.String(), nullable=False),
        sa.Column("comparison_result", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], name="fk_temporal_comparisons_session_id"
        ),
        sa.ForeignKeyConstraint(
            ["aoi_id"], ["aoi.id"], name="fk_temporal_comparisons_aoi_id", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_temporal_comparisons_aoi_id", "temporal_comparisons", ["aoi_id"])
    op.create_index("ix_temporal_comparisons_session_id", "temporal_comparisons", ["session_id"])

    # ---- map_layers --------------------------------------------------------
    op.create_table(
        "map_layers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("map_layers")
    op.drop_index("ix_temporal_comparisons_session_id", table_name="temporal_comparisons")
    op.drop_index("ix_temporal_comparisons_aoi_id", table_name="temporal_comparisons")
    op.drop_table("temporal_comparisons")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_session_id", table_name="tasks")
    op.drop_table("tasks")
    op.execute("DROP INDEX IF EXISTS idx_items_geometry")
    op.drop_index("ix_items_datetime", table_name="items")
    op.drop_index("ix_items_collection_id", table_name="items")
    op.drop_table("items")
    op.execute("DROP INDEX IF EXISTS idx_measurements_geometry")
    op.drop_index("ix_measurements_aoi_id", table_name="measurements")
    op.drop_table("measurements")
    op.execute("DROP INDEX IF EXISTS idx_aoi_geometry")
    op.drop_index("ix_aoi_session_id", table_name="aoi")
    op.drop_table("aoi")
    op.drop_table("collections")
    op.drop_table("sessions")
