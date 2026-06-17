import asyncio
import sys

from sqlalchemy import text
from app.databases.base import Base
from app.databases.postgres import engine
from app.models import (
    AOI,
    AppSession,
    MapLayer,
    Measurement,
    Task,
    TemporalComparison,
)
from app.utils.logger_utils import get_logger

logger = get_logger("DROP DATABASE")

APP_TABLES = [
    TemporalComparison.__table__,
    Measurement.__table__,
    Task.__table__,
    AOI.__table__,
    MapLayer.__table__,
    AppSession.__table__,
]


async def drop_db(force: bool = False):
    if not force:
        confirm = input(
            "Bạn có chắc chắn muốn DROP tất cả application tables? (y/N): "
        )
        if confirm.lower() != 'y':
            logger.info("Hủy bỏ drop database.")
            return

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.drop_all(
                sync_conn, checkfirst=True
            )
        )

    logger.info("Đã drop tất cả application tables thành công!")


if __name__ == "__main__":
    force = "--force" in sys.argv or "-f" in sys.argv
    asyncio.run(drop_db(force=force))