"""
Shared satellite-imagery provider.

Slippy-map tile math + concurrent mosaic fetch, reused by everything that needs
the AOI's imagery (object detection AND the AOI image export). `MLService`
inherits :class:`ImageryProvider`, so detection and export draw from exactly the
same code path and the same base-layer tiles the user is viewing.
"""

from __future__ import annotations

import io
import math
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Tuple
from urllib.parse import urlparse

import httpx
from PIL import Image

from app.configs.config import Config
from app.utils.logger_utils import get_logger

logger = get_logger("Imagery")

_TILE_PX = 256

_TILE_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=10.0)
_TILE_RETRIES = 3
_FETCH_WORKERS = 8  # so threads
_HTTP_HEADERS = {"User-Agent": "horus-maps/1.0 (+imagery)"}
_MIN_ZOOM = 15

TILE_SOURCES: Dict[str, str] = {
    "google": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    "esri": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/{z}/{y}/{x}"
    ),
}
_DEFAULT_SOURCE = "google"

_ALLOWED_TILE_HOSTS = {
    "mt0.google.com",
    "mt1.google.com",
    "mt2.google.com",
    "mt3.google.com",
    "server.arcgisonline.com",
    "tile.openstreetmap.org",
    "a.tile.openstreetmap.org",
    "b.tile.openstreetmap.org",
    "c.tile.openstreetmap.org",
}


def _deg2tile(lat: float, lon: float, z: int) -> Tuple[int, int]:
    """WGS84 → slippy-map tile index (x, y) at zoom z."""
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


def _pixel_to_lonlat(px: float, py: float, z: int) -> Tuple[float, float]:
    """Global map-pixel (px, py) at zoom z → (lon, lat) — inverse Web-Mercator.
    Casts to native float (np.float64 is not JSON-serialisable)."""
    n = 2**z
    lon = px / (_TILE_PX * n) * 360.0 - 180.0
    lat = math.degrees(
        math.atan(math.sinh(math.pi * (1.0 - 2.0 * py / (_TILE_PX * n))))
    )
    return float(lon), float(lat)


def _valid_tile_template(url: str | None) -> bool:
    if (
        not url
        or not isinstance(url, str)
        or not url.startswith(("http://", "https://"))
    ):
        return False
    if not all(p in url for p in ("{x}", "{y}", "{z}")):
        return False
    try:
        return (urlparse(url).hostname or "") in _ALLOWED_TILE_HOSTS
    except Exception:
        return False


def _source_label(url: str) -> str:
    u = url.lower()
    if "google" in u:
        return "google"
    if "arcgisonline" in u:
        return "esri"
    if "openstreetmap" in u:
        return "osm"
    return "custom"


def resolve_template(tile_url: str | None, source: str = _DEFAULT_SOURCE) -> str:
    """The base-layer template to fetch: the client's `tile_url` if trusted,
    else a named fallback source."""
    if _valid_tile_template(tile_url):
        return tile_url  # type: ignore[return-value]
    return TILE_SOURCES.get(source, TILE_SOURCES[_DEFAULT_SOURCE])


