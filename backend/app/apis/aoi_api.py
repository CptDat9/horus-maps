import asyncio
import json
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import String, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.config import Config
from app.databases.deps import get_db
from app.models.aoi import AOI
from app.models.utils import NotFound
from app.schemas.aoi import AOICreate, AOIListResponse, AOIResponse, AOIUpdate
from app.services.aoi_service import aoi_service
from app.utils.logger_utils import get_logger

logger = get_logger("AOIAPI")
router = APIRouter(prefix="/api/sessions/{session_id}/aois", tags=["AOI"])


async def _fetch_geojson_batch(db: AsyncSession, aois: list[AOI]) -> dict[uuid.UUID, dict]:
    """Single query to get all geometries as GeoJSON — avoids N+1."""
    if not aois:
        return {}
    ids = [a.id for a in aois]
    stmt = select(
        AOI.id.label("aoi_id"),
        cast(func.ST_AsGeoJSON(AOI.geometry), String).label("geojson"),
    ).where(AOI.id.in_(ids))
    result = await db.execute(stmt)
    return {
        row.aoi_id: json.loads(row.geojson)
        for row in result
        if row.geojson
    }


def _build_response(aoi: AOI, geojson_map: dict[uuid.UUID, dict]) -> AOIResponse:
    return AOIResponse(
        id=aoi.id,
        session_id=aoi.session_id,
        name=aoi.name,
        description=aoi.description,
        properties=aoi.properties,
        geometry=geojson_map.get(aoi.id, {}),
        created_at=aoi.created_at,
        updated_at=aoi.updated_at,
    )


@router.post("", response_model=AOIResponse, status_code=status.HTTP_201_CREATED)
async def create_aoi(
    session_id: uuid.UUID,
    aoi_data: AOICreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        aoi = await aoi_service.create(db, session_id, aoi_data)
        geojson_map = await _fetch_geojson_batch(db, [aoi])

        # Fire-and-forget: trigger async AOI data extraction
        try:
            from app.workers.task_manager import task_manager
            await task_manager.create_task(
                session_id=session_id,
                task_type="extract_aoi",
                payload={"aoi_id": str(aoi.id)},
            )
        except Exception as e:
            logger.warning(f"Could not queue AOI extraction task: {e}")

        return _build_response(aoi, geojson_map)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=AOIListResponse)
async def list_aois(
    session_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    aois, total = await aoi_service.list(db, session_id, skip, limit)
    geojson_map = await _fetch_geojson_batch(db, list(aois))
    items = [_build_response(aoi, geojson_map) for aoi in aois]
    return AOIListResponse(
        items=items,
        total=total,
        page=skip // limit + 1 if limit > 0 else 1,
        size=limit,
    )


@router.get("/{aoi_id}", response_model=AOIResponse)
async def get_aoi(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    try:
        aoi = await aoi_service.get(db, aoi_id)
        if aoi.session_id != session_id:
            raise NotFound(f"AOI {aoi_id} not found")
        geojson_map = await _fetch_geojson_batch(db, [aoi])
        return _build_response(aoi, geojson_map)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{aoi_id}/image")
async def export_aoi_image(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    tile_url: str | None = Query(None),
    zoom: int | None = Query(None, ge=14, le=21),
    db: AsyncSession = Depends(get_db),
):
    """Export the AOI as a satellite PNG — built from the SAME base-layer tiles
    the detection pipeline uses (the active map layer sent via `tile_url`)."""
    aoi = await db.get(AOI, aoi_id)
    if not aoi or aoi.session_id != session_id:
        raise HTTPException(status_code=404, detail=f"AOI {aoi_id} not found")

    row = (await db.execute(
        text(
            "SELECT ST_XMin(geometry), ST_YMin(geometry), ST_XMax(geometry), ST_YMax(geometry) "
            "FROM aoi WHERE id = :aoi_id"
        ),
        {"aoi_id": aoi.id},
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="AOI geometry not found")
    bbox = (float(row[0]), float(row[1]), float(row[2]), float(row[3]))

    out_path = os.path.join(Config.DETECTION_OUTPUT_DIR, "aoi", f"{aoi_id}.png")
    from app.services.ml_service import ml_service
    try:
        await asyncio.to_thread(
            ml_service.export_aoi_image, bbox, out_path, tile_url=tile_url, zoom=zoom,
        )
    except Exception as e:
        logger.error("AOI image export failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not fetch imagery for AOI")

    return FileResponse(out_path, media_type="image/png", filename=f"aoi_{aoi_id}.png")


@router.put("/{aoi_id}", response_model=AOIResponse)
async def update_aoi(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    aoi_data: AOIUpdate,
    db: AsyncSession = Depends(get_db),
):
    try:
        aoi = await aoi_service.get(db, aoi_id)
        if aoi.session_id != session_id:
            raise NotFound(f"AOI {aoi_id} not found")
        aoi = await aoi_service.update(db, aoi_id, aoi_data)
        geojson_map = await _fetch_geojson_batch(db, [aoi])
        return _build_response(aoi, geojson_map)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{aoi_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_aoi(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    try:
        aoi = await aoi_service.get(db, aoi_id)
        if aoi.session_id != session_id:
            raise NotFound(f"AOI {aoi_id} not found")
        await aoi_service.delete(db, aoi_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
