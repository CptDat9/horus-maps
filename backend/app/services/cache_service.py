import json
from typing import Any, Awaitable, Callable, Optional
from redis.asyncio import Redis, from_url
from app.databases.redis_cached import RedisCache
from app.configs.config import RedisConfig
from app.utils.logger_utils import get_logger

logger = get_logger("CacheService")

class CacheService(RedisCache):
    def __init__(self, connection_url: Optional[str] = None):
        super().__init__(connection_url)
        self.binary_client: Optional[Redis] = None
        self._url = connection_url or RedisConfig.get_connection_url()

    async def connect(self):
        await super().connect()

        self.binary_client = from_url(
            self._url or RedisConfig.get_connection_url(),
            decode_responses=False,
            max_connections=50,
        )

        await self.binary_client.ping()
        logger.info("Redis Binary Client initialized successfully.")

    async def disconnect(self):
        """Đóng an toàn cả 2 cụm connection pools"""
        await super().disconnect()
        if self.binary_client:
            await self.binary_client.aclose()
            logger.info("Redis Binary Client disconnected.")


    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """hàm xử lý String / JSON (Kế thừa và tối ưu hóa an toàn)"""
        if not self.client:
            raise RuntimeError("Redis Client chưa được kết nối.")
        try:
            string_value = (
                json.dumps(value, default=str)
                if isinstance(value, (dict, list))
                else str(value)
            )
            return await self.client.set(key, string_value, ex=expire)
        except Exception as e:
            logger.error(f"Lỗi ghi Cache (String) với key={key}: {str(e)}")
            return False

    async def get_bytes(self, key: str) -> Optional[bytes]:
        """Lấy luồng dữ liệu bytes nguyên bản (Không qua giải mã chuỗi)"""
        if not self.binary_client:
            raise RuntimeError("Redis Binary Client chưa được kết nối.")
        try:
            return await self.binary_client.get(key)
        except Exception as e:
            logger.error(f"Lỗi đọc Cache (Bytes) với key={key}: {str(e)}")
            return None

    async def set_bytes(self, key: str, value: bytes, expire: Optional[int] = None) -> bool:
        """Ghi trực tiếp chuỗi bytes của ảnh vào bộ nhớ ram"""
        if not self.binary_client:
            raise RuntimeError("Redis Binary Client chưa được kết nối.")
        try:
            return await self.binary_client.set(key, value, ex=expire)
        except Exception as e:
            logger.error(f"Lỗi ghi Cache (Bytes) với key={key}: {str(e)}")
            return False

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        expire: Optional[int] = None,
    ) -> Any:
        """Read-through cache for JSON values: return the cached value, else call
        the async ``factory``, cache its result, and return it. Cache faults
        (Redis down, serialization) never block the caller — the freshly computed
        value is always returned."""
        try:
            cached = await self.get(key)
            if cached is not None:
                return cached
        except Exception as e:
            logger.warning(f"Cache read failed for key={key}: {e}")

        value = await factory()
        try:
            await self.set(key, value, expire=expire)
        except Exception as e:
            logger.warning(f"Cache write failed for key={key}: {e}")
        return value


cache_service = CacheService()