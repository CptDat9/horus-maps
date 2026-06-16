"""
API smoke tests that run fully offline by overriding the DB dependency with an
in-memory fake (no Postgres / Redis / RabbitMQ needed).
"""
import pytest
from fastapi.testclient import TestClient

from app.apis import map_api
from app.databases.deps import get_db
from app.main import app


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    """Returns no rows for every query → map_service falls back to defaults."""
    async def execute(self, *_a, **_k):
        return _FakeResult([])

    async def scalar(self, *_a, **_k):
        return None


async def _fake_db():
    yield _FakeSession()


@pytest.fixture
def client(monkeypatch):
    # The layers endpoint hits Redis for caching; force a cache miss offline.
    async def _miss(*_a, **_k):
        raise RuntimeError("no redis in tests")

    monkeypatch.setattr(map_api.cache_service, "get", _miss)
    monkeypatch.setattr(map_api.cache_service, "set", _miss)

    app.dependency_overrides[get_db] = _fake_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_get_layers_returns_default_layers(client):
    response = client.get("/api/layers")
    assert response.status_code == 200
    layers = response.json()
    assert isinstance(layers, list) and layers

    sentinel = next((l for l in layers if l["id"] == "sentinel-2-true-color"), None)
    assert sentinel is not None
    # Contract the frontend relies on to decide visibility / ordering.
    assert "is_active" in sentinel and "display_order" in sentinel
    assert sentinel["type"] == "stac"
