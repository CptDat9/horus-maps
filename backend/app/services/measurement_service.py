import json
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aoi import AOI
from app.models.measurement import Measurement
from app.schemas.measurement import MeasurementCreate
from app.services.session_service import session_service
from app.utils.logger_utils import get_logger

logger = get_logger("MeasurementService")

# Unit conversion factors from SI base units
_AREA_FACTORS: dict[str, float] = {
    "m2": 1.0,
    "sqm": 1.0,
    "km2": 1e-6,
    "sqkm": 1e-6,
    "ha": 1e-4,
}
_LENGTH_FACTORS: dict[str, float] = {
    "m": 1.0,
    "km": 1e-3,
}


def _convert(value_si: float, unit: str, mtype: str) -> float:
    """Convert SI value (m² or m) to the requested unit."""
    unit_lower = unit.lower()
    if mtype == "area":
        return value_si * _AREA_FACTORS.get(unit_lower, 1.0)
    if mtype in ("perimeter", "distance"):
        return value_si * _LENGTH_FACTORS.get(unit_lower, 1.0)
    return value_si


class MeasurementService:
    async def create(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        aoi_id: uuid.UUID,
        measurement_data: MeasurementCreate,
    ) -> Measurement:
        await session_service.ensure(db, session_id)
        aoi = await db.get(AOI, aoi_id)
        if not aoi or aoi.session_id != session_id:
            raise ValueError(f"AOI {aoi_id} not found")

        value_si = await self._calculate_si_value(db, aoi, measurement_data.type)
        value = _convert(value_si, measurement_data.unit, measurement_data.type)

        geom = None
        if measurement_data.geometry:
            geojson_str = (
                json.dumps(measurement_data.geometry)
                if isinstance(measurement_data.geometry, dict)
                else measurement_data.geometry
            )
            geom = func.ST_GeomFromGeoJSON(geojson_str)

        measurement = Measurement(
            session_id=session_id,
            aoi_id=aoi_id,
            type=measurement_data.type,
            value=value,
            unit=measurement_data.unit,
            geometry=geom,
            meta=measurement_data.metadata,
        )
        db.add(measurement)
        await db.commit()
        await db.refresh(measurement)
        return measurement

    async def _calculate_si_value(
        self, db: AsyncSession, aoi: AOI, mtype: str
    ) -> float:
        """
        Fast path: read pre-computed stats stored in aoi.properties (set on create).
        Slow path: PostGIS query (fallback for old AOIs or if pre-computation failed).
        """
        props = aoi.properties or {}

        if mtype == "area":
            if "_area_m2" in props:
                logger.debug(f"AOI {aoi.id}: area from cache ({props['_area_m2']} m²)")
                return props["_area_m2"]
            sql = text("SELECT ST_Area(geometry::geography) FROM aoi WHERE id = :id")

        elif mtype == "perimeter":
            if "_perimeter_m" in props:
                logger.debug(f"AOI {aoi.id}: perimeter from cache ({props['_perimeter_m']} m)")
                return props["_perimeter_m"]
            sql = text("SELECT ST_Perimeter(geometry::geography) FROM aoi WHERE id = :id")

        else:
            return 0.0

        logger.debug(f"AOI {aoi.id}: computing {mtype} via PostGIS (no cached value)")
        value = (await db.execute(sql, {"id": aoi.id})).scalar_one()
        return float(value) if value else 0.0

    async def get(self, db: AsyncSession, measurement_id: uuid.UUID) -> Measurement:
        m = await db.get(Measurement, measurement_id)
        if not m:
            raise ValueError(f"Measurement {measurement_id} not found")
        return m

    async def list_by_aoi(
        self,
        db: AsyncSession,
        aoi_id: uuid.UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[list[Measurement], int]:
        count_stmt = select(func.count(Measurement.id)).where(Measurement.aoi_id == aoi_id)
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = (
            select(Measurement)
            .where(Measurement.aoi_id == aoi_id)
            .offset(skip)
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return list(rows), total


measurement_service = MeasurementService()
