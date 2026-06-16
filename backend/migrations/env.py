"""Alembic environment for the Horus Maps application schema.

Single source of truth for the `public.*` app tables (sessions, aoi, measurements,
temporal_comparisons, tasks, map_layers, collections, items). Run:

    alembic upgrade head                       # apply migrations (boot/deploy)
    alembic revision --autogenerate -m "..."   # generate the next migration

The PgSTAC catalog (`pgstac.*`), PostGIS `spatial_ref_sys`, and any tiger/topology
schema are owned by pypgstac / PostGIS, NOT by this app — `_include_object` keeps
them out of every autogenerate diff so Alembic never tries to drop them.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.configs.config import PostgresConfig
from app.databases.base import Base

# Import every model so it registers on Base.metadata before autogenerate runs.
import app.models  # noqa: F401

# GeoAlchemy2 ships Alembic helpers that (a) render Geometry columns correctly and
# (b) skip the PostGIS-managed spatial indexes + spatial_ref_sys during autogenerate.
try:
    from geoalchemy2 import alembic_helpers
except Exception:  # pragma: no cover - older GeoAlchemy2
    alembic_helpers = None

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url() -> str:
    # Alembic runs synchronously; strip the async driver so SQLAlchemy uses psycopg2.
    return PostgresConfig().CONNECTION_URL.replace("+asyncpg", "")


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Only manage the app's own public-schema objects."""
    schema = getattr(obj, "schema", None)
    if schema not in (None, "public"):
        return False  # pgstac / tiger / topology — owned elsewhere
    if type_ == "table" and name == "spatial_ref_sys":
        return False  # PostGIS system table
    if alembic_helpers is not None:
        return alembic_helpers.include_object(obj, name, type_, reflected, compare_to)
    return True


_render_item = getattr(alembic_helpers, "render_item", None)
_writer = getattr(alembic_helpers, "writer", None)


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=_include_object,
        render_item=_render_item,
        process_revision_directives=_writer,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _sync_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=_include_object,
            render_item=_render_item,
            process_revision_directives=_writer,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
