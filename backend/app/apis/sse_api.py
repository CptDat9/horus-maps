"""
Server-Sent Events (SSE) endpoint — push-based alternative to WebSocket.
Simpler for browser clients: no library needed, works via EventSource API.

Usage:
  const es = new EventSource(`/api/sse/tasks/${taskId}`);
  es.onmessage = (e) => console.log(JSON.parse(e.data));
  es.addEventListener('done', () => es.close());
"""

import asyncio
import json
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.constants.task_constants import TERMINAL_STATUSES
from app.databases.postgres import AsyncSessionLocal
from app.services.task_service import task_service
from app.utils.logger_utils import get_logger

logger = get_logger("SSE")
router = APIRouter(prefix="/api/sse", tags=["SSE"])

_POLL_INTERVAL = 2
_HEARTBEAT_EVERY = 15
_MAX_DURATION = 300


@router.get("/tasks/{task_id}")
async def task_sse(task_id: uuid.UUID, request: Request):
    """
    Stream task status updates via SSE until the task reaches a terminal state
    (completed / failed) or the client disconnects.
    """

    async def event_stream():
        last_status: str | None = None
        elapsed = 0

        while elapsed < _MAX_DURATION:
            if await request.is_disconnected():
                logger.info(f"SSE client disconnected for task {task_id}")
                break

            if elapsed > 0 and elapsed % _HEARTBEAT_EVERY == 0:
                yield ": ping\n\n"

            try:
                async with AsyncSessionLocal() as db:
                    task = await task_service.get(db, task_id)

                if task.status != last_status:
                    payload = {
                        "task_id": str(task_id),
                        "status": task.status,
                        "result": task.result,
                        "error_message": task.error_message,
                        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
                    }
                    event_name = "done" if task.status in TERMINAL_STATUSES else "update"

                    yield f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"
                    last_status = task.status

                    if task.status in TERMINAL_STATUSES:
                        break

            except Exception as e:
                error_payload = json.dumps({"error": str(e)})
                yield f"event: error\ndata: {error_payload}\n\n"
                break

            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL

        yield "event: stream_end\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
