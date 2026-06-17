import uuid
from typing import Any, Awaitable, Callable, Dict

import httpx

from app.constants.task_constants import TaskStatus, TaskType
from app.utils.logger_utils import get_logger
from app.databases.deps import get_db_context
from app.services.task_service import task_service
from app.services.aoi_service import aoi_service
from app.services.comparison_service import comparison_service
from app.services.detection_service import detection_service
from app.services.pgstac_service import pgstac_service
from app.services.map_service import map_service

logger = get_logger("TaskHandlers")

Handler = Callable[[Any, Dict[str, Any]], Awaitable[Dict[str, Any]]]


class TaskHandlers:
    def __init__(self) -> None:
        self._registry: Dict[str, Handler] = {
            TaskType.EXTRACT_AOI.value: self._extract_aoi,
            TaskType.TEMPORAL_COMPARISON.value: self._temporal_comparison,
            TaskType.DETECTION.value: self._run_detection,
            TaskType.SEARCH_ITEMS.value: self._search_items,
            TaskType.GET_COLLECTIONS.value: self._get_collections,
            TaskType.REFRESH_LAYERS.value: self._refresh_layers,
            TaskType.HEAVY_REQUEST.value: self._heavy_request,
        }

    async def dispatch(self, task_id: uuid.UUID, task_type: str, payload: Dict[str, Any]) -> None:
        """Route task to its registered handler. Status is managed by task_manager."""
        handler = self._registry.get(task_type)
        async with get_db_context() as db:
            try:
                if handler is None:
                    logger.warning("Unhandled task type: %s", task_type)
                    result = {"message": f"Task type '{task_type}' has no specific handler"}
                else:
                    result = await handler(db, payload)

                await task_service.update_status(db, task_id, TaskStatus.COMPLETED.value, result=result)
                logger.info("Task %s (%s) completed", task_id, task_type)

            except Exception as e:
                logger.error("Task %s (%s) failed: %s", task_id, task_type, e, exc_info=True)
                await task_service.update_status(db, task_id, TaskStatus.FAILED.value, error_message=str(e))


    async def _heavy_request(self, db, payload: Dict) -> Dict:
        """Placeholder task queued by the rate limiter when a session exceeds the
        soft threshold — acknowledged so the API surface stays protected."""
        logger.info("Heavy request task acknowledged: %s", payload.get("path"))
        return {"message": "Heavy request acknowledged", "path": payload.get("path")}


    async def _extract_aoi(self, db, payload: Dict) -> Dict:
        """
        Find STAC items that intersect the AOI geometry and return their metadata.
        The result is stored in the task record and broadcast via WebSocket.
        """
        aoi_id_str = payload.get("aoi_id")
        if not aoi_id_str:
            raise ValueError("payload missing aoi_id")

        aoi = await aoi_service.get(db, uuid.UUID(aoi_id_str))

        from sqlalchemy import text
        sql = text(
            "SELECT ST_XMin(geometry), ST_YMin(geometry), ST_XMax(geometry), ST_YMax(geometry) "
            "FROM aoi WHERE id = :aoi_id"
        )
        row = (await db.execute(sql, {"aoi_id": aoi.id})).fetchone()
        if not row:
            raise ValueError(f"AOI {aoi_id_str} geometry not found")

        bbox = [float(row[0]), float(row[1]), float(row[2]), float(row[3])]

        collections = ["sentinel-2-l2a", "sentinel-2-l1c"]
        found_items = []
        for col in collections:
            items = await pgstac_service.search_items_by_bbox(db, col, bbox, limit=5)
            for item in items:
                found_items.append({
                    "id": item["id"],
                    "collection": item.get("collection_id"),
                    "datetime": item["datetime"].isoformat() if item.get("datetime") else None,
                    "assets": list((item.get("data") or {}).get("assets", {}).keys()),
                })

        return {
            "aoi_id": aoi_id_str,
            "bbox": bbox,
            "items_found": len(found_items),
            "items": found_items,
        }

    async def _temporal_comparison(self, db, payload: Dict) -> Dict:
        """
        Retrieve both STAC items and build, for each date, BOTH:
          - a slippy tile-URL template (kept for any map-based view), and
          - a static image URL: the AOI bbox rendered by TiTiler to a single
            PNG, used by the side-by-side comparison viewer (zoom + export).
        Updates the comparison record status to 'completed'.
        """
        import urllib.parse

        comparison_id_str = payload.get("comparison_id")
        left_item_id = payload.get("left_item_id")
        right_item_id = payload.get("right_item_id")

        if not all([comparison_id_str, left_item_id, right_item_id]):
            raise ValueError("payload missing comparison_id / left_item_id / right_item_id")

        from app.configs.config import Config

        comparison = await comparison_service.get(db, uuid.UUID(comparison_id_str))
        from sqlalchemy import text
        bbox_row = (
            await db.execute(
                text(
                    "SELECT ST_XMin(geometry), ST_YMin(geometry), "
                    "ST_XMax(geometry), ST_YMax(geometry) FROM aoi WHERE id = :aoi_id"
                ),
                {"aoi_id": comparison.aoi_id},
            )
        ).fetchone()
        bbox = [float(c) for c in bbox_row] if bbox_row else None

        left = await pgstac_service.get_item(db, left_item_id)
        right = await pgstac_service.get_item(db, right_item_id)

        def _cog_href(item: Dict | None) -> str | None:
            if not item:
                return None
            assets = (item.get("data") or {}).get("assets", {})
            visual = assets.get("visual")
            return visual["href"] if visual and "href" in visual else None

        color = urllib.parse.quote(Config.STAC_VISUAL_COLOR_FORMULA)
        enhance = f"resampling={Config.TITILER_RESAMPLING}&color_formula={color}"

        def _tile_url(item: Dict | None) -> str | None:
            href = _cog_href(item)
            if not href:
                return None
            cog = urllib.parse.quote(href, safe="")
            return (
                f"{Config.TITILER_PUBLIC_URL}/cog/tiles/{Config.TITILER_TMS}"
                f"/{{z}}/{{x}}/{{y}}.png?url={cog}&{enhance}"
            )

        def _image_url(item: Dict | None) -> str | None:
            href = _cog_href(item)
            if not href or not bbox:
                return None
            cog = urllib.parse.quote(href, safe="")
            minx, miny, maxx, maxy = bbox
            return (
                f"{Config.TITILER_PUBLIC_URL}/cog/bbox/"
                f"{minx},{miny},{maxx},{maxy}.png?url={cog}&max_size=1024&{enhance}"
            )

        result = {
            "comparison_id": comparison_id_str,
            "bbox": bbox,
            "left": {
                "item_id": left_item_id,
                "datetime": left["datetime"].isoformat() if left and left.get("datetime") else None,
                "tile_url": _tile_url(left),
                "image_url": _image_url(left),
            },
            "right": {
                "item_id": right_item_id,
                "datetime": right["datetime"].isoformat() if right and right.get("datetime") else None,
                "tile_url": _tile_url(right),
                "image_url": _image_url(right),
            },
        }

        await self._save_comparison_snapshots(
            comparison_id_str, payload.get("session_id"), comparison.aoi_id,
            bbox, enhance, {"left": _cog_href(left), "right": _cog_href(right)}, result,
        )

        await comparison_service.update_status(
            db, uuid.UUID(comparison_id_str), TaskStatus.COMPLETED.value, result
        )

        return result

    @staticmethod
    async def _save_comparison_snapshots(comparison_id, session_id, aoi_id, bbox, enhance, hrefs, result):
        """Render each side's AOI crop to a PNG on the shared static volume so the
        comparison history is self-contained (survives the source COG, loads fast).
        Best-effort: a failed snapshot leaves the on-demand image_url as fallback."""
        import os
        import urllib.parse

        from app.configs.config import Config

        if not bbox or not session_id:
            return
        out_dir = os.path.join(Config.DETECTION_OUTPUT_DIR, "comparisons")
        os.makedirs(out_dir, exist_ok=True)
        minx, miny, maxx, maxy = bbox
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=5.0)) as client:
            for side, href in hrefs.items():
                if not href:
                    continue
                cog = urllib.parse.quote(href, safe="")
                url = (
                    f"{Config.TITILER_URL}/cog/bbox/"
                    f"{minx},{miny},{maxx},{maxy}.png?url={cog}&max_size=1024&{enhance}"
                )
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200 and resp.content:
                        with open(os.path.join(out_dir, f"{comparison_id}_{side}.png"), "wb") as fh:
                            fh.write(resp.content)
                        result[side]["snapshot_url"] = (
                            f"/api/sessions/{session_id}/aois/{aoi_id}"
                            f"/comparisons/{comparison_id}/image/{side}"
                        )
                except Exception as e:
                    logger.warning("Comparison snapshot %s/%s failed: %s", comparison_id, side, e)

    async def _run_detection(self, db, payload: Dict) -> Dict:
        """
        Run YOLO-OBB object detection over an AOI: read its bbox, fetch
        high-resolution Esri imagery, infer, then persist each detection and
        return a GeoJSON-shaped result the frontend overlays directly.

        Inference is CPU-bound and blocking, so it runs in a worker thread to
        keep the consumer's event loop (task-status pub/sub) responsive.
        """
        import asyncio

        from app.services.ml_service import ml_service

        aoi_id_str = payload.get("aoi_id")
        session_id_str = payload.get("session_id")
        if not aoi_id_str or not session_id_str:
            raise ValueError("payload missing aoi_id / session_id")

        aoi_id = uuid.UUID(aoi_id_str)
        session_id = uuid.UUID(session_id_str)
        classes = payload.get("classes")
        object_class = payload.get("object_class", "all")
        tile_url = payload.get("tile_url")
        zoom = payload.get("zoom")
        confidence = float(payload.get("confidence", 0.2))
        iou = float(payload.get("iou", 0.45))

        aoi = await aoi_service.get(db, aoi_id)

        from sqlalchemy import text
        sql = text(
            "SELECT ST_XMin(geometry), ST_YMin(geometry), ST_XMax(geometry), ST_YMax(geometry) "
            "FROM aoi WHERE id = :aoi_id"
        )
        row = (await db.execute(sql, {"aoi_id": aoi.id})).fetchone()
        if not row:
            raise ValueError(f"AOI {aoi_id_str} geometry not found")
        bbox = (float(row[0]), float(row[1]), float(row[2]), float(row[3]))

        import os
        from app.configs.config import Config

        run_id = uuid.uuid4()
        runs_dir = os.path.join(Config.DETECTION_OUTPUT_DIR, "runs")
        preview_path = os.path.join(runs_dir, f"{run_id}.png")
        geojson = await asyncio.to_thread(
            ml_service.detect_bbox,
            bbox=bbox,
            object_class=object_class,
            classes=classes,
            zoom=zoom,
            conf=confidence,
            iou=iou,
            tile_url=tile_url,
            output_path=preview_path,
        )

        from app.schemas.detection import DetectionCreate

        rows = [
            DetectionCreate(
                object_type=f["properties"]["object_type"],
                geometry=f["geometry"],
                confidence=f["properties"]["confidence"],
                properties=f["properties"],
            )
            for f in geojson["features"]
        ]
        meta = dict(geojson.get("metadata", {}))
        meta["has_preview"] = os.path.exists(preview_path)
        run = await detection_service.create_run(
            db, session_id, aoi_id, rows,
            classes=meta.get("classes"), meta=meta, run_id=run_id,
        )

        return {
            "aoi_id": aoi_id_str,
            "run_id": str(run.id),
            "count": run.count,
            "counts_by_type": meta.get("counts_by_type", {}),
            "has_preview": meta.get("has_preview", False),
            "zoom": meta.get("zoom"),
            "profile": meta.get("profile"),
            "source": meta.get("source"),
            "confidence": meta.get("confidence"),
            "iou": meta.get("iou"),
            "tile": meta.get("tile"),
            "overlap": meta.get("overlap"),
            "imgsz": meta.get("imgsz"),
            "mosaic_size": meta.get("mosaic_size"),
            "tiles_total": meta.get("tiles_total"),
            "tiles_failed": meta.get("tiles_failed"),
            "model": meta.get("model"),
            "elapsed_s": meta.get("elapsed_s"),
            "note": meta.get("note"),
        }

    async def _search_items(self, db, payload: Dict) -> Dict:
        items = await pgstac_service.search_items(
            db, payload.get("collections"), payload.get("limit", 100)
        )
        return {
            "count": len(items),
            "items": [{"id": i["id"], "collection": i.get("collection_id")} for i in items],
        }

    async def _get_collections(self, db, payload: Dict) -> Dict:
        collections = await pgstac_service.get_collections(db)
        return {
            "count": len(collections),
            "collections": [{"id": c["id"]} for c in collections],
        }

    async def _refresh_layers(self, db) -> Dict:
        layers = await map_service.list_layers(db)
        return {"count": len(layers), "layers": layers}


task_handlers = TaskHandlers()
