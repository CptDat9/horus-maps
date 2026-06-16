import uuid
from typing import Any, Dict

from app.utils.logger_utils import get_logger
from app.databases.deps import get_db_context
from app.services.task_service import task_service
from app.services.aoi_service import aoi_service
from app.services.comparison_service import comparison_service
from app.services.detection_service import detection_service
from app.services.pgstac_service import pgstac_service
from app.services.map_service import map_service

logger = get_logger("TaskHandlers")


class TaskHandlers:
    async def dispatch(self, task_id: uuid.UUID, task_type: str, payload: Dict[str, Any]) -> None:
        """Route task to the appropriate handler. Status is managed by task_manager."""
        async with get_db_context() as db:
            try:
                if task_type == "extract_aoi":
                    result = await self._extract_aoi(db, payload)

                elif task_type == "temporal_comparison":
                    result = await self._temporal_comparison(db, payload)

                elif task_type == "detection":
                    result = await self._run_detection(db, payload)

                elif task_type == "search_items":
                    result = await self._search_items(db, payload)

                elif task_type == "get_collections":
                    result = await self._get_collections(db, payload)

                elif task_type == "refresh_layers":
                    result = await self._refresh_layers(db)

                elif task_type == "heavy_request":
                    # Queued by rate limiter — log and ack
                    result = {
                        "message": "Heavy request acknowledged",
                        "path": payload.get("path"),
                    }
                    logger.info(f"Heavy request task acknowledged: {payload.get('path')}")

                else:
                    result = {"message": f"Task type '{task_type}' has no specific handler"}
                    logger.warning(f"Unhandled task type: {task_type}")

                # Mark completed (task_manager called update_status("running") already)
                await task_service.update_status(db, task_id, "completed", result=result)
                logger.info(f"Task {task_id} ({task_type}) completed")

            except Exception as e:
                logger.error(f"Task {task_id} ({task_type}) failed: {e}", exc_info=True)
                await task_service.update_status(db, task_id, "failed", error_message=str(e))

    # ------------------------------------------------------------------ #

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

        # The comparison is anchored to an AOI — fetch its bbox so we can crop
        # each scene to exactly the area of interest (a focused, exportable image).
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
            # `visual` is pre-scaled 8-bit RGB → no rescale (matches map_api).
            visual = assets.get("visual")
            return visual["href"] if visual and "href" in visual else None

        def _tile_url(item: Dict | None) -> str | None:
            href = _cog_href(item)
            if not href:
                return None
            cog = urllib.parse.quote(href, safe="")
            return (
                f"{Config.TITILER_PUBLIC_URL}/cog/tiles/{Config.TITILER_TMS}"
                f"/{{z}}/{{x}}/{{y}}.png?url={cog}"
            )

        def _image_url(item: Dict | None) -> str | None:
            """TiTiler bbox crop → one PNG of the AOI for this scene."""
            href = _cog_href(item)
            if not href or not bbox:
                return None
            cog = urllib.parse.quote(href, safe="")
            minx, miny, maxx, maxy = bbox
            return (
                f"{Config.TITILER_PUBLIC_URL}/cog/bbox/"
                f"{minx},{miny},{maxx},{maxy}.png?url={cog}&max_size=1024"
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

        await comparison_service.update_status(
            db, uuid.UUID(comparison_id_str), "completed", result
        )

        return result

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
        tile_url = payload.get("tile_url")  # active base-layer template from the FE
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

        # One run = one history entry; the preview is stored per run.
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
        # Persist as a NEW run (history preserved — old runs are not deleted).
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
