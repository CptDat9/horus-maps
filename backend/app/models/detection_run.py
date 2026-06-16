import uuid
from datetime import datetime

from sqlalchemy import Integer, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.databases.base import Base


class DetectionRun(Base):
    """One object-detection run over an AOI — the history unit. Detections from
    this run link back via Detection.run_id."""

    __tablename__ = "detection_runs"
    __table_args__ = (Index("ix_detection_runs_aoi_id", "aoi_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False
    )
    aoi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aoi.id", ondelete="CASCADE"), nullable=False
    )
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    classes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
