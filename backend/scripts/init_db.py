"""
Initialize the application schema by running Alembic migrations to head.

Schema is now owned by Alembic (see backend/migrations/), not by
Base.metadata.create_all. This wrapper just runs `alembic upgrade head` so the
old `python -m scripts.init_db` entrypoint keeps working; it is equivalent to
running `alembic upgrade head` from the backend directory.

The PgSTAC catalog (pgstac schema) is managed separately by `pypgstac migrate` /
stac-fastapi-pgstac and is NOT created here.
"""
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig

from app.utils.logger_utils import get_logger

logger = get_logger("INIT DATABASE")

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def init_db() -> None:
    cfg = AlembicConfig(str(_ALEMBIC_INI))
    logger.info("Running Alembic migrations to head (%s)", _ALEMBIC_INI)
    command.upgrade(cfg, "head")
    logger.info("Application schema is up to date")


if __name__ == "__main__":
    init_db()
