from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.configs.config import PostgresConfig, Config

_pg = PostgresConfig()

engine = create_async_engine(
    _pg.CONNECTION_URL,
    echo=Config.SQL_ECHO,
    pool_size=Config.DB_POOL_SIZE,
    max_overflow=Config.DB_MAX_OVERFLOW,
    pool_timeout=Config.DB_POOL_TIMEOUT,
    pool_recycle=Config.DB_POOL_RECYCLE,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)