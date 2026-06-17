"""
Session-scoped fixed-window rate limiter (Redis-backed, fail-open).

Design:
- Only *mutating* requests (POST/PUT/PATCH/DELETE) are throttled. Reads — map
  tiles, layer/STAC lookups, SSE/WS, health, docs — are never limited, so map
  browsing stays smooth and we don't create a Redis key per tile.
- The window is keyed per session (path uses /api/sessions/{id}/…, falling back
  to the X-Session-ID header), so the limit is a real per-user budget rather
  than a free pass for every distinct URL.
- Two tiers (both from rate_limit_config), so a burst of legitimate background-
  task submissions isn't punished like an abusive flood:
    count <= NORMAL_LIMIT        → pass.
    NORMAL_LIMIT < count <= QUEUE_LIMIT
                                 → pass, but tag the response `X-RateLimit-Tier:
                                   degraded` so the client/UI knows it's near the
                                   ceiling. Heavy domain ops are already offloaded
                                   to RabbitMQ at the endpoint layer, so the work
                                   itself is queued regardless.
    count > QUEUE_LIMIT          → 429 with Retry-After.
"""
import re

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.configs.config import rate_limit_config
from app.utils.logger_utils import get_logger
from app.services.cache_service import cache_service

logger = get_logger("RateLimitMiddleware")

_EXEMPT_PREFIXES = (
    "/health", "/docs", "/redoc", "/openapi.json", "/ws", "/api/sse",
    "/api/stac", "/api/maps/search", "/api/maps/collections",
)
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_SESSION_IN_PATH = re.compile(r"/api/sessions/([^/]+)")


def _session_key(request: Request) -> str:
    match = _SESSION_IN_PATH.search(request.url.path)
    if match:
        return match.group(1)
    return request.headers.get("X-Session-ID", "anonymous")


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method not in _WRITE_METHODS or any(
            path.startswith(p) for p in _EXEMPT_PREFIXES
        ):
            return await call_next(request)

        normal = rate_limit_config.NORMAL_LIMIT
        ceiling = max(rate_limit_config.QUEUE_LIMIT, normal)
        key = f"rate:{_session_key(request)}"

        try:
            count, ttl = await cache_service.incr_with_ttl(key, rate_limit_config.WINDOW_SECS)
        except Exception as err:
            logger.warning("Rate limit Redis error (%s), allowing request", err)
            return await call_next(request)

        if count > ceiling:
            retry_after = ttl if ttl and ttl > 0 else rate_limit_config.WINDOW_SECS
            logger.warning("Rate limited (hard): session=%s count=%s", key, count)
            return JSONResponse(
                status_code=429,
                content={"detail": "Quá nhiều yêu cầu. Vui lòng thử lại sau."},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(normal),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(normal)
        response.headers["X-RateLimit-Remaining"] = str(max(0, normal - count))
        if count > normal:
            response.headers["X-RateLimit-Tier"] = "degraded"
        return response
