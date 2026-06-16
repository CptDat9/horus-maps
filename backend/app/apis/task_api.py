import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.deps import get_db
from app.models.utils import NotFound
from app.schemas.common import TaskCreate, TaskResponse
from app.services.task_service import task_service

router = APIRouter(prefix="/api/sessions/{session_id}/tasks", tags=["Tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    session_id: uuid.UUID,
    task_data: TaskCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await task_service.create(db, session_id, task_data)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    session_id: uuid.UUID,
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    try:
        task = await task_service.get(db, task_id)
        if task.session_id != session_id:
            raise NotFound(f"Task {task_id} not found")
        return task
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    session_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    tasks, _ = await task_service.list_by_session(db, session_id, skip, limit)
    return tasks
