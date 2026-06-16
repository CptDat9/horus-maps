"""
Unit tests for the STAC / Sentinel tile pipeline — the part that was broken.
These run fully offline (no Postgres / Redis / Titiler / network).
"""
import math
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.apis import map_api
from app.configs.config import Config
from app.services.stac_client import StacClient, _feature_to_item, _parse_dt
from app.utils.tile_utils import coarse_tile, tile_to_bbox


# --------------------------------------------------------------------------- #
#  Tile math
# --------------------------------------------------------------------------- #

def test_tile_to_bbox_world_origin():
    # z=0 single tile covers the whole Web-Mercator world.
    minx, miny, maxx, maxy = tile_to_bbox(0, 0, 0)
    assert minx == pytest.approx(-180.0)
    assert maxx == pytest.approx(180.0)
    assert maxy == pytest.approx(85.0511, abs=1e-3)
    assert miny == pytest.approx(-85.0511, abs=1e-3)


def test_tile_to_bbox_is_ordered():
    minx, miny, maxx, maxy = tile_to_bbox(10, 800, 450)
    assert minx < maxx and miny < maxy


def test_coarse_tile_groups_high_zoom():
    # A z=14 tile collapses onto its z=9 ancestor (shared scene lookup).
    assert coarse_tile(14, 13000, 7000, base_z=9) == (9, 13000 >> 5, 7000 >> 5)


def test_coarse_tile_noop_below_base():
    assert coarse_tile(6, 33, 21, base_z=9) == (6, 33, 21)


# --------------------------------------------------------------------------- #
#  STAC client helpers
# --------------------------------------------------------------------------- #

def test_parse_dt_handles_rfc3339_z():
    dt = _parse_dt("2024-05-01T10:20:30Z")
    assert dt == datetime(2024, 5, 1, 10, 20, 30, tzinfo=timezone.utc)


def test_parse_dt_bad_value():
    assert _parse_dt("not-a-date") is None
    assert _parse_dt(None) is None


def test_feature_to_item_normalizes():
    feature = {
        "id": "S2_ABC",
        "collection": "sentinel-2-l2a",
        "properties": {"datetime": "2024-01-02T00:00:00Z", "eo:cloud_cover": 3.1},
        "assets": {"visual": {"href": "https://x/visual.tif"}},
    }
    item = _feature_to_item(feature)
    assert item["id"] == "S2_ABC"
    assert item["collection_id"] == "sentinel-2-l2a"
    assert item["data"] is feature
    assert item["datetime"].year == 2024


# --------------------------------------------------------------------------- #
#  Remote STAC search request building / response parsing (mocked httpx)
# --------------------------------------------------------------------------- #

class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("err", request=None, response=self)


class _FakeHttp:
    """Captures the last POST body so we can assert the query we send."""
    def __init__(self, payload):
        self._payload = payload
        self.last_json = None

    async def post(self, url, json=None):
        self.last_json = json
        return _FakeResponse(self._payload)


@pytest.mark.asyncio
async def test_search_builds_cloud_filter_and_sort(monkeypatch):
    client = StacClient("https://example.test/v1")
    fake = _FakeHttp({"features": []})
    monkeypatch.setattr(client, "_http", lambda: fake)

    await client.search(
        collections=["sentinel-2-l2a"],
        bbox=[100.0, 10.0, 101.0, 11.0],
        limit=5,
        max_cloud_cover=20,
        sort_by_cloud=True,
    )

    body = fake.last_json
    assert body["collections"] == ["sentinel-2-l2a"]
    assert body["bbox"] == [100.0, 10.0, 101.0, 11.0]
    assert body["limit"] == 5
    assert body["query"] == {"eo:cloud_cover": {"lte": 20}}
    assert body["sortby"][0]["field"] == "properties.eo:cloud_cover"
    assert body["sortby"][0]["direction"] == "asc"


@pytest.mark.asyncio
async def test_search_parses_features(monkeypatch):
    client = StacClient("https://example.test/v1")
    payload = {"features": [{
        "id": "S2_1", "collection": "sentinel-2-l2a",
        "properties": {"datetime": "2024-03-03T00:00:00Z"},
        "assets": {"visual": {"href": "https://x/v.tif"}},
    }]}
    monkeypatch.setattr(client, "_http", lambda: _FakeHttp(payload))

    items = await client.search(collections=["sentinel-2-l2a"], limit=1)
    assert len(items) == 1
    assert items[0]["id"] == "S2_1"
    assert items[0]["datetime"].month == 3


# --------------------------------------------------------------------------- #
#  Titiler tile URL construction (the actual rendering bug)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_build_stac_tile_url_visual_has_no_rescale(monkeypatch):
    item = {"id": "S2_1", "data": {"assets": {"visual": {"href": "https://b/cogs/visual.tif"}}}}
    monkeypatch.setattr(map_api.cache_service, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(map_api.cache_service, "set", AsyncMock(return_value=True))
    monkeypatch.setattr(
        map_api.pgstac_service, "search_items_by_bbox", AsyncMock(return_value=[item])
    )

    layer = {"options": {"collection": "sentinel-2-l2a", "asset": "visual", "rescale": "0,3000"}}
    url = await map_api._build_stac_tile_url(None, layer, 12, 3200, 2000)

    assert f"/cog/tiles/{Config.TITILER_TMS}/12/3200/2000.png" in url
    # visual is pre-scaled → rescale must be dropped even if present in options
    assert "rescale" not in url
    # href is URL-encoded into the url= param
    assert "url=https%3A%2F%2Fb%2Fcogs%2Fvisual.tif" in url


@pytest.mark.asyncio
async def test_build_stac_tile_url_band_keeps_rescale(monkeypatch):
    item = {"id": "S2_1", "data": {"assets": {"nir": {"href": "https://b/cogs/nir.tif"}}}}
    monkeypatch.setattr(map_api.cache_service, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(map_api.cache_service, "set", AsyncMock(return_value=True))
    monkeypatch.setattr(
        map_api.pgstac_service, "search_items_by_bbox", AsyncMock(return_value=[item])
    )

    layer = {"options": {"asset": "nir", "rescale": "0,4000", "colormap_name": "greens"}}
    url = await map_api._build_stac_tile_url(None, layer, 11, 1, 1)
    assert "rescale=0,4000" in url
    assert "colormap_name=greens" in url


@pytest.mark.asyncio
async def test_build_stac_tile_url_no_imagery_returns_none(monkeypatch):
    monkeypatch.setattr(map_api.cache_service, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(
        map_api.pgstac_service, "search_items_by_bbox", AsyncMock(return_value=[])
    )
    url = await map_api._build_stac_tile_url(None, {"options": {}}, 12, 1, 1)
    assert url is None
