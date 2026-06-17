"""
YOLO-OBB satellite object detection.

Inference pipeline (prototyped in ml/yolo_obb.ipynb), built on the shared
:class:`ImageryProvider` so it draws imagery from the SAME tiles the map shows:

    AOI bbox ──► fetch base-layer mosaic (ImageryProvider) ──► chip with overlap
    ──► YOLO11-OBB predict per chip (imgsz > tile = magnify) ──► global NMS
    ──► reproject pixel OBB → lon/lat ──► GeoJSON FeatureCollection.

Heavy, CPU-bound work (model load + inference) is synchronous; callers on the
async worker offload it with `asyncio.to_thread`. The model is loaded once per
process (lazy singleton).
"""
from __future__ import annotations

import math
import os
import threading
import time
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw

from app.configs.config import Config
from app.services.imagery import (
    ImageryProvider,
    resolve_template,
    _pixel_to_lonlat,
    _source_label,
    _TILE_PX,
    _DEFAULT_SOURCE,
)
from app.utils.logger_utils import get_logger

logger = get_logger("MLService")

_DRAW_COLOR = {
    "plane": (52, 211, 153),
    "helicopter": (52, 211, 153),
    "ship": (34, 211, 238),
    "harbor": (250, 204, 21),
    "large-vehicle": (244, 114, 182),
    "small-vehicle": (244, 114, 182),
}
_DRAW_DEFAULT = (251, 191, 36)

DOTA_CLASSES: Dict[int, str] = {
    0: "plane", 1: "ship", 2: "storage-tank", 3: "baseball-diamond",
    4: "tennis-court", 5: "basketball-court", 6: "ground-track-field",
    7: "harbor", 8: "bridge", 9: "large-vehicle", 10: "small-vehicle",
    11: "helicopter", 12: "roundabout", 13: "soccer-ball-field", 14: "swimming-pool",
}

CLASS_GROUPS: Dict[str, List[int]] = {
    "aircraft": [0, 11],
    "vessels": [1, 7],
    "vehicles": [9, 10],
    "all": [0, 1, 9, 10, 11],
}

IDEAL_ZOOM: Dict[str, int] = {"aircraft": 18, "vessels": 17, "vehicles": 20, "all": 20}
PROFILE_MAX_TILES: Dict[str, int] = {"vehicles": 400, "all": 450, "aircraft": 600, "vessels": 700}
PROFILE_MIN_ZOOM: Dict[str, int] = {"vehicles": 15, "all": 15, "aircraft": 14, "vessels": 13}
_FALLBACK_MIN_ZOOM = 15
TILE_SIZE: Dict[str, int] = {"vehicles": 448, "vessels": 2048, "all": 640}
IMGSZ_SIZE: Dict[str, int] = {"vehicles": 1280, "aircraft": 1024, "vessels": 2048, "all": 1280}
OVERLAP_SIZE: Dict[str, int] = {"vehicles": 128, "vessels": 256, "all": 160}
_DEFAULT_TILE = 1024
_DEFAULT_IMGSZ = 1024
_DEFAULT_OVERLAP = 128
_DEDUPE_IOU = 0.55

MIN_RELIABLE_ZOOM: Dict[int, int] = {
    0: 17,
    1: 17,
    9: 19,
    10: 20,
    11: 18,
}

CLASS_SIZE_M: Dict[int, Tuple[float, float]] = {
    0: (6.0, 90.0),
    1: (4.0, 400.0),
    9: (4.0, 30.0),
    10: (2.0, 8.0),
    11: (6.0, 45.0),
}

CLASS_CONF_FLOOR: Dict[int, float] = {
    0: 0.10,
    1: 0.10,
    9: 0.10,
    10: 0.0,
    11: 0.10,
}


