import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.config import Config
from app.models.map_layer import MapLayer


def _default_layers(titiler_url: str) -> list[dict[str, Any]]:
    base = titiler_url.rstrip("/")
    return [
        {
            "id": "osm",
            "name": "OpenStreetMap",
            "type": "tile",
            "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            "options": {"attribution": "© OpenStreetMap"},
            "is_active": True,
            "display_order": 2,
        },
        {
            "id": "sentinel-2-true-color",
            "name": "Sentinel-2 True Color",
            "type": "stac",
            "url": f"{base}/cog",
            "options": {
                "collection": "sentinel-2-l2a",
                "asset": "visual",
                "color_formula": "gamma RGB 1.05 sigmoidal RGB 4 0.5 saturation 1.15",
                "minzoom": 8,
                "maxzoom": 15,
                "attribution": "Contains modified Copernicus Sentinel-2 data",
            },
            "is_active": True,
            "display_order": 10,
        },
        {
            "id": "sentinel-2-nir",
            "name": "Sentinel-2 NIR (Vegetation)",
            "type": "stac",
            "url": f"{base}/cog",
            "options": {
                "collection": "sentinel-2-l2a",
                "asset": "nir",
                "rescale": "0,4000",
                "colormap_name": "greens",
                "minzoom": 8,
                "maxzoom": 15,
                "attribution": "Contains modified Copernicus Sentinel-2 data",
            },
            "is_active": False,
            "display_order": 11,
        },
    ]


class MapService:
    _LAYER_CACHE_TTL = 300.0

    def __init__(self) -> None:
        self._layer_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}

    @staticmethod
    def layer_to_api(layer: MapLayer | dict[str, Any]) -> dict[str, Any]:
        if isinstance(layer, MapLayer):
            options = layer.options or {}
            return {
                "id": layer.id,
                "name": layer.name,
                "type": layer.type,
                "url": layer.url,
                "options": options,
                "is_active": layer.is_active,
                "display_order": layer.display_order,
                "attribution": options.get("attribution"),
            }
        options = layer.get("options") or {}
        return {
            "id": layer["id"],
            "name": layer["name"],
            "type": layer["type"],
            "url": layer["url"],
            "options": options,
            "is_active": layer.get("is_active", True),
            "display_order": layer.get("display_order", 0),
            "attribution": options.get("attribution"),
        }

    async def list_layers(self, db: AsyncSession, active_only: bool = True) -> list[dict[str, Any]]:
        stmt = select(MapLayer).order_by(MapLayer.display_order)
        if active_only:
            stmt = stmt.where(MapLayer.is_active.is_(True))
        result = await db.execute(stmt)
        rows = result.scalars().all()
        if not rows:
            return [self.layer_to_api(x) for x in _default_layers(Config.TITILER_URL)]
        return [self.layer_to_api(row) for row in rows]

    async def get_layer_by_id(self, db: AsyncSession, layer_id: str) -> dict[str, Any] | None:
        now = time.monotonic()
        cached = self._layer_cache.get(layer_id)
        if cached and now - cached[0] < self._LAYER_CACHE_TTL:
            return cached[1]

        row = await db.get(MapLayer, layer_id)
        if row:
            layer = self.layer_to_api(row)
        else:
            layer = next(
                (self.layer_to_api(d) for d in _default_layers(Config.TITILER_URL) if d["id"] == layer_id),
                None,
            )
        self._layer_cache[layer_id] = (now, layer)
        return layer

    _OBSOLETE_LAYER_IDS = ("openfreemap-bright",)

    async def seed_defaults(self, db: AsyncSession) -> None:
        """Reconcile the layer catalogue with the current defaults on every startup:
        insert missing layers, refresh existing ones, drop layers we no longer ship."""
        existing = {
            row.id: row
            for row in (await db.execute(select(MapLayer))).scalars().all()
        }
        for layer in _default_layers(Config.TITILER_URL):
            row = existing.get(layer["id"])
            if row is None:
                db.add(MapLayer(**layer))
            else:
                for key, value in layer.items():
                    setattr(row, key, value)

        for obsolete_id in self._OBSOLETE_LAYER_IDS:
            if obsolete_id in existing:
                await db.delete(existing[obsolete_id])

        await db.commit()
        self._layer_cache.clear()

        try:
            from app.constants.cache_constants import CacheConstants
            from app.services.cache_service import cache_service
            await cache_service.delete(f"{CacheConstants.STAC_COLLECTIONS}:all_layers")
        except Exception:
            pass


map_service = MapService()
