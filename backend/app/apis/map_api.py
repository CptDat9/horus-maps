import urllib.parse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.config import Config
from app.constants.cache_constants import CacheConstants
from app.databases.deps import get_db
from app.schemas.common import MapSearchRequest
from app.services.cache_service import cache_service
from app.services.map_service import map_service
from app.services.pgstac_service import pgstac_service
from app.utils.logger_utils import get_logger
from app.utils.tile_utils import coarse_tile, tile_to_bbox

# Sentinel-2 assets whose pixels are already display-ready 8-bit RGB and must
# NOT be linearly rescaled like the raw uint16 reflectance bands.
_PRESCALED_ASSETS = {"visual", "rendered_preview", "preview"}

# Browsers (and any CDN) may cache rendered tiles for a day — pans/zooms back to a
# visited area then cost nothing, which is the single biggest perceived speed-up.
_TILE_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}

logger = get_logger("MapAPI")
router = APIRouter(prefix="/api", tags=["Map & Tile Operations"])

_http = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0, connect=5.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
)


@router.get("/layers", status_code=status.HTTP_200_OK)
async def get_layers(db: AsyncSession = Depends(get_db)):
    """List all active map layers."""
    cache_key = f"{CacheConstants.STAC_COLLECTIONS}:all_layers"
    try:
        cached = await cache_service.get(cache_key)
        if cached:
            return cached
    except Exception as err:
        logger.warning(f"Cache read failed: {err}")

    layers = await map_service.list_layers(db)
    try:
        await cache_service.set(cache_key, layers, expire=Config.LAYER_CACHE_TTL)
    except Exception as err:
        logger.warning(f"Cache write failed: {err}")
    return layers


@router.get(
    "/tiles/{layer_id}/{z}/{x}/{y}",
    responses={200: {"content": {"image/png": {}}}, 204: {"description": "No imagery"}},
)
async def get_map_tile(
    layer_id: str = Path(...),
    z: int = Path(...),
    x: int = Path(...),
    y: int = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Proxy tile from upstream source. Caches result in Redis."""
    cache_key = f"{CacheConstants.TILE}:{layer_id}:{z}:{x}:{y}"
    try:
        tile_bytes = await cache_service.get_bytes(cache_key)
        if tile_bytes:
            return Response(content=tile_bytes, media_type="image/png", headers=_TILE_CACHE_HEADERS)
    except Exception as err:
        logger.warning(f"Tile cache read failed: {err}")

    layer = await map_service.get_layer_by_id(db, layer_id)
    if not layer:
        raise HTTPException(status_code=404, detail=f"Layer '{layer_id}' not found")

    if layer["type"] == "tile":
        target_url = layer["url"].format(z=z, x=x, y=y)
    elif layer["type"] == "stac":
        target_url = await _build_stac_tile_url(db, layer, z, x, y)
        if not target_url:
            return Response(status_code=204)
    else:
        raise HTTPException(status_code=400, detail="Unsupported layer type")

    # Release the pooled DB connection BEFORE the slow upstream fetch. A map load
    # fires dozens of tile requests at once; holding a connection across a multi-
    # second COG read would drain the pool and stall every other endpoint too.
    await db.close()
    return await _proxy_tile(target_url, cache_key)


async def _build_stac_tile_url(db, layer: dict, z: int, x: int, y: int) -> str | None:
    """For a STAC layer, find the least-cloudy scene covering this tile and build a
    TiTiler COG tile URL pointing at the scene's COG asset href. None = no imagery."""
    options = layer.get("options") or {}
    collection = options.get("collection", Config.STAC_DEFAULT_COLLECTION)
    asset_key = options.get("asset", "visual")
    colormap = options.get("colormap_name")
    color_formula = None if colormap else options.get("color_formula")
    # Pre-scaled RGB assets (visual) render near-black if rescaled, so only honour
    # an explicit rescale for raw reflectance bands.
    rescale = None if asset_key in _PRESCALED_ASSETS else options.get("rescale")

    # Group neighbouring tiles onto one scene lookup to limit DB/remote hits.
    cz, cx, cy = coarse_tile(z, x, y)
    item_cache_key = f"stac_item:{collection}:{cz}:{cx}:{cy}"
    item_data: dict | None = None
    try:
        item_data = await cache_service.get(item_cache_key)
    except Exception:
        pass

    if not item_data:
        bbox = tile_to_bbox(cz, cx, cy)
        items = await pgstac_service.search_items_by_bbox(
            db, collection, bbox, limit=1, sort_by_cloud=True
        )
        if not items:
            return None
        item_data = items[0]
        try:
            await cache_service.set(item_cache_key, item_data, expire=Config.ITEM_CACHE_TTL)
        except Exception:
            pass

    assets = (item_data.get("data") or {}).get("assets", {})
    asset = assets.get(asset_key) or assets.get("visual")
    href = (asset or {}).get("href")
    if not href:
        logger.warning("Asset '%s' missing href in item %s", asset_key, item_data.get("id"))
        return None

    cog_url = urllib.parse.quote(href, safe="")
    # bilinear renders up-scaled 10 m Sentinel-2 far less blocky than the default.
    params = [f"url={cog_url}", "resampling=bilinear"]
    if rescale:
        params.append(f"rescale={rescale}")
    if colormap:
        params.append(f"colormap_name={colormap}")
    if color_formula:
        params.append(f"color_formula={urllib.parse.quote(color_formula)}")

    tms = Config.TITILER_TMS
    return f"{Config.TITILER_URL}/cog/tiles/{tms}/{z}/{x}/{y}.png?{'&'.join(params)}"


async def _proxy_tile(target_url: str, cache_key: str) -> Response:
    """Fetch tile from upstream and cache the result. A slow/edge tile degrades to
    an empty 204 (basemap shows through) instead of a broken tile + 5xx spam."""
    for attempt in range(2):
        try:
            resp = await _http.get(target_url)
            break
        except httpx.RequestError as err:
            if attempt == 0:
                continue
            logger.warning("Tile upstream %s (giving up) %s", type(err).__name__, target_url[:120])
            return Response(status_code=204)

    if resp.status_code in (204, 404):
        return Response(status_code=204)
    if resp.status_code != 200:
        logger.warning(
            "Tile upstream %s for %s: %s", resp.status_code, target_url, resp.text[:300]
        )
        raise HTTPException(status_code=502, detail="Upstream tile server error")

    raw = resp.content
    try:
        await cache_service.set_bytes(cache_key, raw, expire=Config.TILE_CACHE_TTL)
    except Exception as err:
        logger.warning(f"Tile cache write failed: {err}")

    return Response(content=raw, media_type="image/png", headers=_TILE_CACHE_HEADERS)


@router.get("/maps/collections")
async def get_collections(db: AsyncSession = Depends(get_db)):
    collections = await pgstac_service.get_collections(db)
    return {"collections": [{"id": c["id"], **c["data"]} for c in collections]}


@router.post("/maps/search")
async def search_items(request: MapSearchRequest, db: AsyncSession = Depends(get_db)):
    items = await pgstac_service.search_items(
        db,
        collection_ids=request.collections,
        limit=request.limit,
        bbox=request.bbox,
        datetime_str=request.datetime,
    )
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": item["id"],
                **item["data"],
                "properties": {
                    "datetime": item["datetime"].isoformat() if item.get("datetime") else None,
                    "collection": item.get("collection_id"),
                    **(item["data"].get("properties", {})),
                },
            }
            for item in items
        ],
    }
