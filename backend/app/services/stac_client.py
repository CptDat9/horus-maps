"""
Async client for a remote STAC API (STAC API - Item Search spec).

Used as the authoritative imagery source when the local PgSTAC catalog is empty
or not migrated. Defaults to Element 84 Earth Search v1, which serves public
Sentinel-2 L2A COGs that Titiler can read directly (no signing / no ingestion).

All methods return items in the same normalized shape used by PgSTACService:
    {"id", "collection_id", "data" (full STAC Feature), "datetime"}
so callers don't care whether the source is local Postgres or a remote API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import httpx

from app.configs.config import Config
from app.utils.logger_utils import get_logger

logger = get_logger("StacClient")


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        # STAC datetimes are RFC3339 ("...Z"). fromisoformat needs "+00:00".
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _feature_to_item(feature: dict) -> dict:
    props = feature.get("properties") or {}
    return {
        "id": feature.get("id"),
        "collection_id": feature.get("collection"),
        "data": feature,
        "datetime": _parse_dt(props.get("datetime") or props.get("start_datetime")),
    }


class StacClient:
    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or Config.STAC_SEARCH_URL).rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    def _http(self) -> httpx.AsyncClient:
        # Lazily created so the singleton can be imported without a running loop.
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(Config.STAC_HTTP_TIMEOUT, connect=5.0),
                headers={"Accept": "application/geo+json, application/json"},
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def search(
        self,
        collections: Optional[list[str]] = None,
        bbox: Optional[list[float]] = None,
        datetime_str: Optional[str] = None,
        limit: int = 20,
        max_cloud_cover: Optional[int] = None,
        sort_by_cloud: bool = False,
    ) -> list[dict]:
        body: dict[str, Any] = {
            "collections": collections or [Config.STAC_DEFAULT_COLLECTION],
            "limit": max(1, min(limit, 100)),
        }
        if bbox and len(bbox) == 4:
            body["bbox"] = bbox
        if datetime_str:
            body["datetime"] = datetime_str

        cloud = max_cloud_cover if max_cloud_cover is not None else Config.STAC_MAX_CLOUD_COVER
        if cloud is not None:
            # STAC `query` extension — supported by Earth Search.
            body["query"] = {"eo:cloud_cover": {"lte": cloud}}

        # Least-cloudy first for tile rendering; newest first for browsing.
        body["sortby"] = (
            [{"field": "properties.eo:cloud_cover", "direction": "asc"}]
            if sort_by_cloud
            else [{"field": "properties.datetime", "direction": "desc"}]
        )

        try:
            resp = await self._http().post("/search", json=body)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Remote STAC search %s -> %s: %s",
                self.base_url, e.response.status_code, e.response.text[:300],
            )
            return []
        except httpx.HTTPError as e:
            logger.warning("Remote STAC search failed (%s): %s", self.base_url, e)
            return []

        features = (resp.json() or {}).get("features", [])
        return [_feature_to_item(f) for f in features]

    async def get_item(
        self, item_id: str, collection_id: Optional[str] = None
    ) -> Optional[dict]:
        # Prefer the canonical item endpoint when the collection is known.
        if collection_id:
            try:
                resp = await self._http().get(
                    f"/collections/{collection_id}/items/{item_id}"
                )
                if resp.status_code == 200:
                    return _feature_to_item(resp.json())
            except httpx.HTTPError as e:
                logger.warning("Remote STAC get_item failed: %s", e)

        # Otherwise resolve by id via search.
        try:
            resp = await self._http().post("/search", json={"ids": [item_id], "limit": 1})
            resp.raise_for_status()
            features = (resp.json() or {}).get("features", [])
            return _feature_to_item(features[0]) if features else None
        except httpx.HTTPError as e:
            logger.warning("Remote STAC get_item-by-id failed: %s", e)
            return None

    async def get_collections(self, limit: int = 100) -> list[dict]:
        try:
            resp = await self._http().get("/collections")
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Remote STAC get_collections failed: %s", e)
            return []
        cols = (resp.json() or {}).get("collections", [])[:limit]
        return [{"id": c.get("id"), "data": c} for c in cols]


stac_client = StacClient()
