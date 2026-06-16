import json

from sqlalchemy import String, cast, func, select


async def geometry_as_geojson(db, geometry_column, row_id, id_column):
    stmt = select(cast(func.ST_AsGeoJSON(geometry_column), String)).where(id_column == row_id)
    raw = (await db.execute(stmt)).scalar_one_or_none()
    return json.loads(raw) if raw else None