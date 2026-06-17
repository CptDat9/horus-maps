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
    RUN_SETTING = {
        "host": os.getenv("SERVER_HOST", "0.0.0.0"),
        "port": int(os.getenv("SERVER_PORT", 8000)),
        "debug": _as_bool(os.getenv("DEBUG"), False),
        "access_log": False,
        "auto_reload": _as_bool(os.getenv("SERVER_RELOAD"), True),
        "workers": int(os.getenv("SERVER_WORKERS", 1)),
    }

    RESPONSE_TIMEOUT = 20

    API_VERSION = os.getenv("API_VERSION", "0.1.0")
    API_TITLE = os.getenv("API_TITLE", "Horus Maps API")
    API_DESCRIPTION = os.getenv("API_DESCRIPTION", "GIS / Remote-Sensing backend for Horus Maps")
    API_CONTACT_EMAIL = os.getenv("API_CONTACT_EMAIL", "hoadd.hd4@gmail.com")

    DEFAULT_MAP_CENTER_LAT: float = float(os.getenv("DEFAULT_MAP_CENTER_LAT", 16.0))
    DEFAULT_MAP_CENTER_LNG: float = float(os.getenv("DEFAULT_MAP_CENTER_LNG", 106.0))
    DEFAULT_MAP_ZOOM: int = int(os.getenv("DEFAULT_MAP_ZOOM", 6))

    TITILER_URL: str = os.getenv("TITILER_URL", "http://localhost:8081").rstrip("/")
    TITILER_PUBLIC_URL: str = os.getenv("TITILER_PUBLIC_URL", TITILER_URL).rstrip("/")
    TITILER_TMS: str = os.getenv("TITILER_TMS", "WebMercatorQuad")
    TITILER_RESAMPLING: str = os.getenv("TITILER_RESAMPLING", "bilinear")
    STAC_VISUAL_COLOR_FORMULA: str = os.getenv(
        "STAC_VISUAL_COLOR_FORMULA",
        "gamma RGB 1.05 sigmoidal RGB 4 0.5 saturation 1.15",
    )

    STAC_API_URL: str = os.getenv("STAC_API_URL", "http://localhost:8080").rstrip("/")

    STAC_SEARCH_URL: str = os.getenv(
        "STAC_SEARCH_URL", "https://earth-search.aws.element84.com/v1"
    ).rstrip("/")
    STAC_DEFAULT_COLLECTION: str = os.getenv("STAC_DEFAULT_COLLECTION", "sentinel-2-l2a")
    STAC_MAX_CLOUD_COVER: int = int(os.getenv("STAC_MAX_CLOUD_COVER", 30))
    STAC_USE_LOCAL: bool = _as_bool(os.getenv("STAC_USE_LOCAL"), True)
    STAC_USE_REMOTE: bool = _as_bool(os.getenv("STAC_USE_REMOTE"), True)
    STAC_HTTP_TIMEOUT: float = float(os.getenv("STAC_HTTP_TIMEOUT", 20.0))

    DETECTION_MODEL_PATH: str = os.getenv(
        "DETECTION_MODEL_PATH",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml", "yolo11s-obb.pt"),
    )
    DETECTION_MAX_TILES: int = int(os.getenv("DETECTION_MAX_TILES", 400))
    DETECTION_OUTPUT_DIR: str = os.getenv(
        "DETECTION_OUTPUT_DIR",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "detections")),
    )

    SQL_ECHO: bool = _as_bool(os.getenv("SQL_ECHO"), False)

    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", 20))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", 30))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", 10))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", 1800))

    CORS_ORIGINS: list = _as_list(os.getenv("CORS_ORIGINS"), ["*"])

    TILE_CACHE_TTL: int = int(os.getenv("TILE_CACHE_TTL", 86400))
    LAYER_CACHE_TTL: int = int(os.getenv("LAYER_CACHE_TTL", 3600))
    ITEM_CACHE_TTL: int = int(os.getenv("ITEM_CACHE_TTL", 600))


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
    NORMAL_LIMIT = int(os.getenv("RATE_LIMIT_NORMAL", 60))
    QUEUE_LIMIT = int(os.getenv("RATE_LIMIT_QUEUE", 120))
    WINDOW_SECS = int(os.getenv("RATE_LIMIT_WINDOW", 60))


config = Config()
redis_config = RedisConfig()
postgres_config = PostgresConfig()
rabbitmq_config = RabbitMQConfig()
rate_limit_config = RateLimitConfig()
