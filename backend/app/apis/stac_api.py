from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.deps import get_db
from app.schemas.common import MapSearchRequest
from app.services.pgstac_service import pgstac_service

router = APIRouter(prefix="/api/stac", tags=["STAC"])


def _item_to_feature(item: dict) -> dict:
    data = item.get("data") or {}
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": item["id"],
        "collection": item.get("collection_id"),
        **{k: v for k, v in data.items() if k not in ("properties",)},
        "properties": {
            "datetime": item["datetime"].isoformat() if item.get("datetime") else None,
            "collection": item.get("collection_id"),
            **(data.get("properties", {})),
        },
    }


@router.get("/collections")
async def list_collections(
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    try:
        collections = await pgstac_service.get_collections(db, limit)
        return {
            "type": "Catalog",
            "description": "STAC collections from PgSTAC",
            "stac_version": "1.0.0",
            "links": [{"rel": "search", "href": "/api/stac/search", "method": "POST"}],
            "collections": [{"id": c["id"], **c["data"]} for c in collections],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{collection_id}")
async def get_collection(collection_id: str, db: AsyncSession = Depends(get_db)):
    try:
        collection = await pgstac_service.get_collection(db, collection_id)
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")
        return {"id": collection["id"], **collection["data"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{collection_id}/items")
async def list_items(
    collection_id: str,
    limit: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await pgstac_service.search_items(db, [collection_id], limit=limit)
        return {
            "type": "FeatureCollection",
            "context": {"returned": len(items)},
            "features": [_item_to_feature(i) for i in items],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{collection_id}/items/{item_id}")
async def get_item(collection_id: str, item_id: str, db: AsyncSession = Depends(get_db)):
    """Single STAC item endpoint — used by Titiler as ?url= target."""
    try:
        item = await pgstac_service.get_item(db, item_id, collection_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return _item_to_feature(item)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/items/{item_id}/tile-url")
async def item_tile_url(item_id: str, db: AsyncSession = Depends(get_db)):
    """Browser-ready TiTiler tile-URL template for an item's `visual` COG —
    lets the frontend display a specific dated scene as a map overlay."""
    import urllib.parse

    from app.configs.config import Config

    item = await pgstac_service.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    assets = (item.get("data") or {}).get("assets", {})
    visual = assets.get("visual")
    if not visual or "href" not in visual:
        raise HTTPException(status_code=404, detail="Item has no visual asset")
    cog = urllib.parse.quote(visual["href"], safe="")
    tile_url = (
        f"{Config.TITILER_PUBLIC_URL}/cog/tiles/{Config.TITILER_TMS}"
        f"/{{z}}/{{x}}/{{y}}.png?url={cog}"
    )
    return {
        "item_id": item_id,
        "datetime": item["datetime"].isoformat() if item.get("datetime") else None,
        "tile_url": tile_url,
    }


@router.post("/search")
async def search_items(request: MapSearchRequest, db: AsyncSession = Depends(get_db)):
    try:
        items = await pgstac_service.search_items(
            db,
            collection_ids=request.collections,
            limit=request.limit,
            bbox=request.bbox,
            datetime_str=request.datetime,
        )
        return {
            "type": "FeatureCollection",
            "context": {"returned": len(items)},
            "features": [_item_to_feature(i) for i in items],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
