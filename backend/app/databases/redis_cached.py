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


    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """Atomically increment a counter, returning the new value (None if down)."""
        if self.client is None:
            return None
        return await self.client.incrby(key, amount)

    async def expire(self, key: str, seconds: int) -> bool:
        if self.client is None:
            return False
        return bool(await self.client.expire(key, seconds))

    async def ttl(self, key: str) -> int:
        """Seconds left on a key's TTL; -1 = no expiry, -2 = missing/down."""
        if self.client is None:
            return -2
        return await self.client.ttl(key)

    async def incr_with_ttl(self, key: str, window_secs: int) -> tuple[int, int]:
        """Increment a fixed-window counter and ensure it expires after the window.
        Returns (count, ttl_seconds). On the first hit the TTL is set so the
        window rolls; returns (0, window_secs) when Redis is unavailable so the
        caller can fail open."""
        count = await self.incr(key)
        if count is None:
            return 0, window_secs
        if count == 1:
            await self.expire(key, window_secs)
            return count, window_secs
        ttl = await self.ttl(key)
        return count, (ttl if ttl and ttl > 0 else window_secs)

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
