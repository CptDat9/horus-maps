"""
Session-scoped fixed-window rate limiter (Redis-backed, fail-open).

Design:
- Only *mutating* requests (POST/PUT/PATCH/DELETE) are throttled. Reads — map
  tiles, layer/STAC lookups, SSE, health, docs — are never limited, so map
  browsing stays smooth and we don't create a Redis key per tile.
- The window is keyed per session (X-Session-ID), not per path, so the limit is
  a real global budget rather than a free pass for every distinct URL.
- Heavy domain operations (AOI extract, temporal comparison, detection) are
  offloaded to RabbitMQ at the *endpoint* layer (task_manager), which is the
  correct place — the middleware only protects the API surface.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.configs.config import rate_limit_config
from app.utils.logger_utils import get_logger
from app.services.cache_service import cache_service

logger = get_logger("RateLimitMiddleware")

_EXEMPT_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/ws", "/api/sse")
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method not in _WRITE_METHODS or any(
            path.startswith(p) for p in _EXEMPT_PREFIXES
        ):
            return await call_next(request)

        session_id = request.headers.get("X-Session-ID", "anonymous")
        key = f"rate:{session_id}"

        try:

            current = await cache_service.client.incr(key)
            if current == 1:
                await cache_service.client.expire(key, rate_limit_config.WINDOW_SECS)
            ttl = await cache_service.client.ttl(key)
        except Exception as err:
            logger.warning("Rate limit Redis error (%s), allowing request", err)
            return await call_next(request)

        if current > rate_limit_config.NORMAL_LIMIT:
            retry_after = ttl if ttl and ttl > 0 else rate_limit_config.WINDOW_SECS
            logger.warning("Rate limited: session=%s count=%s", session_id, current)
            return JSONResponse(
                status_code=429,
                content={"detail": "Quá nhiều yêu cầu. Vui lòng thử lại sau."},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(rate_limit_config.NORMAL_LIMIT),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        remaining = max(0, rate_limit_config.NORMAL_LIMIT - current)
        response.headers["X-RateLimit-Limit"] = str(rate_limit_config.NORMAL_LIMIT)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
