import uuid
from typing import Optional, Dict, Any

from app.constants.websocket_constants import task_channel
from app.utils.logger_utils import get_logger
from app.databases.postgres import AsyncSessionLocal
from app.schemas.common import TaskCreate
from app.services.cache_service import cache_service
from app.services.task_service import task_service
from app.services.rabbitmq_service import rabbitmq_service

logger = get_logger("TaskManager")


class TaskManager:
    async def create_task(
        self,
        session_id: uuid.UUID,
        task_type: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a DB task record and publish to RabbitMQ."""
        async with AsyncSessionLocal() as db:
            task = await task_service.create(
                db=db,
                session_id=session_id,
                task_data=TaskCreate(task_type=task_type, payload=payload),
            )

            await rabbitmq_service.publish_task(
                task_type=task_type,
                payload={
                    "task_id": str(task.id),
                    "session_id": str(session_id),
                    **payload,
                },
            )

            return {
                "task_id": str(task.id),
                "status": task.status,
                "message": "Task đã được đưa vào hàng đợi xử lý",
            }

    async def update_task_status(
        self,
        task_id: uuid.UUID,
        status: str,
        result: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> None:
        async with AsyncSessionLocal() as db:
            task = await task_service.update_status(db, task_id, status, result, error_message)

        # Bridge worker → API WebSocket clients via Redis pub/sub. The worker runs
        # in a separate process from the API, so an in-memory broadcast can't
        # reach connected sockets — Redis is the cross-process channel.
        try:
            await cache_service.publish(
                task_channel(task_id),
                {
                    "task_id": str(task_id),
                    "status": task.status,
                    "result": task.result,
                    "error_message": task.error_message,
                    "updated_at": task.updated_at.isoformat() if task.updated_at else None,
                },
            )
        except Exception as e:
            logger.warning("Could not publish task update for %s: %s", task_id, e)

    async def process_task(self, task_id: uuid.UUID, task_type: str, payload: Dict[str, Any]) -> None:
        """Entry point called by the worker. Delegates to task_handlers."""
        from app.workers.task_handlers import task_handlers

        try:
            await self.update_task_status(task_id, "running")
            await task_handlers.dispatch(task_id, task_type, payload)
        except Exception as e:
            logger.error(f"Task {task_id} failed at manager level: {e}")
            await self.update_task_status(task_id, "failed", error_message=str(e))


task_manager = TaskManager()
