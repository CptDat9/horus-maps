import json
import uuid
from typing import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.elements import WKTElement

from app.models.aoi import AOI
from app.models.detection import Detection
from app.models.detection_run import DetectionRun
from app.models.utils import NotFound
from app.schemas.detection import DetectionCreate
from app.services.session_service import session_service


class DetectionService:
    # ------------------------------------------------------------------ #
    # Runs (history per AOI)

    async def create_run(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        aoi_id: uuid.UUID,
        detections: Iterable[DetectionCreate],
        classes: list[int] | None,
        meta: dict | None,
        run_id: uuid.UUID | None = None,
    ) -> DetectionRun:
        """Persist one detection run + all its boxes in a single transaction.
        Runs accumulate (history); previous runs are NOT deleted."""
        await session_service.ensure(db, session_id)
        run = DetectionRun(
            id=run_id or uuid.uuid4(),
            session_id=session_id, aoi_id=aoi_id, classes=classes, meta=meta, count=0,
        )
        db.add(run)
        await db.flush()  # get run.id

        rows = [
            Detection(
                session_id=session_id,
                aoi_id=aoi_id,
                run_id=run.id,
                object_type=d.object_type,
                # extended=True → parse GeoJSON via ST_GeomFromGeoJSON.
                geometry=WKTElement(json.dumps(d.geometry), srid=4326, extended=True),
                confidence=d.confidence,
                properties=d.properties,
            )
            for d in detections
        ]
        run.count = len(rows)
        if rows:
            db.add_all(rows)
        await db.commit()
        await db.refresh(run)
        return run

    async def list_runs(
        self, db: AsyncSession, aoi_id: uuid.UUID, limit: int = 50
    ) -> list[DetectionRun]:
        stmt = (
            select(DetectionRun)
            .where(DetectionRun.aoi_id == aoi_id)
            .order_by(DetectionRun.created_at.desc())
            .limit(limit)
        )
        return list((await db.execute(stmt)).scalars().all())

    async def latest_run(self, db: AsyncSession, aoi_id: uuid.UUID) -> DetectionRun | None:
        stmt = (
            select(DetectionRun)
            .where(DetectionRun.aoi_id == aoi_id)
            .order_by(DetectionRun.created_at.desc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def get_run(self, db: AsyncSession, run_id: uuid.UUID) -> DetectionRun:
        run = await db.get(DetectionRun, run_id)
        if not run:
            raise NotFound(f"Detection run {run_id} not found")
        return run

    async def delete_run(self, db: AsyncSession, run_id: uuid.UUID) -> None:
        run = await db.get(DetectionRun, run_id)
        if run:
            await db.delete(run)  # detections cascade
            await db.commit()

    # ------------------------------------------------------------------ #
    # Detections

    async def list_by_run(self, db: AsyncSession, run_id: uuid.UUID) -> list[Detection]:
        stmt = select(Detection).where(Detection.run_id == run_id)
        return list((await db.execute(stmt)).scalars().all())

    async def list_latest(
        self, db: AsyncSession, aoi_id: uuid.UUID
    ) -> tuple[list[Detection], DetectionRun | None]:
        """Detections of the most recent run for the AOI (what the map shows)."""
        run = await self.latest_run(db, aoi_id)
        if not run:
            return [], None
        return await self.list_by_run(db, run.id), run

    async def get(self, db: AsyncSession, detection_id: uuid.UUID) -> Detection:
        detection = await db.get(Detection, detection_id)
        if not detection:
            raise NotFound(f"Detection {detection_id} not found")
        return detection

    async def delete_all(self, db: AsyncSession, aoi_id: uuid.UUID) -> int:
        """Clear the entire detection history for an AOI."""
        await db.execute(delete(Detection).where(Detection.aoi_id == aoi_id))
        result = await db.execute(delete(DetectionRun).where(DetectionRun.aoi_id == aoi_id))
        await db.commit()
        return result.rowcount or 0


detection_service = DetectionService()
