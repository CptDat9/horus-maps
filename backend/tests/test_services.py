import uuid

import pytest

# These are DB-backed integration tests. They need an async SQLite driver and,
# for the AOI geometry path, PostGIS — skip cleanly when unavailable so the rest
# of the offline unit suite still runs.
pytest.importorskip("aiosqlite")

from geojson_pydantic import Polygon
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.databases.base import Base
from app.models.aoi import AOI
from app.models.session import AppSession
from app.models.task import Task
from app.schemas.aoi import AOICreate
from app.schemas.common import TaskCreate
from app.services.aoi_service import AOIService
from app.services.session_service import SessionService
from app.services.task_service import TaskService


@pytest.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AppSession.__table__, AOI.__table__, Task.__table__],
        )

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def session_id(test_db: AsyncSession) -> uuid.UUID:
    row = await SessionService().create(test_db)
    return row.id


@pytest.mark.asyncio
async def test_session_create(test_db: AsyncSession):
    row = await SessionService().create(test_db)
    assert row.id is not None
    assert row.session_id


@pytest.mark.asyncio
async def test_aoi_create(test_db: AsyncSession, session_id: uuid.UUID):
    polygon = Polygon(
        type="Polygon",
        coordinates=[[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]],
    )
    aoi = await AOIService().create(
        test_db,
        session_id,
        AOICreate(name="Test AOI", description="Test", geometry=polygon),
    )
    assert aoi.name == "Test AOI"
    assert aoi.id is not None


@pytest.mark.asyncio
async def test_task_create(test_db: AsyncSession, session_id: uuid.UUID):
    task = await TaskService().create(
        test_db,
        session_id,
        TaskCreate(task_type="measurement", payload={"test": "data"}),
    )
    assert task.task_type == "measurement"
    assert task.status == "pending"


@pytest.mark.asyncio
async def test_task_update_status(test_db: AsyncSession, session_id: uuid.UUID):
    service = TaskService()
    task = await service.create(
        test_db, session_id, TaskCreate(task_type="test_task", payload={})
    )
    updated = await service.update_status(test_db, task.id, "running")
    assert updated.status == "running"
    assert updated.started_at is not None
