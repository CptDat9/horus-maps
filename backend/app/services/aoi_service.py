import json
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aoi import AOI
from app.models.utils import NotFound
from app.schemas.aoi import AOICreate, AOIUpdate
from app.services.session_service import session_service
from app.utils.logger_utils import get_logger

logger = get_logger("AOIService")


class AOIService:
    async def create(
        self, db: AsyncSession, session_id: uuid.UUID, aoi_data: AOICreate
    ) -> AOI:
        await session_service.ensure(db, session_id)
        geojson = json.dumps(aoi_data.geometry.model_dump())

        aoi = AOI(
            session_id=session_id,
            name=aoi_data.name,
            description=aoi_data.description,
            geometry=func.ST_GeomFromGeoJSON(geojson),
            properties=aoi_data.properties,
        )
        db.add(aoi)
        await db.flush()

        stats = await self._compute_stats(db, aoi.id)
        if stats:
            aoi.properties = {
                **(aoi_data.properties or {}),
                "_area_m2": stats["area_m2"],
                "_perimeter_m": stats["perimeter_m"],
            }

        await db.commit()
        await db.refresh(aoi)
        return aoi

    async def _compute_stats(self, db: AsyncSession, aoi_id: uuid.UUID) -> dict | None:
        """Single PostGIS call — returns area (m²) and perimeter (m) for an AOI."""
        sql = text(
            """
            SELECT
                ST_Area(geometry::geography)      AS area_m2,
                ST_Perimeter(geometry::geography) AS perimeter_m
            FROM aoi
            WHERE id = :id
            """
        )
        row = (await db.execute(sql, {"id": aoi_id})).fetchone()
        if row and row.area_m2 is not None:
            return {
                "area_m2": float(row.area_m2),
                "perimeter_m": float(row.perimeter_m),
            }
        return None

    async def get(self, db: AsyncSession, aoi_id: uuid.UUID) -> AOI:
        stmt = select(AOI).where(AOI.id == aoi_id)
        aoi = (await db.execute(stmt)).scalar_one_or_none()
        if not aoi:
            raise NotFound(f"AOI {aoi_id} not found")
        return aoi

    async def list(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[list[AOI], int]:
        count_stmt = select(func.count(AOI.id)).where(AOI.session_id == session_id)
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = (
            select(AOI)
            .where(AOI.session_id == session_id)
            .offset(skip)
            .limit(limit)
        )
        aois = (await db.execute(stmt)).scalars().all()
        return list(aois), total

    async def update(
        self,
        db: AsyncSession,
        aoi_id: uuid.UUID,
        aoi_data: AOIUpdate,
    ) -> AOI:
        aoi = await self.get(db, aoi_id)
        if aoi_data.name is not None:
            aoi.name = aoi_data.name
        if aoi_data.description is not None:
            aoi.description = aoi_data.description
        if aoi_data.properties is not None:
            internal = {k: v for k, v in (aoi.properties or {}).items() if k.startswith("_")}
            public = {k: v for k, v in aoi_data.properties.items() if not k.startswith("_")}
            aoi.properties = {**internal, **public}
        await db.commit()
        await db.refresh(aoi)
        return aoi

    async def delete(self, db: AsyncSession, aoi_id: uuid.UUID) -> None:
        aoi = await self.get(db, aoi_id)
        await db.delete(aoi)
        await db.commit()


aoi_service = AOIService()
