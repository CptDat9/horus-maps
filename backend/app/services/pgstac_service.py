"""
Unified STAC access facade.

Resolution order for every query (each step is crash-safe — a missing
`pgstac` schema or empty table never raises to the caller):

    1. Local PgSTAC stored procedure  (pgstac.search / pgstac.items)
    2. Local raw SQL on pgstac.items
    3. Local public.items SQLAlchemy model (app fallback table)
    4. Remote STAC API (Element 84 Earth Search) — authoritative for Sentinel-2

The remote step is what makes Sentinel imagery work without ingesting any data
locally. Set STAC_USE_LOCAL=false to skip the DB entirely, or STAC_USE_REMOTE=false
to disable the remote fallback.
"""
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.config import Config
from app.models.collection import Collection
from app.models.item import Item
from app.services.stac_client import stac_client
from app.utils.logger_utils import get_logger

logger = get_logger("PgSTACService")


class PgSTACService:
    def __init__(self) -> None:
        # Cache local-backend availability so we don't re-probe (and re-log) a
        # missing pgstac schema / public.items table on every single tile.
        # None = unknown, True/False = probed result.
        self._pgstac_ok: Optional[bool] = None
        self._public_items_ok: Optional[bool] = None

    # ------------------------------------------------------------------ #
    #  Collections                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _rollback(session: AsyncSession) -> None:
        # A failed statement aborts the asyncpg transaction; without a rollback
        # every later query in this session fails with "transaction is aborted".
        try:
            await session.rollback()
        except Exception:
            pass

    async def get_collections(self, session: AsyncSession, limit: int = 100) -> List[Dict]:
        if Config.STAC_USE_LOCAL:
            try:
                sql = text("SELECT id, content FROM pgstac.collections ORDER BY id LIMIT :limit")
                rows = (await session.execute(sql, {"limit": limit})).fetchall()
                if rows:
                    return [{"id": r.id, "data": r.content or {}} for r in rows]
            except Exception as e:
                logger.debug("pgstac.collections unavailable: %s", e)
                await self._rollback(session)

            try:
                stmt = select(Collection).limit(limit)
                rows = (await session.execute(stmt)).scalars().all()
                if rows:
                    return [{"id": c.id, "data": c.data or {}} for c in rows]
            except Exception as e:
                logger.debug("public.collections unavailable: %s", e)
                await self._rollback(session)

        if Config.STAC_USE_REMOTE:
            return await stac_client.get_collections(limit)
        return []

    async def get_collection(self, session: AsyncSession, collection_id: str) -> Optional[Dict]:
        if Config.STAC_USE_LOCAL:
            try:
                sql = text("SELECT id, content FROM pgstac.collections WHERE id = :id")
                row = (await session.execute(sql, {"id": collection_id})).fetchone()
                if row:
                    return {"id": row.id, "data": row.content or {}}
            except Exception:
                await self._rollback(session)
            try:
                c = await session.get(Collection, collection_id)
                if c:
                    return {"id": c.id, "data": c.data or {}}
            except Exception:
                await self._rollback(session)

        if Config.STAC_USE_REMOTE:
            for c in await stac_client.get_collections():
                if c["id"] == collection_id:
                    return c
        return None

    # ------------------------------------------------------------------ #
    #  Item search                                                         #
    # ------------------------------------------------------------------ #

    async def search_items(
        self,
        session: AsyncSession,
        collection_ids: Optional[List[str]] = None,
        limit: int = 100,
        bbox: Optional[List[float]] = None,
        datetime_str: Optional[str] = None,
        sort_by_cloud: bool = False,
    ) -> List[Dict]:
        if Config.STAC_USE_LOCAL:
            local = await self._search_local(session, collection_ids, bbox, datetime_str, limit)
            if local:
                return local

        if Config.STAC_USE_REMOTE:
            return await stac_client.search(
                collections=collection_ids,
                bbox=bbox,
                datetime_str=datetime_str,
                limit=limit,
                sort_by_cloud=sort_by_cloud,
            )
        return []

    async def search_items_by_bbox(
        self,
        session: AsyncSession,
        collection_id: str,
        bbox: List[float],
        limit: int = 1,
        sort_by_cloud: bool = True,
    ) -> List[Dict]:
        """Tile-level search — defaults to least-cloudy scene first."""
        return await self.search_items(
            session,
            collection_ids=[collection_id],
            limit=limit,
            bbox=bbox,
            sort_by_cloud=sort_by_cloud,
        )

    async def _search_local(
        self,
        session: AsyncSession,
        collections: Optional[List[str]],
        bbox: Optional[List[float]],
        datetime_str: Optional[str],
        limit: int,
    ) -> List[Dict]:
        # 1+2) PgSTAC schema (stored proc, then raw items). Skipped entirely once
        # we've learned the schema isn't present → no per-tile log spam.
        if self._pgstac_ok is not False:
            body: Dict[str, Any] = {"limit": limit}
            if collections:
                body["collections"] = collections
            if bbox and len(bbox) == 4:
                body["bbox"] = bbox
            if datetime_str:
                body["datetime"] = datetime_str

            pgstac_alive = False
            try:
                # cast(:q as jsonb) — NOT ":q::jsonb"; the latter trips SQLAlchemy's
                # bindparam parser and emits a stray ':' → Postgres syntax error.
                sql = text("SELECT pgstac.search(cast(:q as jsonb))")
                row = (await session.execute(sql, {"q": json.dumps(body)})).scalar_one_or_none()
                pgstac_alive = True
                if isinstance(row, dict) and row.get("features"):
                    self._pgstac_ok = True
                    return [self._feature(f) for f in row["features"]]
            except Exception as e:
                logger.debug("pgstac.search() unavailable: %s", e)
                await self._rollback(session)

            if not pgstac_alive:
                try:
                    conditions = ["TRUE"]
                    params: Dict[str, Any] = {"limit": limit}
                    if collections:
                        conditions.append("collection = ANY(:collections)")
                        params["collections"] = collections
                    if bbox and len(bbox) == 4:
                        conditions.append("geometry && ST_MakeEnvelope(:minx,:miny,:maxx,:maxy,4326)")
                        params.update({"minx": bbox[0], "miny": bbox[1], "maxx": bbox[2], "maxy": bbox[3]})
                    if datetime_str:
                        parts = datetime_str.split("/")
                        if len(parts) == 2:
                            conditions.append("datetime BETWEEN :dt0 AND :dt1")
                            params["dt0"], params["dt1"] = parts[0], parts[1]
                        else:
                            conditions.append("datetime = :dt")
                            params["dt"] = datetime_str
                    where = " AND ".join(conditions)
                    sql = text(
                        f"SELECT id, collection, content, datetime FROM pgstac.items "
                        f"WHERE {where} ORDER BY datetime DESC LIMIT :limit"
                    )
                    rows = (await session.execute(sql, params)).fetchall()
                    pgstac_alive = True
                    if rows:
                        self._pgstac_ok = True
                        return [
                            {"id": r.id, "collection_id": r.collection, "data": r.content or {}, "datetime": r.datetime}
                            for r in rows
                        ]
                except Exception as e:
                    logger.debug("pgstac.items raw SQL unavailable: %s", e)
                    await self._rollback(session)

            # Remember the schema's presence so future tiles skip these probes.
            self._pgstac_ok = pgstac_alive
            if not pgstac_alive:
                logger.info("PgSTAC schema not present — using remote STAC fallback")

        # 3) public.items app fallback table.
        if self._public_items_ok is not False:
            try:
                stmt = select(Item)
                if collections:
                    stmt = stmt.where(Item.collection_id.in_(collections))
                stmt = stmt.order_by(Item.datetime.desc()).limit(limit)
                rows = (await session.execute(stmt)).scalars().all()
                self._public_items_ok = True
                return [
                    {"id": i.id, "collection_id": i.collection_id, "data": i.data or {}, "datetime": i.datetime}
                    for i in rows
                ]
            except Exception as e:
                logger.debug("public.items unavailable: %s", e)
                await self._rollback(session)
                self._public_items_ok = False
        return []

    @staticmethod
    def _feature(f: dict) -> dict:
        return {
            "id": f.get("id"),
            "collection_id": f.get("collection"),
            "data": f,
            "datetime": f.get("properties", {}).get("datetime"),
        }

    # ------------------------------------------------------------------ #
    #  Single item                                                         #
    # ------------------------------------------------------------------ #

    async def get_item(
        self,
        session: AsyncSession,
        item_id: str,
        collection_id: Optional[str] = None,
    ) -> Optional[Dict]:
        if Config.STAC_USE_LOCAL:
            if self._pgstac_ok is not False:
                try:
                    if collection_id:
                        sql = text(
                            "SELECT id, collection, content, datetime FROM pgstac.items "
                            "WHERE id = :id AND collection = :col"
                        )
                        row = (await session.execute(sql, {"id": item_id, "col": collection_id})).fetchone()
                    else:
                        sql = text(
                            "SELECT id, collection, content, datetime FROM pgstac.items WHERE id = :id"
                        )
                        row = (await session.execute(sql, {"id": item_id})).fetchone()
                    if row:
                        return {"id": row.id, "collection_id": row.collection,
                                "data": row.content or {}, "datetime": row.datetime}
                except Exception:
                    self._pgstac_ok = False
                    await self._rollback(session)

            if self._public_items_ok is not False:
                try:
                    stmt = select(Item).where(Item.id == item_id)
                    if collection_id:
                        stmt = stmt.where(Item.collection_id == collection_id)
                    item = (await session.execute(stmt)).scalar_one_or_none()
                    if item:
                        return {"id": item.id, "collection_id": item.collection_id,
                                "data": item.data or {}, "datetime": item.datetime}
                except Exception:
                    self._public_items_ok = False
                    await self._rollback(session)

        if Config.STAC_USE_REMOTE:
            return await stac_client.get_item(item_id, collection_id)
        return None


pgstac_service = PgSTACService()
