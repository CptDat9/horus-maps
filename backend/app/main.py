from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.apis import (
    aoi_api,
    comparison_api,
    detection_api,
    map_api,
    measurement_api,
    session_api,
    sse_api,
    stac_api,
    task_api,
    websocket_api,
)
from app.configs.config import Config
from app.databases.postgres import AsyncSessionLocal
from app.services.cache_service import cache_service
from app.services.map_service import map_service
from app.middleware.rate_limit import RateLimitMiddleware
from app.services.rabbitmq_service import rabbitmq_service
from app.services.stac_client import stac_client
from app.utils.logger_utils import get_logger

config = Config()
logger = get_logger("App")


@asynccontextmanager
async def lifespan(app: FastAPI):
    for name, coro in (("redis", cache_service.connect()), ("rabbitmq", rabbitmq_service.connect())):
        try:
            await coro
        except Exception as e:
            logger.error("Startup: %s unavailable: %s", name, e)
    try:
        async with AsyncSessionLocal() as db:
            await map_service.seed_defaults(db)
    except Exception as e:
        logger.error("Startup: could not seed map layers: %s", e)
    yield
    await cache_service.disconnect()
    await rabbitmq_service.close()
    await stac_client.close()
    await stac_api.close()


app = FastAPI(
    title=config.API_TITLE,
    description=config.API_DESCRIPTION,
    version=config.API_VERSION,
    lifespan=lifespan,
)
app.add_middleware(RateLimitMiddleware)
_origins = config.CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(session_api.router)
app.include_router(aoi_api.router)
app.include_router(measurement_api.router)
app.include_router(comparison_api.router)
app.include_router(task_api.router)
app.include_router(detection_api.router)
app.include_router(map_api.router)
app.include_router(stac_api.router)
app.include_router(sse_api.router)
app.include_router(websocket_api.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "horus-maps-backend"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.RUN_SETTING["host"],
        port=config.RUN_SETTING["port"],
        reload=config.RUN_SETTING["auto_reload"],
        workers=config.RUN_SETTING["workers"],
    )
