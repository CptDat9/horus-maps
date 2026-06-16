import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.deps import get_db
from app.models.measurement import Measurement
from app.models.utils import NotFound
from app.schemas.measurement import (
    MeasurementCreate,
    MeasurementListResponse,
    MeasurementResponse,
)
from app.services.measurement_service import measurement_service
from app.utils.geo_utils import geometry_as_geojson

router = APIRouter(
    prefix="/api/sessions/{session_id}/aois/{aoi_id}/measurements",
    tags=["Measurements"],
)


async def _to_response(db: AsyncSession, row: Measurement) -> MeasurementResponse:
    geometry = None
    if row.geometry is not None:
        geometry = await geometry_as_geojson(
            db, Measurement.geometry, row.id, Measurement.id
        )
    return MeasurementResponse.model_validate(
        {
            "id": row.id,
            "session_id": row.session_id,
            "aoi_id": row.aoi_id,
            "type": row.type,
            "value": row.value,
            "unit": row.unit,
            "geometry": geometry,
            "metadata": row.meta,
            "created_at": row.created_at,
        }
    )


@router.post("", response_model=MeasurementResponse, status_code=status.HTTP_201_CREATED)
async def create_measurement(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    measurement_data: MeasurementCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await measurement_service.create(
            db, session_id, aoi_id, measurement_data
        )
        return await _to_response(db, row)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=MeasurementListResponse)
async def list_measurements(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    rows, total = await measurement_service.list_by_aoi(db, aoi_id, skip, limit)
    items = [await _to_response(db, row) for row in rows]
    return MeasurementListResponse(items=items, total=total)
