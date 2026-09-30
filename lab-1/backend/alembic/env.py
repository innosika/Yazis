"""Alembic migration environment.

Migrations run through the *async* engine rather than a synchronous one. The
application stack is asyncpg-only, and adding psycopg purely so Alembic can have a sync
driver would mean shipping a second PostgreSQL driver whose behaviour (type adaption,
parameter style) differs subtly from the one actually used at runtime. Alembic supports
this directly via ``connection.run_sync``.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from irs.config import settings

# Importing the package populates Base.metadata with every model before autogenerate
# compares it against the database.
from irs.db.models import Base  # noqa: F401  # isort: skip

config = context.config
config.set_main_option("sqlalchemy.url", str(settings.postgres_dsn))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to) -> bool:  # type: ignore[no-untyped-def]
    """Keep autogenerate from trying to manage objects owned by extensions."""
    if type_ == "table" and name in {"spatial_ref_sys"}:
        return False
    return True


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
        # Render pgvector's VECTOR type with its import, so generated migrations are
        # valid Python without hand-editing.
        user_module_prefix="pgvector.sqlalchemy.",
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting — used for review, not for deployment."""
    context.configure(
        url=str(settings.postgres_dsn),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
        user_module_prefix="pgvector.sqlalchemy.",
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
