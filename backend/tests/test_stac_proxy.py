"""
Offline tests for the /api/stac gateway: requests proxy to the stac-fastapi
service, and fall back to pgstac_service when that service is unreachable.
"""
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.apis import stac_api
from app.databases.deps import get_db
from app.main import app


class _FakeSession:
    async def execute(self, *_a, **_k):
        raise AssertionError("DB should not be touched on the proxy path")


async def _fake_db():
    yield _FakeSession()


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = _fake_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_search_proxies_to_stac_fastapi(client, monkeypatch):
    upstream = {"type": "FeatureCollection", "features": [{"id": "scene-1"}]}
    monkeypatch.setattr(
        stac_api._stac, "request", AsyncMock(return_value=httpx.Response(200, json=upstream))
    )

    resp = client.post("/api/stac/search", json={"collections": ["sentinel-2-l2a"], "limit": 1})

    assert resp.status_code == 200
    assert resp.json() == upstream


def test_search_falls_back_when_stac_service_down(client, monkeypatch):
    monkeypatch.setattr(
        stac_api._stac, "request", AsyncMock(side_effect=httpx.ConnectError("stac down"))
    )
    monkeypatch.setattr(
        stac_api.pgstac_service,
        "search_items",
        AsyncMock(return_value=[
            {"id": "local-1", "collection_id": "sentinel-2-l2a", "data": {}, "datetime": None}
        ]),
    )

    resp = client.post("/api/stac/search", json={"collections": ["sentinel-2-l2a"], "limit": 1})

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "FeatureCollection"
    assert [f["id"] for f in body["features"]] == ["local-1"]
