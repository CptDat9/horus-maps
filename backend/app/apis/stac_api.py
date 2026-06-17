"""
Gateway for `/api/stac/*`.

Requests are answered by the standalone stac-fastapi-pgstac service
(`Config.STAC_API_URL`) so the browser talks to one origin while the real,
spec-compliant STAC API does the work. If that service is unreachable we fall
back to `pgstac_service` (local PgSTAC, then the remote Sentinel catalogue),
keeping the catalogue browsable in every infrastructure state.

`/items/{id}/tile-url` is not part of the STAC spec — it is served here directly
because it turns an item's `visual` COG into a Titiler tile-URL template.
"""
import urllib.parse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.config import Config
from app.databases.deps import get_db
from app.schemas.common import MapSearchRequest
from app.services.pgstac_service import pgstac_service
from app.utils.logger_utils import get_logger

logger = get_logger("StacAPI")
router = APIRouter(prefix="/api/stac", tags=["STAC"])

_stac = httpx.AsyncClient(
    base_url=Config.STAC_API_URL,
    timeout=httpx.Timeout(20.0, connect=5.0),
    headers={"Accept": "application/geo+json, application/json"},
)


async def _proxy(method: str, path: str, *, params=None, json=None) -> dict:
    resp = await _stac.request(method, path, params=params, json=json)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:300])
    return resp.json()


async def close() -> None:
    if not _stac.is_closed:
        await _stac.aclose()


def _item_to_feature(item: dict) -> dict:
    data = item.get("data") or {}
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": item["id"],
        "collection": item.get("collection_id"),
        **{k: v for k, v in data.items() if k != "properties"},
        "properties": {
            "datetime": item["datetime"].isoformat() if item.get("datetime") else None,
            "collection": item.get("collection_id"),
            **(data.get("properties", {})),
        },
    }


def _feature_collection(items: list[dict]) -> dict:
    return {
        "type": "FeatureCollection",
        "context": {"returned": len(items)},
        "features": [_item_to_feature(i) for i in items],
    }


@router.get("/collections")
async def list_collections(limit: int = Query(100, ge=1, le=1000), db: AsyncSession = Depends(get_db)):
    try:
        return await _proxy("GET", "/collections", params={"limit": limit})
    except httpx.RequestError as err:
        logger.warning("STAC service unreachable (%s) — local fallback", err)
        collections = await pgstac_service.get_collections(db, limit)
        return {"collections": [{"id": c["id"], **c["data"]} for c in collections]}


@router.get("/collections/{collection_id}")
async def get_collection(collection_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await _proxy("GET", f"/collections/{collection_id}")
    except httpx.RequestError as err:
        logger.warning("STAC service unreachable (%s) — local fallback", err)
        collection = await pgstac_service.get_collection(db, collection_id)
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")
        return {"id": collection["id"], **collection["data"]}


@router.get("/collections/{collection_id}/items")
async def list_items(
    collection_id: str,
    limit: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _proxy("GET", f"/collections/{collection_id}/items", params={"limit": limit})
    except httpx.RequestError as err:
        logger.warning("STAC service unreachable (%s) — local fallback", err)
        items = await pgstac_service.search_items(db, [collection_id], limit=limit)
        return _feature_collection(items)


@router.post("/search")
async def search_items(request: MapSearchRequest, db: AsyncSession = Depends(get_db)):
    body: dict = {"collections": request.collections, "limit": request.limit}
    if request.bbox:
        body["bbox"] = request.bbox
    if request.geometry:
        body["intersects"] = request.geometry
    if request.datetime:
        body["datetime"] = request.datetime
    try:
        return await _proxy("POST", "/search", json=body)
    except httpx.RequestError as err:
        logger.warning("STAC service unreachable (%s) — local fallback", err)
        items = await pgstac_service.search_items(
            db,
            collection_ids=request.collections,
            limit=request.limit,
            bbox=request.bbox,
            datetime_str=request.datetime,
        )
        return _feature_collection(items)


@router.get("/items/{item_id}/tile-url")
async def item_tile_url(item_id: str, db: AsyncSession = Depends(get_db)):
    """Browser-ready Titiler tile-URL template for an item's `visual` COG, so the
    frontend can display one dated scene as a map overlay."""
    item = await pgstac_service.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    assets = (item.get("data") or {}).get("assets", {})
    visual = assets.get("visual")
    if not visual or "href" not in visual:
        raise HTTPException(status_code=404, detail="Item has no visual asset")

    cog = urllib.parse.quote(visual["href"], safe="")
    color = urllib.parse.quote(Config.STAC_VISUAL_COLOR_FORMULA)
    tile_url = (
        f"{Config.TITILER_PUBLIC_URL}/cog/tiles/{Config.TITILER_TMS}"
        f"/{{z}}/{{x}}/{{y}}.png?url={cog}"
        f"&resampling={Config.TITILER_RESAMPLING}&color_formula={color}"
    )
    return {
        "item_id": item_id,
        "datetime": item["datetime"].isoformat() if item.get("datetime") else None,
        "tile_url": tile_url,
    }
