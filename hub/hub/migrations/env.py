"""Alembic migration environment — async SQLAlchemy."""

import asyncio
from logging.config import fileConfig

import sqlalchemy as sa
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


def _build_an_empty_database_from_the_models(connection) -> None:
    """Give an empty database migrated to head the schema `init_db` would have built (F329).

    The chain cannot build a database on its own. No migration creates `projects` — `create_all`
    always has — and so every migration that recreates a table guards on `projects` and returns
    early without it, trusting that "`create_all` builds the rest from the model". That holds only
    when `create_all` runs *first*, which is `init_db`'s order. The CLI's native start and the
    Docker image both run `alembic upgrade head` alone on a fresh database and let the server's
    `create_all` follow; by then the chain has already created `conversations` (`0017`) in its
    oldest shape while skipping every change to it, `create_all` leaves an existing table alone,
    and the database is stamped head without `conversations.title`. Every conversation the operator
    then starts fails on the INSERT. `conversations` is the loudest of 28 schema objects that
    differ from `init_db`'s build — missing columns, indexes (`uq_projects_path_key` among them)
    and foreign keys.

    Here rather than in either caller, so every door — the CLI, the Docker image, a hand-typed
    `alembic upgrade head` — gets the same database `init_db` builds. Only for head: a database
    being built up to an older revision is a test constructing history, and giving it today's
    tables would stamp a schema that revision never had. Only for an empty database: one that
    already has tables is being upgraded, which is the chain's job. And never for a command
    with no destination (`alembic current`), which must not change what it reports on.
    """
    try:
        destination = context.get_revision_argument()
    except KeyError:
        # `current`, `check` and the other read-only commands pass no destination at all.
        return
    if destination != context.get_head_revision():
        return
    with connection.begin():
        if sa.inspect(connection).get_table_names():
            return
        target_metadata.create_all(connection)


def do_run_migrations(connection):
    _build_an_empty_database_from_the_models(connection)
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
