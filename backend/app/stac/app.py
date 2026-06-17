"""
Spec-compliant STAC API, served as its own process (default port 8080).

This is the catalogue's source of truth: a stac-fastapi-pgstac application backed
by the PgSTAC schema in the shared Postgres database. The main Horus API
(`app.main`) does NOT mount it — instead `app.apis.stac_api` proxies `/api/stac/*`
to this service so the browser keeps a single origin while every STAC request is
answered by the real, conformant engine.

We re-export the library's pre-built `app` rather than assembling a `StacApi`
ourselves: it stays version-locked to the installed stac-fastapi-pgstac and picks
up the full extension set (search/sort/fields/filter/pagination). Everything is
configured by environment variables read at import time:

    POSTGRES_USER / POSTGRES_PASS / POSTGRES_DBNAME
    POSTGRES_HOST_READER / POSTGRES_HOST_WRITER / POSTGRES_PORT   (PgSTAC pool)
    STAC_FASTAPI_TITLE / STAC_FASTAPI_DESCRIPTION                 (landing page)

Run it with:  uvicorn app.stac.app:app --host 0.0.0.0 --port 8080
"""
from stac_fastapi.pgstac.app import app

__all__ = ["app"]
