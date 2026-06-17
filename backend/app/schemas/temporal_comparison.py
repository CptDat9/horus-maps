import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class TemporalComparisonCreate(BaseModel):
    left_item_id: str = Field(...)
    right_item_id: str = Field(...)
    metadata: Optional[dict] = Field(None)


class TemporalComparisonResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    aoi_id: uuid.UUID
    left_item_id: str
    right_item_id: str
    status: str
    task_id: Optional[uuid.UUID] = None
    comparison_result: Optional[dict] = None
    metadata: Optional[dict] = Field(None, validation_alias="meta")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
