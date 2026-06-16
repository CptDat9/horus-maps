import json
from typing import Any, Dict, Optional, Tuple

from aio_pika import ExchangeType, Message, connect_robust
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractQueue,
    AbstractRobustConnection,
)
from aio_pika.exceptions import ChannelPreconditionFailed

from app.configs.config import rabbitmq_config
from app.utils.logger_utils import get_logger

logger = get_logger("RabbitMQService")

_HEAVY_QUEUE_ARGS = {
    "x-max-priority": rabbitmq_config.MAX_PRIORITY,
    "x-dead-letter-exchange": rabbitmq_config.DLX,
}


async def _declare(channel: AbstractChannel) -> Tuple[AbstractExchange, AbstractQueue]:
    exchange = await channel.declare_exchange(
        rabbitmq_config.EXCHANGE, ExchangeType.TOPIC, durable=True
    )
    dlx = await channel.declare_exchange(rabbitmq_config.DLX, ExchangeType.FANOUT, durable=True)
    dlq = await channel.declare_queue(rabbitmq_config.QUEUE_DLQ, durable=True)
    await dlq.bind(dlx)

    queue = await channel.declare_queue(
        rabbitmq_config.QUEUE_HEAVY, durable=True, arguments=_HEAVY_QUEUE_ARGS
    )
    await queue.bind(exchange, routing_key="task.#")
    return exchange, queue


async def setup_topology(
    connection: AbstractRobustConnection, publisher_confirms: bool = True
) -> Tuple[AbstractChannel, AbstractExchange, AbstractQueue]:
    """
    Declare the shared exchange/queue topology and return (channel, exchange,
    heavy_queue). Used by both the API (publisher) and the worker (consumer) so
    they always agree on settings.

    Self-heals the common upgrade conflict: if `horus_heavy_tasks` already exists
    with different arguments (e.g. created before priority/DLX were added),
    Rabbit raises PRECONDITION_FAILED. RabbitMQ forbids changing a durable
    queue's args, so we delete the (empty, dev) queue and recreate it.
    """
    channel = await connection.channel(publisher_confirms=publisher_confirms)
    try:
        exchange, queue = await _declare(channel)
    except ChannelPreconditionFailed as e:
        logger.warning("Heavy queue args mismatch (%s) — recreating queue", e)
        channel = await connection.channel(publisher_confirms=publisher_confirms)
        await channel.queue_delete(rabbitmq_config.QUEUE_HEAVY)
        exchange, queue = await _declare(channel)
    return channel, exchange, queue


class RabbitMQService:
    def __init__(self) -> None:
        self.connection: Optional[AbstractRobustConnection] = None
        self.channel: Optional[AbstractChannel] = None
        self.exchange: Optional[AbstractExchange] = None

    async def connect(self) -> None:
        if self.connection and not self.connection.is_closed:
            return
        try:
            self.connection = await connect_robust(rabbitmq_config.URL)
            self.channel, self.exchange, _ = await setup_topology(self.connection)
            logger.info("Connected to RabbitMQ")
        except Exception as e:
            # Don't crash app startup if the broker is down — publish_task will
            # surface the error to callers, which degrade gracefully.
            self.connection = self.channel = self.exchange = None
            logger.error("RabbitMQ connect failed: %s", e)

    async def publish_task(
        self, task_type: str, payload: Dict[str, Any], priority: int = 1
    ) -> None:
        if not self.exchange or (self.connection and self.connection.is_closed):
            await self.connect()
        if not self.exchange:
            raise RuntimeError("RabbitMQ not connected")

        body = json.dumps({"task_type": task_type, "payload": payload}).encode()
        message = Message(
            body,
            delivery_mode=2,  # persistent
            priority=max(0, min(priority, rabbitmq_config.MAX_PRIORITY)),
            content_type="application/json",
        )
        await self.exchange.publish(message, routing_key=f"task.{task_type}")
        logger.info("Published task=%s priority=%s", task_type, priority)

    async def close(self) -> None:
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            logger.info("Closed RabbitMQ connection")


rabbitmq_service = RabbitMQService()
