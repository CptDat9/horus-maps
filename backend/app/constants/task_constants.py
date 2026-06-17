"""
Central definitions for the async-task subsystem.

One source of truth for task-type and status strings (previously scattered as
magic strings across the API endpoints, the worker dispatch, and the SSE/WS
status checks) plus the RabbitMQ priority each task type is published with.

The heavy queue is declared with ``x-max-priority`` (see rabbitmq_service), so
quick, interactive jobs (a temporal comparison, an AOI scene lookup) are
delivered ahead of a slow CPU-bound detection run when both are waiting — the
map UI stays responsive even while a long detection is in flight.
"""
from enum import Enum


class TaskType(str, Enum):
    EXTRACT_AOI = "extract_aoi"
    TEMPORAL_COMPARISON = "temporal_comparison"
    DETECTION = "detection"
    SEARCH_ITEMS = "search_items"
    GET_COLLECTIONS = "get_collections"
    REFRESH_LAYERS = "refresh_layers"
    HEAVY_REQUEST = "heavy_request"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL_STATUSES: frozenset[str] = frozenset(
    {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value}
)

_DEFAULT_PRIORITY = 5
TASK_PRIORITY: dict[str, int] = {
    TaskType.TEMPORAL_COMPARISON.value: 8,
    TaskType.EXTRACT_AOI.value: 7,
    TaskType.SEARCH_ITEMS.value: 6,
    TaskType.GET_COLLECTIONS.value: 6,
    TaskType.REFRESH_LAYERS.value: 5,
    TaskType.DETECTION.value: 3,
    TaskType.HEAVY_REQUEST.value: 1,
}


def priority_for(task_type: str) -> int:
    """RabbitMQ priority for a task type (falls back to a neutral default)."""
    return TASK_PRIORITY.get(task_type, _DEFAULT_PRIORITY)
