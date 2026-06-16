import math


def tile_to_bbox(z: int, x: int, y: int) -> list[float]:
    """Convert XYZ slippy-map tile to WGS84 bounding box [minx, miny, maxx, maxy]."""
    n = 2 ** z
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0
    lat_max = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat_min = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return [lon_min, lat_min, lon_max, lat_max]


def coarse_tile(z: int, x: int, y: int, base_z: int = 13) -> tuple[int, int, int]:
    """
    Project a tile up to a coarser zoom so neighbouring high-zoom tiles share a
    single STAC scene lookup (one DB/remote hit per ~region instead of per tile).

    base_z must stay HIGH enough that one Sentinel-2 scene (~110 km MGRS cell)
    actually covers the coarse area, otherwise the chosen scene only overlaps part
    of it and the uncovered child tiles fall outside its COG -> 204 holes. At
    base_z=13 (~9.5 km) every browsing zoom (z<=13) is looked up per-tile, so the
    scene picked for a tile almost always covers that whole tile. Coarsening only
    kicks in above z13 where tiles are tiny and a z13 cell is safely inside a scene.
    """
    if z <= base_z:
        return z, x, y
    shift = z - base_z
    return base_z, x >> shift, y >> shift
