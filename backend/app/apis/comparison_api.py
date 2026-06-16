import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.deps import get_db
from app.models.temporal_comparison import TemporalComparison
from app.models.utils import NotFound
from app.schemas.temporal_comparison import (
    TemporalComparisonCreate,
    TemporalComparisonResponse,
)
from app.services.comparison_service import comparison_service
from app.utils.logger_utils import get_logger

logger = get_logger("ComparisonAPI")
router = APIRouter(
    prefix="/api/sessions/{session_id}/aois/{aoi_id}/comparisons",
    tags=["Temporal Comparisons"],
)


def _to_response(row: TemporalComparison) -> TemporalComparisonResponse:
    return TemporalComparisonResponse.model_validate(row)


@router.post("", response_model=TemporalComparisonResponse, status_code=status.HTTP_201_CREATED)
async def create_comparison(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    comparison_data: TemporalComparisonCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await comparison_service.create(db, session_id, aoi_id, comparison_data)

        try:
            from app.workers.task_manager import task_manager
            await task_manager.create_task(
                session_id=session_id,
                task_type="temporal_comparison",
                payload={
                    "comparison_id": str(row.id),
                    "left_item_id": comparison_data.left_item_id,
                    "right_item_id": comparison_data.right_item_id,
                },
            )
        except Exception as e:
            logger.warning(f"Could not queue comparison task: {e}")

        return _to_response(row)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{comparison_id}", response_model=TemporalComparisonResponse)
async def get_comparison(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    comparison_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await comparison_service.get(db, comparison_id)
        if row.session_id != session_id or row.aoi_id != aoi_id:
            raise NotFound(f"Temporal comparison {comparison_id} not found")
        return _to_response(row)
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("", response_model=list[TemporalComparisonResponse])
async def list_comparisons(
    session_id: uuid.UUID,
    aoi_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    rows, _ = await comparison_service.list_by_aoi(db, aoi_id, skip, limit)
    return [_to_response(row) for row in rows if row.session_id == session_id]
