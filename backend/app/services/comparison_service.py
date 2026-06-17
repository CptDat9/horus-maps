import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aoi import AOI
from app.models.temporal_comparison import TemporalComparison
from app.models.utils import NotFound
from app.schemas.temporal_comparison import TemporalComparisonCreate
from app.services.pgstac_service import pgstac_service
from app.services.session_service import session_service


class TemporalComparisonService:
    async def create(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        aoi_id: uuid.UUID,
        comparison_data: TemporalComparisonCreate,
    ) -> TemporalComparison:
        await session_service.ensure(db, session_id)

        aoi = await db.get(AOI, aoi_id)
        if not aoi or aoi.session_id != session_id:
            raise ValueError(f"AOI {aoi_id} not found")

        left = await pgstac_service.get_item(db, comparison_data.left_item_id)
        right = await pgstac_service.get_item(db, comparison_data.right_item_id)
        if not left or not right:
            raise ValueError(
                f"One or both items not found in STAC catalog "
                f"(left={comparison_data.left_item_id}, right={comparison_data.right_item_id})"
            )

        comparison = TemporalComparison(
            session_id=session_id,
            aoi_id=aoi_id,
            left_item_id=comparison_data.left_item_id,
            right_item_id=comparison_data.right_item_id,
            status="pending",
            meta=comparison_data.metadata,
        )
        db.add(comparison)
        await db.commit()
        await db.refresh(comparison)
        return comparison

    async def get(self, db: AsyncSession, comparison_id: uuid.UUID) -> TemporalComparison:
        comparison = await db.get(TemporalComparison, comparison_id)
        if not comparison:
            raise NotFound(f"Temporal comparison {comparison_id} not found")
        return comparison

    async def set_task_id(
        self, db: AsyncSession, comparison_id: uuid.UUID, task_id: uuid.UUID
    ) -> TemporalComparison:
        """Link the comparison to the background task that builds it."""
        comparison = await self.get(db, comparison_id)
        comparison.task_id = task_id
        await db.commit()
        await db.refresh(comparison)
        return comparison

    async def update_status(
        self,
        db: AsyncSession,
        comparison_id: uuid.UUID,
        status: str,
        result: dict | None = None,
    ) -> TemporalComparison:
        comparison = await self.get(db, comparison_id)
        comparison.status = status
        if result is not None:
            comparison.comparison_result = result
        await db.commit()
        await db.refresh(comparison)
        return comparison

    async def list_by_aoi(
        self,
        db: AsyncSession,
        aoi_id: uuid.UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[list[TemporalComparison], int]:
        count_stmt = select(func.count(TemporalComparison.id)).where(
            TemporalComparison.aoi_id == aoi_id
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = (
            select(TemporalComparison)
            .where(TemporalComparison.aoi_id == aoi_id)
            .offset(skip)
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return list(rows), total


comparison_service = TemporalComparisonService()
