import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.databases.base import Base


class TemporalComparison(Base):
    __tablename__ = "temporal_comparisons"
    __table_args__ = (
        Index("ix_temporal_comparisons_aoi_id", "aoi_id"),
        Index("ix_temporal_comparisons_session_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False
    )
    aoi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aoi.id", ondelete="CASCADE"), nullable=False
    )
    # BUG FIX: no ForeignKey to public.items. STAC items live in the PgSTAC
    # schema or a remote catalog (Earth Search) that this app does not own, so a
    # FK against the (empty) public.items table caused IntegrityError on every
    # comparison insert. Item IDs are opaque catalog identifiers.
    left_item_id: Mapped[str] = mapped_column(String, nullable=False)
    right_item_id: Mapped[str] = mapped_column(String, nullable=False)
    comparison_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
