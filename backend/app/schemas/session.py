import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class SessionCreate(BaseModel):
    metadata: Optional[dict] = Field(None)
    ttl_hours: int = Field(24, ge=1, le=720)


class SessionResponse(BaseModel):
    id: uuid.UUID
    session_id: str
    metadata: Optional[dict] = Field(None, validation_alias="meta")
    created_at: datetime
    last_accessed: datetime
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
