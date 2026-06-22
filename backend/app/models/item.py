from datetime import datetime

from sqlalchemy import Text, DateTime, ForeignKey, Index, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2 import Geometry

from app.databases.base import Base
# Luu JSON STAC item

class Item(Base):
    """
    Optional app-level fallback catalog (public.items). The canonical STAC
    catalog lives in the pgstac schema / a remote STAC API; this table is only
    queried as a last resort and may be empty.
    """
    __tablename__ = "items"
    __table_args__ = (
        Index("ix_items_collection_id", "collection_id"),
        Index("ix_items_datetime", "datetime"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    collection_id: Mapped[str] = mapped_column(
        Text, ForeignKey("collections.id"), nullable=False
    )
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    geometry = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False #4326: he toa do WGS84 (GPS)
    )
    datetime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
