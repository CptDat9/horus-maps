"""detections table (AI object detection)

Stores oriented bounding boxes produced by the YOLO-OBB worker over an AOI.

NOTE: no FK to public.items — detections come from the Esri World-Imagery
basemap, not a STAC item (same rationale as temporal_comparisons.left_item_id).

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-13
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GEOM = Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "detections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aoi_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("object_type", sa.String(), nullable=False),
        sa.Column("geometry", _GEOM, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("properties", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name="fk_detections_session_id"),
        sa.ForeignKeyConstraint(
            ["aoi_id"], ["aoi.id"], name="fk_detections_aoi_id", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_detections_aoi_id", "detections", ["aoi_id"])
    op.create_index("ix_detections_session_id", "detections", ["session_id"])
    op.execute("CREATE INDEX idx_detections_geometry ON detections USING gist (geometry)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_detections_geometry")
    op.drop_index("ix_detections_session_id", table_name="detections")
    op.drop_index("ix_detections_aoi_id", table_name="detections")
    op.drop_table("detections")