class MLService(ImageryProvider):
    """Lazy-loaded YOLO-OBB detector. One model instance per worker process."""

    def __init__(self) -> None:
        self._model: Any = None
        self._lock = threading.Lock()


    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                from ultralytics import YOLO

                logger.info("Loading YOLO-OBB model from %s", Config.DETECTION_MODEL_PATH)
                self._model = YOLO(Config.DETECTION_MODEL_PATH)
                logger.info("Model loaded: %d classes", len(self._model.names))
        return self._model

    @property
    def class_names(self) -> Dict[int, str]:
        return self._load_model().names

    def resolve_classes(self, group: str) -> List[int]:
        """Map a UI category to DOTA class ids (defaults to all movers)."""
        return CLASS_GROUPS.get(group, CLASS_GROUPS["all"])

    @staticmethod
    def _profile_for_classes(classes: List[int]) -> str:
        """Pick imagery/zoom tuning from the chosen classes. Vehicles win (they
        are the smallest → need the most resolution) when the set is mixed."""
        s = set(classes)
        if s & {9, 10}:
            return "vehicles"
        if s & {0, 11}:
            return "aircraft"
        if s & {1, 7}:
            return "vessels"
        return "all"

    @staticmethod
    def _budget_for(profile: str) -> int:
        """Mosaic tile budget for a profile (larger for coarse-zoom big objects)."""
        return PROFILE_MAX_TILES.get(profile, Config.DETECTION_MAX_TILES)

    @staticmethod
    def _min_zoom_for(profile: str) -> int:
        """Coarsest zoom a profile may fall back to before refusing the AOI."""
        return PROFILE_MIN_ZOOM.get(profile, _FALLBACK_MIN_ZOOM)

    def _auto_zoom(self, bbox: Tuple[float, float, float, float], object_class: str) -> int:
        """Highest zoom ≤ the profile's ideal that fits the tile budget."""
        return self._zoom_for_budget(
            bbox, IDEAL_ZOOM.get(object_class, 19),
            self._budget_for(object_class), self._min_zoom_for(object_class),
        )


    def _detect_tiled(
        self,
        mosaic: Image.Image,
        tile: int,
        overlap: int,
        conf: float,
        classes: List[int] | None,
        iou: float = 0.45,
        imgsz: int = _DEFAULT_IMGSZ,
    ) -> List[Tuple[np.ndarray, int, float]]:
        """
        Chip the mosaic into `tile`-px windows (with `overlap`) and run the model
        on each at `imgsz` (decoupled → up-scales small objects), translating every
        OBB back to global mosaic-pixel coords; then a global NMS removes the
        duplicates produced where tiles overlap.
        """
        model = self._load_model()
        width, height = mosaic.size
        step = tile - overlap
        dets: List[Tuple[np.ndarray, int, float]] = []

        for top in range(0, max(1, height - overlap), step):
            for left in range(0, max(1, width - overlap), step):
                crop = mosaic.crop(
                    (left, top, min(left + tile, width), min(top + tile, height))
                )
                result = model.predict(
                    crop, imgsz=imgsz, conf=conf, iou=iou, classes=classes,
                    agnostic_nms=False, max_det=3000, verbose=False,
                )[0]
                if result.obb is None:
                    continue
                polys = result.obb.xyxyxyxy.cpu().numpy()
                cls = result.obb.cls.cpu().numpy().astype(int)
                confs = result.obb.conf.cpu().numpy()
                offset = np.array([left, top], dtype=np.float64)
                for poly, c, cf in zip(polys, cls, confs):
                    dets.append((poly + offset, int(c), float(cf)))

        return self._dedupe(dets, _DEDUPE_IOU)

    @staticmethod
    def _obb_iou(rect_a, area_a: float, rect_b, area_b: float) -> float:
        """IoU of two oriented boxes (cv2 RotatedRect tuples) via their true
        rotated-polygon intersection. Returns 0 when they don't overlap."""
        import cv2

        ok, region = cv2.rotatedRectangleIntersection(rect_a, rect_b)
        if not ok or region is None:
            return 0.0
        inter = abs(cv2.contourArea(region))
        union = area_a + area_b - inter
        return float(inter / union) if union > 0 else 0.0

    @staticmethod
    def _dedupe(
        dets: List[Tuple[np.ndarray, int, float]], iou_thresh: float = _DEDUPE_IOU
    ) -> List[Tuple[np.ndarray, int, float]]:
        """Greedy NMS on the OBBs' TRUE rotated geometry, applied PER CLASS so a
        large-vehicle box never suppresses a nearby small-vehicle box. A cheap
        axis-aligned-envelope test prunes obvious non-overlaps before the exact
        (but costlier) oriented-IoU is computed. Only removes the near-duplicate
        boxes produced where tiles overlap; distinct adjacent cars are kept."""
        if not dets:
            return dets
        import cv2

        kept: List[Tuple[np.ndarray, int, float]] = []
        for cls_id in sorted({c for _, c, _ in dets}):
            cls_dets = [d for d in dets if d[1] == cls_id]
            polys = [p.astype(np.float32) for p, _, _ in cls_dets]
            boxes = np.array(
                [[p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()] for p in polys]
            )
            rects = [cv2.minAreaRect(p) for p in polys]
            areas = np.array([r[1][0] * r[1][1] for r in rects])
            scores = np.array([cf for _, _, cf in cls_dets])
            order = scores.argsort()[::-1]
            while order.size:
                i = order[0]
                kept.append(cls_dets[i])
                rest = order[1:]
                ex1 = np.maximum(boxes[i, 0], boxes[rest, 0])
                ey1 = np.maximum(boxes[i, 1], boxes[rest, 1])
                ex2 = np.minimum(boxes[i, 2], boxes[rest, 2])
                ey2 = np.minimum(boxes[i, 3], boxes[rest, 3])
                env_overlap = (ex2 > ex1) & (ey2 > ey1)
                suppress = np.zeros(rest.size, dtype=bool)
                for k in np.nonzero(env_overlap)[0]:
                    j = rest[k]
                    if MLService._obb_iou(rects[i], areas[i], rects[j], areas[j]) > iou_thresh:
                        suppress[k] = True
                order = rest[~suppress]
        return kept

    @staticmethod
    def _ground_sample_distance(z: int, lat: float) -> float:
        """Metres per pixel of a Web-Mercator basemap at zoom `z` and latitude
        `lat` (resolution shrinks with cos(lat))."""
        return 156543.03392 * math.cos(math.radians(lat)) / (2 ** z)

    @staticmethod
    def _filter_implausible(
        dets: List[Tuple[np.ndarray, int, float]],
        z: int,
        lat: float,
        user_conf: float,
    ) -> List[Tuple[np.ndarray, int, float]]:
        """Drop detections that can't be real: confidence below the per-class
        floor, or a ground footprint outside the class's plausible size band.
        This is what removes phantom ships on water/field texture and stray
        micro-boxes that a low confidence slider otherwise lets through."""
        if not dets:
            return dets
        import cv2

        gsd = MLService._ground_sample_distance(z, lat)
        kept: List[Tuple[np.ndarray, int, float]] = []
        for poly, c, cf in dets:
            if cf < max(user_conf, CLASS_CONF_FLOOR.get(c, 0.0)):
                continue
            lo, hi = CLASS_SIZE_M.get(c, (0.0, float("inf")))
            (w_px, h_px) = cv2.minAreaRect(poly.astype(np.float32))[1]
            longer_m = max(w_px, h_px) * gsd
            if lo <= longer_m <= hi:
                kept.append((poly, c, cf))
        return kept

    def _save_preview(
        self,
        mosaic: Image.Image,
        dets: List[Tuple[np.ndarray, int, float]],
        names: Dict[int, str],
        output_path: str,
    ) -> None:
        """Draw the detected OBBs on the mosaic and save it as a preview PNG."""
        vis = mosaic.convert("RGB")
        draw = ImageDraw.Draw(vis)
        for poly, c, _cf in dets:
            color = _DRAW_COLOR.get(names[c], _DRAW_DEFAULT)
            draw.polygon([(float(px), float(py)) for px, py in poly], outline=color, width=3)
        max_side = 1600
        if max(vis.size) > max_side:
            ratio = max_side / max(vis.size)
            vis = vis.resize((int(vis.width * ratio), int(vis.height * ratio)), Image.LANCZOS)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        vis.save(output_path, "PNG", optimize=True)

    def detect_bbox(
        self,
        bbox: Tuple[float, float, float, float],
        object_class: str = "all",
        classes: List[int] | None = None,
        zoom: int | None = None,
        conf: float = 0.25,
        iou: float = 0.45,
        tile: int | None = None,
        overlap: int | None = None,
        imgsz: int | None = None,
        source: str = _DEFAULT_SOURCE,
        tile_url: str | None = None,
        output_path: str | None = None,
    ) -> Dict[str, Any]:
        """
        Detect over a geographic bbox → GeoJSON FeatureCollection (+ metadata).
        Imagery comes from `tile_url` (the map's active base layer) via the shared
        ImageryProvider; zoom / chip size are tuned from the chosen classes.
        """
        if classes is None:
            classes = self.resolve_classes(object_class)
        profile = self._profile_for_classes(classes)

        ceiling = IDEAL_ZOOM.get(profile, 20)
        budget = self._budget_for(profile)
        if zoom is not None:
            z = self._zoom_for_budget(
                bbox, min(int(zoom), ceiling), budget, self._min_zoom_for(profile)
            )
        else:
            z = self._auto_zoom(bbox, profile)
        tile = tile or TILE_SIZE.get(profile, _DEFAULT_TILE)
        overlap = overlap or OVERLAP_SIZE.get(profile, _DEFAULT_OVERLAP)
        imgsz = imgsz or IMGSZ_SIZE.get(profile, _DEFAULT_IMGSZ)
        names = self.class_names

        url_tpl = resolve_template(tile_url, source)
        source = _source_label(url_tpl)
        logger.info("Detection: bbox=%s z=%s classes=%s conf=%s src=%s", bbox, z, classes, conf, source)
        t0 = time.perf_counter()
        mosaic, x0, y0, n_tiles, n_failed = self._fetch_mosaic(bbox, z, url_tpl, budget)
        dets = self._detect_tiled(mosaic, tile, overlap, conf, classes, iou, imgsz)
        lat_center = (bbox[1] + bbox[3]) / 2.0
        raw_count = len(dets)
        dets = self._filter_implausible(dets, z, lat_center, conf)
        elapsed = round(time.perf_counter() - t0, 1)
        logger.info(
            "Detection: %d objects (%d dropped as implausible) on %s mosaic in %ss",
            len(dets), raw_count - len(dets), mosaic.size, elapsed,
        )

        if output_path:
            try:
                self._save_preview(mosaic, dets, names, output_path)
            except Exception as e:
                logger.warning("Could not save detection preview: %s", e)

        ox, oy = x0 * _TILE_PX, y0 * _TILE_PX
        features: List[Dict[str, Any]] = []
        counts: Dict[str, int] = {}
        for poly, c, cf in dets:
            ring = [list(_pixel_to_lonlat(ox + px, oy + py, z)) for px, py in poly]
            ring.append(ring[0])
            label = names[c]
            counts[label] = counts.get(label, 0) + 1
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": {"object_type": label, "confidence": round(cf, 4)},
                }
            )

        underresolved = sorted(
            {names[c] for c in classes if z < MIN_RELIABLE_ZOOM.get(c, 0)}
        )
        note = None
        if underresolved:
            need = max(MIN_RELIABLE_ZOOM.get(c, 0) for c in classes)
            note = (
                f"Imagery was coarsened to zoom {z} to fit the AOI — too low for: "
                f"{', '.join(underresolved)}. These need ~z{need} (small vehicles "
                "are only a few pixels below that and get missed). Draw a SMALLER "
                "AOI, or pass an explicit higher `zoom`, for reliable results."
            )

        return {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "count": len(features),
                "counts_by_type": counts,
                "zoom": z,
                "ideal_zoom": IDEAL_ZOOM.get(profile, 19),
                "source": source,
                "profile": profile,
                "classes": classes,
                "confidence": conf,
                "iou": iou,
                "tile": tile,
                "overlap": overlap,
                "imgsz": imgsz,
                "mosaic_size": list(mosaic.size),
                "tiles_total": n_tiles,
                "tiles_failed": n_failed,
                "model": os.path.basename(Config.DETECTION_MODEL_PATH),
                "elapsed_s": elapsed,
                "filtered_out": raw_count - len(features),
                "underresolved_classes": underresolved,
                "note": note,
            },
        }


ml_service = MLService()
