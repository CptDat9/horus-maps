import os

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | bool | None, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_list(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [v.strip() for v in value.split(",") if v.strip()]


class Config:
    # ---- HTTP server -------------------------------------------------------
    # NOTE: the frontend dev proxy targets http://localhost:8000, so the API
    # MUST listen on 8000 by default (was 8080, which collided with stac-fastapi).
    RUN_SETTING = {
        "host": os.getenv("SERVER_HOST", "0.0.0.0"),
        "port": int(os.getenv("SERVER_PORT", 8000)),
        "debug": _as_bool(os.getenv("DEBUG"), False),
        "access_log": False,
        "auto_reload": _as_bool(os.getenv("SERVER_RELOAD"), True),
        "workers": int(os.getenv("SERVER_WORKERS", 1)),
    }

    RESPONSE_TIMEOUT = 20  # seconds

    # ---- OpenAPI metadata --------------------------------------------------
    API_VERSION = os.getenv("API_VERSION", "0.1.0")
    API_TITLE = os.getenv("API_TITLE", "Horus Maps API")
    API_DESCRIPTION = os.getenv("API_DESCRIPTION", "GIS / Remote-Sensing backend for Horus Maps")
    API_CONTACT_EMAIL = os.getenv("API_CONTACT_EMAIL", "hoadd.hd4@gmail.com")

    # ---- Map defaults ------------------------------------------------------
    DEFAULT_MAP_CENTER_LAT: float = float(os.getenv("DEFAULT_MAP_CENTER_LAT", 16.0))
    DEFAULT_MAP_CENTER_LNG: float = float(os.getenv("DEFAULT_MAP_CENTER_LNG", 106.0))
    DEFAULT_MAP_ZOOM: int = int(os.getenv("DEFAULT_MAP_ZOOM", 6))

    # ---- Tile / STAC services ---------------------------------------------
    # Titiler (raster tiler) — renders COG tiles. Default dev port 8081.
    TITILER_URL: str = os.getenv("TITILER_URL", "http://localhost:8081").rstrip("/")
    # Browser-facing Titiler origin. Server-side (the /api/tiles proxy) uses
    # TITILER_URL = http://titiler:80 inside Docker, but tile-URL templates handed
    # to the browser (comparison swipe) need a host-reachable origin. Defaults to
    # TITILER_URL so native/single-host runs need no extra config.
    TITILER_PUBLIC_URL: str = os.getenv("TITILER_PUBLIC_URL", TITILER_URL).rstrip("/")
    # TileMatrixSet path segment required by recent Titiler releases
    # (/cog/tiles/{tileMatrixSetId}/{z}/{x}/{y}).
    TITILER_TMS: str = os.getenv("TITILER_TMS", "WebMercatorQuad")

    # Local stac-fastapi-pgstac instance (optional — may be empty / not migrated).
    STAC_API_URL: str = os.getenv("STAC_API_URL", "http://localhost:8080").rstrip("/")

    # Remote STAC catalog used as the authoritative source for Sentinel-2.
    # Element 84 Earth Search v1 exposes public Sentinel-2 L2A COGs (no signing,
    # no ingestion required). This is what makes Sentinel work out of the box.
    STAC_SEARCH_URL: str = os.getenv(
        "STAC_SEARCH_URL", "https://earth-search.aws.element84.com/v1"
    ).rstrip("/")
    STAC_DEFAULT_COLLECTION: str = os.getenv("STAC_DEFAULT_COLLECTION", "sentinel-2-l2a")
    STAC_MAX_CLOUD_COVER: int = int(os.getenv("STAC_MAX_CLOUD_COVER", 30))
    # Try the local PgSTAC schema first; fall back to the remote STAC API.
    STAC_USE_LOCAL: bool = _as_bool(os.getenv("STAC_USE_LOCAL"), True)
    STAC_USE_REMOTE: bool = _as_bool(os.getenv("STAC_USE_REMOTE"), True)
    STAC_HTTP_TIMEOUT: float = float(os.getenv("STAC_HTTP_TIMEOUT", 20.0))

    # ---- AI object detection (YOLO-OBB) ------------------------------------
    # Weights ship with the repo (ml/yolo11s-obb.pt). The worker resolves the
    # path from this env var; in Docker the file is copied to /app/models.
    DETECTION_MODEL_PATH: str = os.getenv(
        "DETECTION_MODEL_PATH",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml", "yolo11s-obb.pt"),
    )
    # Guard rail: an AOI spanning too many tiles would download for minutes and
    # exhaust memory / time out. 400 lets a focused AOI reach z20 — the sweet
    # spot (verified ~107 vehicles in ~170s). z21 over a large AOI was too slow
    # on CPU, so vehicles cap at z20 here; draw a tighter AOI for more detail.
    DETECTION_MAX_TILES: int = int(os.getenv("DETECTION_MAX_TILES", 400))
    # Annotated detection previews (imagery + drawn boxes) are written here by the
    # worker and served by the API. In Docker this is a shared volume; for native
    # runs api+worker share the filesystem so the default local path works.
    DETECTION_OUTPUT_DIR: str = os.getenv(
        "DETECTION_OUTPUT_DIR",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "detections")),
    )

    # ---- SQL debug ---------------------------------------------------------
    SQL_ECHO: bool = _as_bool(os.getenv("SQL_ECHO"), False)

    # ---- DB connection pool ------------------------------------------------
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", 20))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", 30))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", 10))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", 1800))

    # ---- CORS --------------------------------------------------------------
    CORS_ORIGINS: list = _as_list(os.getenv("CORS_ORIGINS"), ["*"])

    # ---- Cache TTLs (seconds) ---------------------------------------------
    TILE_CACHE_TTL: int = int(os.getenv("TILE_CACHE_TTL", 86400))    # 1 day
    LAYER_CACHE_TTL: int = int(os.getenv("LAYER_CACHE_TTL", 3600))   # 1 hour
    ITEM_CACHE_TTL: int = int(os.getenv("ITEM_CACHE_TTL", 600))      # 10 min


