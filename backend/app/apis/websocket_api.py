import asyncio
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.constants.websocket_constants import task_channel
from app.databases.postgres import AsyncSessionLocal
from app.services.cache_service import cache_service
from app.services.task_service import task_service
from app.utils.logger_utils import get_logger

logger = get_logger("WebSocketAPI")
router = APIRouter(prefix="/ws", tags=["WebSocket"])

_TERMINAL = {"completed", "failed"}


async def _current_state(task_id: uuid.UUID) -> dict | None:
    try:
        async with AsyncSessionLocal() as db:
            task = await task_service.get(db, task_id)
        return {
            "task_id": str(task_id),
            "status": task.status,
            "result": task.result,
            "error_message": task.error_message,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }
    except Exception:
        return None


@router.websocket("/tasks/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: uuid.UUID):
    """
    Push task status to the client. Subscribes to the Redis channel that the
    worker publishes to (cross-process), after sending the current DB state so a
    client that connects late still gets the latest status immediately.
    """
    await websocket.accept()

    pubsub = cache_service.pubsub()
    await pubsub.subscribe(task_channel(task_id))
    try:
        state = await _current_state(task_id)
        if state:
            await websocket.send_json(state)
            if state["status"] in _TERMINAL:
                return

        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
            if msg is None:
                # Keep-alive so proxies / clients don't drop an idle socket.
                await websocket.send_json({"type": "ping"})
                continue
            data = msg["data"]
            await websocket.send_text(data if isinstance(data, str) else json.dumps(data))
            try:
                if json.loads(data).get("status") in _TERMINAL:
                    break
            except (json.JSONDecodeError, TypeError):
                pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WebSocket error for task %s: %s", task_id, e)
    finally:
        try:
            await pubsub.unsubscribe(task_channel(task_id))
            await pubsub.aclose()
        except Exception:
            pass
        try:
            await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
        except Exception:
            pass
