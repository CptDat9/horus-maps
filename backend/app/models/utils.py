import datetime
import json
from geoalchemy2 import Geometry
from geoalchemy2.functions import GenericFunction
from app.utils.logger_utils import get_logger

logger = get_logger("ModelUtils")


class NotFound(Exception):
    """Custom exception to indicate model not found in database"""

    def __init__(self, message: str = ""):
        logger.debug(message)
        super().__init__(message)


class InvalidGeoJson(Exception):
    """Custom exception to notify caller they have supplied Invalid GeoJson"""

    def __init__(self, message: str = ""):
        logger.debug(message)
        super().__init__(message)


class InvalidData(Exception):
    """Custom exception to notify caller they have supplied Invalid data to a model"""

    def __init__(self, message: str = ""):
        logger.debug(message)
        super().__init__(message)


class ST_SetSRID(GenericFunction):
    """Exposes PostGIS ST_SetSRID function"""

    inherit_cache = False
    name = "ST_SetSRID"
    type = Geometry


class ST_GeomFromGeoJSON(GenericFunction):
    """Exposes PostGIS ST_GeomFromGeoJSON function"""

    inherit_cache = False
    name = "ST_GeomFromGeoJSON"
    type = Geometry


class ST_AsGeoJSON(GenericFunction):
    """Exposes PostGIS ST_AsGeoJSON function"""

    inherit_cache = False
    name = "ST_AsGeoJSON"
    type = Geometry


class ST_Centroid(GenericFunction):
    """Exposes PostGIS ST_Centroid function"""

    inherit_cache = False
    name = "ST_Centroid"
    type = Geometry


class ST_Transform(GenericFunction):
    """Exposes PostGIS ST_Transform function"""

    inherit_cache = False
    name = "ST_Transform"
    type = Geometry


class ST_Area(GenericFunction):
    """Exposes PostGIS ST_Area function"""

    inherit_cache = False
    name = "ST_Area"
    type = None


class ST_Perimeter(GenericFunction):
    """Exposes PostGIS ST_Perimeter function"""

    inherit_cache = False
    name = "ST_Perimeter"
    type = None


class ST_GeogFromWKB(GenericFunction):
    """Exposes PostGIS ST_GeogFromWKB function"""

    inherit_cache = False
    name = "ST_GeogFromWKB"
    type = None


class ST_Buffer(GenericFunction):
    """Exposes PostGIS ST_Buffer function"""

    inherit_cache = False
    name = "ST_Buffer"
    type = Geometry


class ST_Intersects(GenericFunction):
    """Exposes PostGIS ST_Intersects function"""

    inherit_cache = False
    name = "ST_Intersects"
    type = Geometry


class ST_MakeEnvelope(GenericFunction):
    """Exposes PostGIS ST_MakeEnvelope function"""

    inherit_cache = False
    name = "ST_MakeEnvelope"
    type = Geometry


class ST_X(GenericFunction):
    """Exposes PostGIS ST_X function"""

    inherit_cache = False
    name = "ST_X"
    type = Geometry


class ST_Y(GenericFunction):
    """Exposes PostGIS ST_Y function"""

    inherit_cache = False
    name = "ST_Y"
    type = Geometry


class DateTimeEncoder(json.JSONEncoder):
    """
    Custom JSON Encoder that handles Python date/times
    HT to stackoverflow http://stackoverflow.com/a/12126976/620362
    """

    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, datetime.date):
            return obj.isoformat()
        elif isinstance(obj, datetime.timedelta):
            return (datetime.datetime.min + obj).time().isoformat()
        else:
            return super(DateTimeEncoder, self).default(obj)