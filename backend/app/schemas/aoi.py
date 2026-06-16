import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict
from geojson_pydantic import Polygon, MultiPolygon


class AOICreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = Field(None)
    geometry: Polygon | MultiPolygon = Field(...)
    properties: Optional[dict] = Field(None)


class AOIUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = Field(None)
    properties: Optional[dict] = Field(None)


class AOIResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    name: str
    description: Optional[str]
    properties: Optional[dict]
    geometry: dict
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AOIListResponse(BaseModel):
    items: list[AOIResponse]
    total: int
    page: int
    size: int
