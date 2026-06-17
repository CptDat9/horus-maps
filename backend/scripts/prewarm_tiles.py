"""
Prewarm the Redis tile cache for demo areas.

Cold Sentinel-2 tiles are slow on first view because TiTiler must read the COG
from a public S3 bucket in us-west-2 (~1 MB/s, ~0.65 s RTT from here), so the
*first* open of a never-read scene takes ~20-30 s. Once fetched, the rendered
PNG is cached in Redis (1 day) and served in milliseconds.

This script walks the XYZ tiles covering each demo area over a zoom range and
GETs them through the API's tile endpoint, which populates that Redis cache.
Run it ahead of a demo so the areas you present open instantly. It is a pure
client — it only issues HTTP GETs, holds no DB connection, and is safe to re-run
(already-cached tiles return instantly).

Run from a container on the compose network (the `stac` service has the code
mounted and can reach the API by service name):

    docker compose exec stac python -m scripts.prewarm_tiles --base-url http://api:8000

Custom area:

    docker compose exec stac python -m scripts.prewarm_tiles --base-url http://api:8000 \
        --name myaoi --bbox 105.6 20.9 106.0 21.2 --min-zoom 9 --max-zoom 14
"""
from __future__ import annotations

import argparse
import asyncio
import math
from typing import Iterator, Tuple

import httpx

from app.utils.logger_utils import get_logger

logger = get_logger("PrewarmTiles")

DEMO_AREAS: dict[str, list[float]] = {
    "hanoi": [105.70, 20.90, 106.05, 21.15],
    "hcmc": [106.55, 10.65, 106.85, 10.90],
    "danang": [108.10, 15.95, 108.30, 16.15],
}


def _lon_to_x(lon: float, z: int) -> int:
    n = 2 ** z
    return max(0, min(n - 1, int((lon + 180.0) / 360.0 * n)))


def _lat_to_y(lat: float, z: int) -> int:
    n = 2 ** z
    lat = max(-85.05112878, min(85.05112878, lat))
    lat_rad = math.radians(lat)
    return max(0, min(n - 1, int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)))


def _tiles_for_bbox(bbox: list[float], z: int) -> Iterator[Tuple[int, int, int]]:
    min_lon, min_lat, max_lon, max_lat = bbox
    x0, x1 = _lon_to_x(min_lon, z), _lon_to_x(max_lon, z)
    y0, y1 = _lat_to_y(max_lat, z), _lat_to_y(min_lat, z)
    for x in range(min(x0, x1), max(x0, x1) + 1):
        for y in range(min(y0, y1), max(y0, y1) + 1):
            yield z, x, y


async def _warm_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    layer: str,
    z: int,
    x: int,
    y: int,
    counters: dict[str, int],
) -> None:
    async with sem:
        try:
            resp = await client.get(f"/api/tiles/{layer}/{z}/{x}/{y}")
        except httpx.HTTPError as err:
            counters["error"] += 1
            logger.debug("tile %d/%d/%d failed: %s", z, x, y, err)
            return
    if resp.status_code == 200:
        counters["ok"] += 1
    elif resp.status_code == 204:
        counters["empty"] += 1
    else:
        counters["error"] += 1
    done = counters["ok"] + counters["empty"] + counters["error"]
    if done % 25 == 0:
        logger.info("  …%d/%d (ok=%d empty=%d err=%d)",
                    done, counters["total"], counters["ok"], counters["empty"], counters["error"])


async def prewarm(
    base_url: str,
    areas: dict[str, list[float]],
    layer: str,
    min_zoom: int,
    max_zoom: int,
    concurrency: int,
) -> None:
    tasks_spec: list[Tuple[int, int, int]] = []
    for name, bbox in areas.items():
        area_tiles = [t for z in range(min_zoom, max_zoom + 1) for t in _tiles_for_bbox(bbox, z)]
        logger.info("Area %-8s z%d-%d → %d tiles", name, min_zoom, max_zoom, len(area_tiles))
        tasks_spec.extend(area_tiles)

    counters = {"ok": 0, "empty": 0, "error": 0, "total": len(tasks_spec)}
    logger.info("Prewarming %d tiles for layer '%s' via %s (concurrency=%d)",
                counters["total"], layer, base_url, concurrency)

    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(90.0, connect=5.0)) as client:
        await asyncio.gather(*(
            _warm_one(client, sem, layer, z, x, y, counters) for (z, x, y) in tasks_spec
        ))

    logger.info("Done: ok=%d (cached) empty=%d (no imagery) err=%d / total=%d",
                counters["ok"], counters["empty"], counters["error"], counters["total"])


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prewarm the Redis tile cache for demo areas")
    p.add_argument("--base-url", default="http://api:8000",
                   help="API origin (default http://api:8000 on the compose network)")
    p.add_argument("--layer", default="sentinel-2-true-color")
    p.add_argument("--min-zoom", type=int, default=8)
    p.add_argument("--max-zoom", type=int, default=13)
    p.add_argument("--concurrency", type=int, default=6,
                   help="Concurrent tile requests; the slow ~1 MB/s S3 link is the real cap")
    p.add_argument("--name", default=None, help="Custom area name (with --bbox)")
    p.add_argument("--bbox", type=float, nargs=4,
                   metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
                   default=None, help="Custom bbox; overrides the built-in demo areas")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.bbox:
        areas = {args.name or "custom": args.bbox}
    else:
        areas = DEMO_AREAS
    asyncio.run(prewarm(
        base_url=args.base_url.rstrip("/"),
        areas=areas,
        layer=args.layer,
        min_zoom=args.min_zoom,
        max_zoom=args.max_zoom,
        concurrency=args.concurrency,
    ))
