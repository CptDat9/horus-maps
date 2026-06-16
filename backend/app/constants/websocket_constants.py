import uuid


class WSChannels:
    TASK_PROGRESS = "task_progress"
    MAP_UPDATE = "map_update"


# Redis pub/sub channel carrying status updates for a single task.
TASK_CHANNEL_PREFIX = "task"


def task_channel(task_id: uuid.UUID | str) -> str:
    return f"{TASK_CHANNEL_PREFIX}:{task_id}"
