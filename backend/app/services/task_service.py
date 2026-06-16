import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.utils import NotFound
from app.schemas.common import TaskCreate
from app.services.session_service import session_service


class TaskService:
    async def create(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        task_data: TaskCreate,
    ) -> Task:
        await session_service.ensure(db, session_id)
        task = Task(
            session_id=session_id,
            task_type=task_data.task_type,
            status="pending",
            payload=task_data.payload,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task

    async def get(self, db: AsyncSession, task_id: uuid.UUID) -> Task:
        task = await db.get(Task, task_id)
        if not task:
            raise NotFound(f"Task {task_id} not found")
        return task

    async def list_by_session(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[list[Task], int]:
        count_stmt = select(func.count(Task.id)).where(Task.session_id == session_id)
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = (
            select(Task)
            .where(Task.session_id == session_id)
            .offset(skip)
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return list(rows), total

    async def update_status(
        self,
        db: AsyncSession,
        task_id: uuid.UUID,
        status: str,
        result: dict | None = None,
        error_message: str | None = None,
    ) -> Task:
        task = await self.get(db, task_id)
        task.status = status
        now = datetime.now(timezone.utc)

        if status == "running":
            task.started_at = now
        elif status == "completed":
            task.completed_at = now
            task.result = result
        elif status == "failed":
            task.completed_at = now
            task.error_message = error_message

        await db.commit()
        await db.refresh(task)
        return task


task_service = TaskService()
