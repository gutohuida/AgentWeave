"""Alembic migration environment — async SQLAlchemy."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from hub.config import settings
from hub.db.models import Base

config = context.config
if config.config_file_name is not None:
    # `disable_existing_loggers=False`, and it is load-bearing (F151).
    #
    # `fileConfig` defaults to True, which sets `disabled = True` on **every logger that already
    # exists** and is not named in `alembic.ini`. This file runs from `init_db()`, the first line
    # of the Hub's `lifespan()` — by which point `uvicorn.error`, `uvicorn.access` and every
    # `hub.*` module logger have all been created at import time. With the default, migrating on
    # startup silenced the whole process for its entire life: no "Application startup complete.",
    # no access log, no `_ui_staleness_warning()` (which is emitted a few lines later in
    # `lifespan()` and had therefore never once been seen), no run-failure traceback. The only
    # lines that survived were alembic's own, because `[loggers]` here names them.
    #
    # The Hub configures no logging of its own, so nothing is being overridden by keeping the
    # existing loggers: this restores uvicorn's, which is what an operator reads.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # F292 investigation, 2026-09-06: this engine used to have no `connect_args` at all, so on
    # SQLite it ran with the driver's default 5s busy timeout while `hub/hub/db/engine.py`'s
    # engine (via `hub/tests/conftest.py`'s pragma listener) waits 30s -- six times shorter
    # patience for exactly the writer this repository already knows can collide with a schema
    # reset (F292's own control run). `timeout` here is the sqlite3/aiosqlite connect-time
    # argument that sets `PRAGMA busy_timeout`, the same mechanism the pragma listener uses.
    connectable = create_async_engine(
        settings.database_url,
        connect_args=(
            {"check_same_thread": False, "timeout": 30.0}
            if "sqlite" in settings.database_url
            else {}
        ),
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        # Was unconditional and placed after the `async with` block, so a migration failure
        # propagated straight past it -- this engine, and its one checked-out-then-rolled-back
        # connection, were never disposed and lived until Python's garbage collector reclaimed
        # them. `_run_alembic_upgrade` (hub/hub/db/engine.py) swallows the exception this raises,
        # so nothing surfaced except the leak.
        await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
