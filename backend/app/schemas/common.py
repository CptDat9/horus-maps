import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class TaskCreate(BaseModel):
    task_type: str = Field(..., min_length=1)
    payload: Optional[dict] = None


class TaskResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    status: str
    task_type: str
    payload: Optional[dict] = None
    result: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int


class MapSearchRequest(BaseModel):
    collections: list[str] = Field(..., min_length=1)
    bbox: Optional[list[float]] = Field(None, description="[minx, miny, maxx, maxy]")
    geometry: Optional[dict] = None
    datetime: Optional[str] = None
    limit: int = Field(20, ge=1, le=100)


class MapLayerResponse(BaseModel):
    id: str
    name: str
    type: str
    url: str
    options: Optional[dict] = None
    is_active: bool
    display_order: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
