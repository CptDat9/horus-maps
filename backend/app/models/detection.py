import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Float, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geometry

from app.databases.base import Base


class Detection(Base):
    """One detected object (an oriented bounding box) over an AOI.

    No FK to `items`: detections are produced from the high-resolution Esri
    World-Imagery basemap, not from a STAC item, so there is no catalog id to
    reference (same rationale as temporal_comparisons.left_item_id).
    """

    __tablename__ = "detections"
    __table_args__ = (
        Index("ix_detections_aoi_id", "aoi_id"),
        Index("ix_detections_session_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False
    )
    aoi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aoi.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("detection_runs.id", ondelete="CASCADE"), nullable=True
    )
    object_type: Mapped[str] = mapped_column(String, nullable=False)
    geometry = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
