import uuid
from typing import Dict, Set

from fastapi import WebSocket

from app.utils.logger_utils import get_logger

logger = get_logger("WebSocketManager")


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[uuid.UUID, Set[WebSocket]] = {}

    async def connect(self, task_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        if task_id not in self.active_connections: 
            self.active_connections[task_id] = set()
        self.active_connections[task_id].add(websocket)
        logger.info(f"WebSocket connected for task {task_id}")

    def disconnect(self, task_id: uuid.UUID, websocket: WebSocket) -> None:
        if task_id in self.active_connections:
            self.active_connections[task_id].discard(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
        logger.info(f"WebSocket disconnected for task {task_id}")

    async def broadcast(self, task_id: uuid.UUID, message: dict) -> None:
        connections = self.active_connections.get(task_id, set())
        dead = set()
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            connections.discard(ws)


manager = ConnectionManager()