class RedisConfig:
    HOST = os.getenv("REDIS_HOST", "localhost")
    PORT = int(os.getenv("REDIS_PORT", 6379))
    DB = int(os.getenv("REDIS_DB", 0))
    PASSWORD = os.getenv("REDIS_PASSWORD", "")

    @classmethod
    def get_connection_url(cls) -> str:
        if cls.PASSWORD:
            return f"redis://:{cls.PASSWORD}@{cls.HOST}:{cls.PORT}/{cls.DB}"
        return f"redis://{cls.HOST}:{cls.PORT}/{cls.DB}"


class RabbitMQConfig:
    """Message-queue configuration."""
    URL = os.getenv("RABBITMQ_URL", "amqp://admin:admin@localhost:5672/")
    QUEUE_NAME = os.getenv("RABBITMQ_QUEUE", "horus_tasks")
    QUEUE_HEAVY = os.getenv("RABBITMQ_QUEUE_HEAVY", "horus_heavy_tasks")
    QUEUE_DLQ = os.getenv("RABBITMQ_QUEUE_DLQ", "horus_dead_letters")
    EXCHANGE = os.getenv("RABBITMQ_EXCHANGE", "horus_exchange")
    DLX = os.getenv("RABBITMQ_DLX", "horus_dlx")
    MAX_PRIORITY = int(os.getenv("RABBITMQ_MAX_PRIORITY", 10))
    PREFETCH = int(os.getenv("RABBITMQ_PREFETCH", 5))


class PostgresConfig:
    """PostgreSQL + PostGIS configuration."""
    USER = os.getenv("POSTGRES_USER", "postgres")
    PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    HOST = os.getenv("POSTGRES_HOST", "localhost")
    PORT = int(os.getenv("POSTGRES_PORT", 5432))
    DB = os.getenv("POSTGRES_DB", "horus_maps")

    @property
    def CONNECTION_URL(self) -> str:
        return f"postgresql+asyncpg://{self.USER}:{self.PASSWORD}@{self.HOST}:{self.PORT}/{self.DB}"


class RateLimitConfig:
    NORMAL_LIMIT = int(os.getenv("RATE_LIMIT_NORMAL", 60))   # ≤ this → pass through
    QUEUE_LIMIT = int(os.getenv("RATE_LIMIT_QUEUE", 120))    # ≤ this → queue heavy, 429 light
    WINDOW_SECS = int(os.getenv("RATE_LIMIT_WINDOW", 60))    # fixed window (seconds)


config = Config()
redis_config = RedisConfig()
postgres_config = PostgresConfig()
rabbitmq_config = RabbitMQConfig()
rate_limit_config = RateLimitConfig()
