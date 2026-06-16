import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class MeasurementCreate(BaseModel):
    type: str = Field(..., description="area|perimeter|distance|height")
    unit: str = Field(..., description="sqkm|km|m")
    geometry: Optional[dict] = Field(None)
    metadata: Optional[dict] = Field(None)


class MeasurementResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    aoi_id: uuid.UUID
    type: str
    value: float
    unit: str
    geometry: Optional[dict] = None
    metadata: Optional[dict] = Field(None, validation_alias="meta")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MeasurementListResponse(BaseModel):
    items: list[MeasurementResponse]
    total: int
