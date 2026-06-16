import json

from typing import Optional, Any, List, cast
from redis.asyncio import Redis, from_url
from app.utils.logger_utils import get_logger
from app.configs.config import RedisConfig

logger = get_logger("Redis Cache")


class RedisCache:
    def __init__(self, connection_url: Optional[str] = None):
        self.connection_url = connection_url
        self.client: Redis | None = None

    async def connect(self):
        client = cast(
            Redis,
            from_url(
                self.connection_url or RedisConfig.get_connection_url(),
                encoding="utf-8",
                decode_responses=True,
            ),
        )

        await client.ping()
        self.client = client
        logger.info("Redis connected")

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.client:
            await self.client.aclose()
            logger.info("Redis disconnected")

    async def get(self, key: str) -> Optional[Any]:
        if self.client is None:
            raise RuntimeError("Redis not connected")

        value = await self.client.get(key)

        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value

        return None

    async def delete(self, key: str) -> int:
        """Delete a cache key (no-op if Redis is unavailable)."""
        if self.client is None:
            return 0
        return await self.client.delete(key)

    async def publish(self, channel: str, message: Any) -> int:
        """Publish to a Redis pub/sub channel (used to bridge worker → API WS)."""
        if self.client is None:
            raise RuntimeError("Redis not connected")
        payload = message if isinstance(message, str) else json.dumps(message)
        return await self.client.publish(channel, payload)

    def pubsub(self):
        if self.client is None:
            raise RuntimeError("Redis not connected")
        return self.client.pubsub()
