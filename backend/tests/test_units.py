"""Offline unit tests for service-layer pure logic and API contracts."""
import pytest

from app.services.map_service import MapService, _default_layers
from app.services.measurement_service import _convert
from app.models.map_layer import MapLayer


# --------------------------------------------------------------------------- #
#  Measurement unit conversion
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "value_si,unit,mtype,expected",
    [
        (1_000_000.0, "km2", "area", 1.0),
        (10_000.0, "ha", "area", 1.0),
        (5.0, "m2", "area", 5.0),
        (1000.0, "km", "perimeter", 1.0),
        (250.0, "m", "distance", 250.0),
        (42.0, "unknown", "area", 42.0),   # unknown unit → factor 1.0
    ],
)
def test_convert(value_si, unit, mtype, expected):
    assert _convert(value_si, unit, mtype) == pytest.approx(expected)


# --------------------------------------------------------------------------- #
#  /api/layers contract — must expose is_active / display_order (frontend reads
#  these to decide visibility and sort order).
# --------------------------------------------------------------------------- #

def test_layer_to_api_contract_from_dict():
    layer = _default_layers("http://titiler:8000")[0]
    api = MapService.layer_to_api(layer)
    assert {"id", "name", "type", "url", "options", "is_active", "display_order"} <= api.keys()
    assert "visible" not in api and "order" not in api


def test_layer_to_api_contract_from_model():
    model = MapLayer(
        id="x", name="X", type="stac", url="http://t/cog",
        options={"attribution": "© test"}, is_active=True, display_order=3,
    )
    api = MapService.layer_to_api(model)
    assert api["is_active"] is True
    assert api["display_order"] == 3
    assert api["attribution"] == "© test"


def test_default_sentinel_true_color_layer_has_no_rescale():
    # The true-color layer uses the pre-scaled `visual` asset → no rescale option.
    tc = next(l for l in _default_layers("http://t") if l["id"] == "sentinel-2-true-color")
    assert tc["options"]["asset"] == "visual"
    assert "rescale" not in tc["options"]
