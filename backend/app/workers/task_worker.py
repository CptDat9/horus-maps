import asyncio
import json
import signal
import uuid

from aio_pika import connect_robust
from aio_pika.abc import AbstractIncomingMessage

from app.configs.config import rabbitmq_config
from app.services.cache_service import cache_service
from app.services.rabbitmq_service import setup_topology
from app.utils.logger_utils import get_logger
from app.workers.task_manager import task_manager

logger = get_logger("TaskWorker")


class TaskWorker:
    def __init__(self) -> None:
        self.connection = None
        self.channel = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        logger.info("Horus Maps Task Worker starting...")
        await cache_service.connect()
        self.connection = await connect_robust(rabbitmq_config.URL)
        self.channel, _, queue = await setup_topology(self.connection, publisher_confirms=False)
        await self.channel.set_qos(prefetch_count=rabbitmq_config.PREFETCH)
        await queue.consume(self.process_message)
        logger.info("Worker listening on queue: %s", rabbitmq_config.QUEUE_HEAVY)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._stop.set)
            except NotImplementedError:
                pass

        await self._stop.wait()
        await self.stop()

    async def process_message(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False):
            body = json.loads(message.body.decode())
            task_type = body.get("task_type")
            payload = body.get("payload", {})
            raw_task_id = payload.get("task_id")

            if not raw_task_id:
                logger.error("Message has no task_id, dropping: type=%s", task_type)
                return

            task_id = uuid.UUID(raw_task_id)
            logger.info("Processing task %s | type=%s", task_id, task_type)
            await task_manager.process_task(task_id, task_type, payload)

    async def stop(self) -> None:
        logger.info("Stopping worker...")
        self._stop.set()
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
        try:
            await cache_service.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(TaskWorker().start())
