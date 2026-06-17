"""
Ingest Sentinel-2 L2A metadata into the local PgSTAC catalogue.

This is what makes the app "PgSTAC-primary": it pulls STAC item metadata from a
remote catalogue (Element 84 Earth Search by default) for a bounding box + time
range and bulk-loads it into PgSTAC via pypgstac. Only metadata is stored — each
item's asset hrefs keep pointing at the public Sentinel-2 COGs on S3, so Titiler
reads pixels directly and we never host imagery ourselves.

Areas / dates not ingested here are still served live by the remote fallback in
`app.services.pgstac_service`.

Examples
--------
    # Vietnam, last 6 months, low cloud (defaults)
    python -m scripts.ingest_sentinel

    # A focused AOI + explicit window
    python -m scripts.ingest_sentinel \
        --bbox 105.6 20.9 106.0 21.2 \
        --datetime 2024-01-01/2024-12-31 \
        --max-cloud 15 --max-items 300

Requires `pypgstac` (see requirements.txt) and a PgSTAC schema already migrated
(`pypgstac migrate`).
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx

from app.configs.config import Config, PostgresConfig
from app.utils.logger_utils import get_logger

logger = get_logger("IngestSentinel")

_DEFAULT_BBOX = [102.1, 8.2, 109.6, 23.4]


def _default_dsn() -> str:
    """Sync libpq DSN for pypgstac, overridable by env. PostgresConfig holds the
    asyncpg URL the app uses; pypgstac needs the plain `postgresql://` form."""
    explicit = os.getenv("PGSTAC_DSN") or os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    pc = PostgresConfig()
    return f"postgresql://{pc.USER}:{pc.PASSWORD}@{pc.HOST}:{pc.PORT}/{pc.DB}"


def _normalize_datetime(value: Optional[str]) -> Optional[str]:
    """STAC /search needs full RFC3339 datetimes; a date-only input (YYYY-MM-DD)
    is rejected with 400. Expand each bound to a full-day instant, and a lone date
    to a whole-day range."""
    def _bound(part: str, *, end: bool) -> str:
        part = part.strip()
        if part in ("", ".."):
            return part
        if "T" in part:
            return part
        return f"{part}T23:59:59Z" if end else f"{part}T00:00:00Z"

    if not value:
        return value
    if "/" in value:
        start, stop = value.split("/", 1)
        return f"{_bound(start, end=False)}/{_bound(stop, end=True)}"
    if "T" in value:
        return value
    return f"{_bound(value, end=False)}/{_bound(value, end=True)}"


def _fetch_collection(client: httpx.Client, collection: str) -> Optional[dict]:
    resp = client.get(f"/collections/{collection}")
    if resp.status_code != 200:
        logger.warning("Collection %s not found upstream (%s)", collection, resp.status_code)
        return None
    return resp.json()


def _search_items(
    client: httpx.Client,
    collection: str,
    bbox: list[float],
    datetime_str: Optional[str],
    max_cloud: Optional[int],
    max_items: int,
    page_size: int = 100,
) -> Iterable[dict]:
    """Page through the remote /search endpoint, yielding STAC item features until
    `max_items` is reached or the catalogue runs out (follows the `next` link)."""
    body: dict[str, Any] = {
        "collections": [collection],
        "bbox": bbox,
        "limit": min(page_size, max_items),
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    if datetime_str:
        body["datetime"] = datetime_str
    if max_cloud is not None:
        body["query"] = {"eo:cloud_cover": {"lte": max_cloud}}

    url = "/search"
    yielded = 0
    while url and yielded < max_items:
        resp = client.post(url, json=body)
        if resp.status_code >= 400:
            logger.error("Search failed %s: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
        payload = resp.json() or {}
        for feature in payload.get("features", []):
            yield feature
            yielded += 1
            if yielded >= max_items:
                return

        nxt = next((lk for lk in payload.get("links", []) if lk.get("rel") == "next"), None)
        if not nxt:
            return
        url = nxt["href"]
        body = nxt.get("body", body)


def _write_ndjson(path: Path, records: Iterable[dict]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record))
            fh.write("\n")
            count += 1
    return count


def _load_into_pgstac(dsn: str, collection_file: Path, items_file: Path) -> None:
    from pypgstac.db import PgstacDB
    from pypgstac.load import Loader, Methods

    with PgstacDB(dsn=dsn) as db:
        loader = Loader(db=db)
        logger.info("Loading collection into PgSTAC")
        loader.load_collections(str(collection_file), insert_mode=Methods.upsert)
        logger.info("Loading items into PgSTAC")
        loader.load_items(str(items_file), insert_mode=Methods.upsert)


def ingest(
    collection: str,
    bbox: list[float],
    datetime_str: Optional[str],
    max_cloud: Optional[int],
    max_items: int,
    dsn: str,
    search_url: str,
) -> None:
    datetime_str = _normalize_datetime(datetime_str)
    logger.info("Ingesting %s from %s | bbox=%s datetime=%s cloud<=%s max=%d",
                collection, search_url, bbox, datetime_str, max_cloud, max_items)

    with httpx.Client(base_url=search_url.rstrip("/"), timeout=60.0,
                      headers={"Accept": "application/geo+json, application/json"},
                      follow_redirects=True) as client:
        collection_doc = _fetch_collection(client, collection)
        if not collection_doc:
            raise SystemExit(f"Cannot ingest: collection '{collection}' missing upstream")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            collection_file = tmp_dir / "collection.ndjson"
            items_file = tmp_dir / "items.ndjson"

            _write_ndjson(collection_file, [collection_doc])
            n_items = _write_ndjson(
                items_file,
                _search_items(client, collection, bbox, datetime_str, max_cloud, max_items),
            )
            logger.info("Fetched %d items", n_items)
            if n_items == 0:
                logger.warning("No items matched — nothing loaded. Widen bbox/dates/cloud.")
                return

            _load_into_pgstac(dsn, collection_file, items_file)
            logger.info("Done: %d %s items now in PgSTAC", n_items, collection)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest Sentinel-2 metadata into PgSTAC")
    parser.add_argument("--collection", default=Config.STAC_DEFAULT_COLLECTION)
    parser.add_argument("--bbox", type=float, nargs=4,
                        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
                        default=_DEFAULT_BBOX)
    parser.add_argument("--datetime", dest="datetime_str", default=None,
                        help="RFC3339 instant or START/END range")
    parser.add_argument("--max-cloud", type=int, default=Config.STAC_MAX_CLOUD_COVER)
    parser.add_argument("--max-items", type=int, default=200)
    parser.add_argument("--dsn", default=_default_dsn())
    parser.add_argument("--search-url", default=Config.STAC_SEARCH_URL)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    ingest(
        collection=args.collection,
        bbox=args.bbox,
        datetime_str=args.datetime_str,
        max_cloud=args.max_cloud,
        max_items=args.max_items,
        dsn=args.dsn,
        search_url=args.search_url,
    )
