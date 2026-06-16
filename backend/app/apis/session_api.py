import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.deps import get_db
from app.models.utils import NotFound
from app.schemas.session import SessionCreate, SessionResponse
from app.services.session_service import session_service

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    data: SessionCreate | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await session_service.create(db, data)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await session_service.get(db, session_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
