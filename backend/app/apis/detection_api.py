import json
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.config import Config
from app.databases.deps import get_db
from app.models.aoi import AOI
from app.models.detection import Detection
from app.models.utils import NotFound
from app.schemas.detection import (
    DetectionJobCreate,
    DetectionJobResponse,
    DetectionListResponse,
    DetectionResponse,
    DetectionRunListResponse,
    DetectionRunResponse,
)
from app.services.detection_service import detection_service
from app.utils.logger_utils import get_logger

logger = get_logger("DetectionAPI")
router = APIRouter(
    prefix="/api/sessions/{session_id}/aois/{aoi_id}/detections",
    tags=["Detections"],
)


async def _ensure_aoi(db: AsyncSession, session_id: uuid.UUID, aoi_id: uuid.UUID) -> AOI:
    aoi = await db.get(AOI, aoi_id)
    if not aoi or aoi.session_id != session_id:
        raise HTTPException(status_code=404, detail=f"AOI {aoi_id} not found")
    return aoi


async def _geojson_map(db: AsyncSession, rows: list[Detection]) -> dict[uuid.UUID, dict]:
    """Fetch all geometries as GeoJSON in one query (avoids N+1)."""
    if not rows:
        return {}
    ids = [r.id for r in rows]
    stmt = select(
        Detection.id.label("did"),
        cast(func.ST_AsGeoJSON(Detection.geometry), String).label("geojson"),
    ).where(Detection.id.in_(ids))
    result = await db.execute(stmt)
    return {r.did: json.loads(r.geojson) for r in result if r.geojson}


def _to_response(row: Detection, geo: dict[uuid.UUID, dict]) -> DetectionResponse:
    return DetectionResponse(
        id=row.id,
        session_id=row.session_id,
        aoi_id=row.aoi_id,
        object_type=row.object_type,
        geometry=geo.get(row.id, {}),
        confidence=row.confidence,
        properties=row.properties,
        created_at=row.created_at,
    )


def _run_preview_path(run_id: uuid.UUID) -> str:
    return os.path.join(Config.DETECTION_OUTPUT_DIR, "runs", f"{run_id}.png")


@router.post("", response_model=DetectionJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_detection(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    job: DetectionJobCreate,
    db: AsyncSession = Depends(get_db),
):
    """Queue an object-detection job over the AOI (a new history run). The client
    tracks progress over SSE/WebSocket and reloads detections when done."""
    await _ensure_aoi(db, session_id, aoi_id)

    from app.constants.task_constants import TaskType
    from app.workers.task_manager import task_manager

    try:
        task = await task_manager.create_task(
            session_id=session_id,
            task_type=TaskType.DETECTION.value,
            payload={
                "aoi_id": str(aoi_id),
                "classes": job.classes,
                "object_class": job.object_class,
                "tile_url": job.tile_url,
                "zoom": job.zoom,
                "confidence": job.confidence,
                "iou": job.iou,
            },
        )
    except Exception as e:
        logger.error("Could not queue detection task: %s", e)
        raise HTTPException(status_code=503, detail="Task queue unavailable")

    return DetectionJobResponse(
        task_id=task["task_id"], status=task["status"], aoi_id=aoi_id,
        message="Detection job queued",
    )


@router.get("", response_model=DetectionListResponse)
async def list_detections(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Detections of the most recent run (what the map overlays)."""
    rows, run = await detection_service.list_latest(db, aoi_id)
    rows = [r for r in rows if r.session_id == session_id]
    geo = await _geojson_map(db, rows)
    return DetectionListResponse(
        items=[_to_response(r, geo) for r in rows],
        total=len(rows),
        run_id=run.id if run else None,
    )


@router.get("/runs", response_model=DetectionRunListResponse)
async def list_runs(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """History of detection runs for the AOI (newest first)."""
    runs = await detection_service.list_runs(db, aoi_id)
    runs = [r for r in runs if r.session_id == session_id]
    return DetectionRunListResponse(
        items=[DetectionRunResponse.model_validate(r) for r in runs],
        total=len(runs),
    )


@router.get("/runs/{run_id}", response_model=DetectionListResponse)
async def get_run_detections(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Detections of a specific historical run."""
    rows = await detection_service.list_by_run(db, run_id)
    rows = [r for r in rows if r.session_id == session_id and r.aoi_id == aoi_id]
    geo = await _geojson_map(db, rows)
    return DetectionListResponse(
        items=[_to_response(r, geo) for r in rows], total=len(rows), run_id=run_id,
    )


@router.get("/runs/{run_id}/preview")
async def run_preview(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Annotated PNG (imagery + drawn boxes) for a specific run."""
    await _ensure_aoi(db, session_id, aoi_id)
    path = _run_preview_path(run_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No preview for this run")
    return FileResponse(path, media_type="image/png", filename=f"detection_{run_id}.png")


@router.get("/preview")
async def latest_preview(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Annotated PNG of the most recent run."""
    await _ensure_aoi(db, session_id, aoi_id)
    run = await detection_service.latest_run(db, aoi_id)
    if not run:
        raise HTTPException(status_code=404, detail="No detection run yet")
    path = _run_preview_path(run.id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No detection preview yet")
    return FileResponse(path, media_type="image/png", filename=f"detection_{run.id}.png")


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_detections(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Clear the entire detection history for the AOI."""
    await _ensure_aoi(db, session_id, aoi_id)
    await detection_service.delete_all(db, aoi_id)


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a single historical run."""
    await _ensure_aoi(db, session_id, aoi_id)
    try:
        await detection_service.delete_run(db, run_id)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
