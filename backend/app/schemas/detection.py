import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

ObjectClass = Literal["all", "aircraft", "vessels", "vehicles"]


class DetectionJobCreate(BaseModel):
    """Request to run object detection over an AOI (queued as a background task)."""

    # Explicit DOTA class ids to detect. If omitted, falls back to object_class.
    classes: Optional[list[int]] = Field(None)
    object_class: ObjectClass = Field("all")
    # The map's active base-layer XYZ tile template — detection runs on the SAME
    # imagery the user is viewing. Falls back to the default source if invalid.
    tile_url: Optional[str] = Field(None)
    zoom: Optional[int] = Field(None, ge=14, le=22)
    confidence: float = Field(0.2, ge=0.05, le=0.95)
    iou: float = Field(0.45, ge=0.1, le=0.9)

    @field_validator("classes")
    @classmethod
    def _check_classes(cls, v):
        if v is None:
            return v
        v = sorted({int(c) for c in v if 0 <= int(c) <= 14})
        return v or None


class DetectionCreate(BaseModel):
    """Internal: one persisted detection (written by the worker, not the client)."""

    object_type: str = Field(...)
    geometry: dict = Field(...)
    confidence: float = Field(..., ge=0.0, le=1.0)
    properties: Optional[dict] = Field(None)


class DetectionResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    aoi_id: uuid.UUID
    object_type: str
    geometry: dict
    confidence: float
    properties: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DetectionListResponse(BaseModel):
    items: list[DetectionResponse]
    total: int
    run_id: Optional[uuid.UUID] = None


class DetectionRunResponse(BaseModel):
    id: uuid.UUID
    aoi_id: uuid.UUID
    count: int
    classes: Optional[list[int]] = None
    meta: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DetectionRunListResponse(BaseModel):
    items: list[DetectionRunResponse]
    total: int


class DetectionJobResponse(BaseModel):
    """Returned when a detection job is queued — the client polls the task/SSE."""

    task_id: str
    status: str
    aoi_id: uuid.UUID
    message: str