class ImageryProvider:
    """Fetches and stitches XYZ tiles into a georeferenced mosaic."""

    @staticmethod
    def _zoom_for_budget(
        bbox: Tuple[float, float, float, float],
        ideal: int,
        budget: int,
        min_zoom: int = _MIN_ZOOM,
    ) -> int:
        """Highest zoom ≤ ideal whose mosaic stays within `budget` tiles, never
        going below `min_zoom` (large objects tolerate a lower floor than cars)."""
        min_lon, min_lat, max_lon, max_lat = bbox
        for z in range(ideal, min_zoom - 1, -1):
            x0, y0 = _deg2tile(max_lat, min_lon, z)
            x1, y1 = _deg2tile(min_lat, max_lon, z)
            if (x1 - x0 + 1) * (y1 - y0 + 1) <= budget:
                return z
        return min_zoom

    def _fetch_mosaic(
        self,
        bbox: Tuple[float, float, float, float],
        z: int,
        url_tpl: str,
        max_tiles: int | None = None,
    ) -> Tuple[Image.Image, int, int, int, int]:
        """
        Download every tile covering bbox (from the XYZ template) and stitch them
        into one RGB image. bbox = (min_lon, min_lat, max_lon, max_lat). Returns
        (mosaic, x0, y0, n_tiles, n_failed); (x0, y0) is the top-left tile index,
        needed to reproject pixels later.
        """
        budget = max_tiles or Config.DETECTION_MAX_TILES
        min_lon, min_lat, max_lon, max_lat = bbox
        x0, y0 = _deg2tile(max_lat, min_lon, z)
        x1, y1 = _deg2tile(min_lat, max_lon, z)
        cols, rows = x1 - x0 + 1, y1 - y0 + 1

        if cols * rows > budget:
            raise ValueError(
                f"AOI too large at zoom {z}: {cols}x{rows} tiles (> {budget}). "
                "Draw a smaller area or lower the zoom."
            )

        mosaic = Image.new("RGB", (cols * _TILE_PX, rows * _TILE_PX))
        jobs = [
            (i, j, xt, yt)
            for i, xt in enumerate(range(x0, x1 + 1))
            for j, yt in enumerate(range(y0, y1 + 1))
        ]

        def _fetch_one(client: httpx.Client, xt: int, yt: int) -> Image.Image | None:
            url = url_tpl.format(z=z, x=xt, y=yt)
            for attempt in range(_TILE_RETRIES):
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    return Image.open(io.BytesIO(resp.content)).convert("RGB")
                except Exception as e:
                    if attempt == _TILE_RETRIES - 1:
                        logger.warning(
                            "Tile z=%s x=%s y=%s failed (%s) — blank", z, xt, yt, e
                        )
                        return None
            return None

        failed = 0
        with httpx.Client(
            timeout=_TILE_TIMEOUT,
            headers=_HTTP_HEADERS,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=_FETCH_WORKERS),
        ) as client:
            with ThreadPoolExecutor(
                max_workers=_FETCH_WORKERS
            ) as pool:  # tao threadpool voi semaphore = 8 chay song song
                #  Bên trong j, các phần tử được đánh chỉ số từ 0 đến 3:

                # j[0] chính là i (vị trí cột)

                # j[1] chính là j (vị trí hàng)

                # j[2] chính là xt (tọa độ X của tile)

                # j[3] chính là yt (tọa độ Y của tile)
                results = pool.map(
                    lambda j: (j[0], j[1], _fetch_one(client, j[2], j[3])), jobs
                )
                for i, j, tile in results:
                    if tile is None:
                        failed += 1
                        continue
                    mosaic.paste(tile, (i * _TILE_PX, j * _TILE_PX))

        if failed:
            logger.warning("Mosaic z=%s: %d/%d tiles missing", z, failed, len(jobs))
        return mosaic, x0, y0, len(jobs), failed

    def export_aoi_image(
        self,
        bbox: Tuple[float, float, float, float],
        output_path: str,
        tile_url: str | None = None,
        source: str = _DEFAULT_SOURCE,
        zoom: int | None = None,
        max_tiles: int = 196,
        max_side: int = 2048,
    ) -> Dict[str, Any]:
        """
        Build and save a viewable PNG of the AOI from the SAME base-layer tiles
        detection uses. Synchronous; capped at `max_tiles` so the on-demand HTTP
        export stays responsive.
        """
        url_tpl = resolve_template(tile_url, source)
        z = zoom or self._zoom_for_budget(bbox, 19, max_tiles)
        mosaic, _x0, _y0, n_tiles, n_failed = self._fetch_mosaic(
            bbox, z, url_tpl, max_tiles
        )
        if max(mosaic.size) > max_side:
            ratio = max_side / max(mosaic.size)
            mosaic = mosaic.resize(
                (int(mosaic.width * ratio), int(mosaic.height * ratio)), Image.LANCZOS
            )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        mosaic.save(output_path, "PNG", optimize=True)
        return {
            "zoom": z,
            "source": _source_label(url_tpl),
            "size": list(mosaic.size),
            "tiles_total": n_tiles,
            "tiles_failed": n_failed,
        }
