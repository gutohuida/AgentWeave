"""Async SQLAlchemy engine, session factory, and init_db."""

import json
import logging
import os
import secrets
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.exc import DisconnectionError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings

# AIJob, JobRun and ProjectInstructions are imported for their side effect: importing
# a model registers its mapper on Base.metadata, which is what `create_all` (below)
# iterates over. Dropping them as "unused" silently stops those tables being created.
from .models import (  # noqa: F401
    AIJob,
    ApiKey,
    Base,
    Charter,
    JobRun,
    OperatorCredential,
    Project,
    ProjectInstructions,
    Runner,
)

logger = logging.getLogger(__name__)

# The placeholder value from .env.example that triggers auto-generation
_PLACEHOLDER_API_KEY = "aw_live_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

# ---------------------------------------------------------------------------
# The dead-worker guard (finding F295).
#
# aiosqlite carries out every statement for a connection on one dedicated worker
# thread. If that thread ends -- which is what happens when the event loop a statement
# was issued on is closed underneath it (aiosqlite 0.22.1, `core.py:47-75`: the worker
# fails to report a result on the closed loop, fails again reporting *that* the same
# way, and its `while True` ends) -- the connection is not slow and is not merely in an
# error state. It accepts work, never answers, and cannot be closed, because closing is
# itself work for the thread that ended. Anything that waits on it waits without bound,
# and cancelling the wait does not return either.
#
# Two listeners, measured against aiosqlite 0.22.1 and SQLAlchemy 2.0.50:
#
#   - `checkout` DETECTS ONLY. It raises `DisconnectionError`, which makes SQLAlchemy
#     invalidate the record and retry the checkout on a fresh connection.
#   - `close` (and `close_detached`) NEUTRALISE, so that the invalidation above -- and
#     every other close -- returns instead of waiting on the ended thread.
#
# Both reach two private aiosqlite attributes on the inner `aiosqlite.Connection`:
# `_connection`, the `sqlite3` handle (assigned `core.py:85`), and `_thread`, the worker
# (`core.py:90`). They are read and set, never reimplemented -- these are the same two
# attributes aiosqlite's own code branches on:
#
#   - `Connection.close()` opens with `if self._connection is None: return`
#     (`core.py:202-203`), so a connection whose handle has been cleared closes
#     instantly and without touching its thread;
#   - `Connection._execute()` raises `ValueError("Connection closed")` when `_running`
#     is false (`core.py:152-153`), so anything still holding a reference gets a loud
#     failure rather than a silent unbounded wait.
#
# Every access is a `getattr` with a `None` default and every listener no-ops when the
# shape is absent, so a driver that is not aiosqlite is untouched and a rename upstream
# disables the guard visibly rather than breaking a healthy checkout.


def _dead_worker_connection(dbapi_connection):  # noqa: ANN001, ANN202
    """Return the inner aiosqlite connection if its worker thread has ended, else None."""
    inner = getattr(dbapi_connection, "_connection", None)
    thread = getattr(inner, "_thread", None)
    if inner is None or thread is None:
        return None
    if thread.is_alive():
        return None
    return inner


def _neutralise_dead_worker(dbapi_connection) -> bool:  # noqa: ANN001
    """Put a dead-worker connection beyond use so closing it cannot wait on the thread.

    Sets `_running = False` and `_connection = None` on the inner `aiosqlite.Connection`
    -- not on the SQLAlchemy adapter, whose `__slots__` carry neither. Returns whether it
    acted.
    """
    inner = _dead_worker_connection(dbapi_connection)
    if inner is None:
        return False
    inner._running = False
    inner._connection = None
    return True


@event.listens_for(engine.sync_engine, "checkout")
def _refuse_dead_worker_connection(
    dbapi_connection, connection_record, connection_proxy
):  # noqa: ANN001, ANN201
    """Never hand out a pooled connection whose aiosqlite worker thread has ended.

    Detection only, deliberately. An earlier draft neutralised the connection here,
    inline, before raising -- correct as far as it went and sited wrongly: the checkout
    is one of several paths that close such a connection, and a neutralisation here
    leaves the others unprotected. The neutralisation lives on the `close` event below.
    """
    if _dead_worker_connection(dbapi_connection) is None:
        return
    # WARNING, not DEBUG: this is the only place the condition is ever observable, and a
    # silently transparent recovery would hide a live defect somewhere else -- a worker
    # only ends because an event loop was closed under a connection still in the pool.
    logger.warning(
        "Discarding a pooled database connection whose driver worker thread had ended; "
        "it could no longer complete work. Opening a fresh connection instead. "
        "The statement is unaffected, but an event loop was closed under a live "
        "connection somewhere (see finding F295)."
    )
    raise DisconnectionError("aiosqlite worker thread has ended for this connection")


@event.listens_for(engine.sync_engine, "close")
def _neutralise_dead_worker_on_close(dbapi_connection, connection_record):  # noqa: ANN001, ANN201
    """Neutralise a dead-worker connection before the pool closes it.

    THIS BELONGS ON `close`, NOT INLINE IN THE CHECKOUT LISTENER ABOVE. Do not move it
    back. SQLAlchemy dispatches `close` from `_ConnectionRecord.__close()`
    (2.0.50, `pool/base.py:878-880`), which is reached by every path that closes a
    pooled connection: the checkout listener's own `invalidate()`, `QueuePool.dispose()`
    -- which `engine.dispose()` calls at instance shutdown -- a checkin-time close, and
    the abandon at the end of `_ConnectionFairy._checkout` when the retries are
    exhausted. A checkout-only guard covers exactly the first of those, so
    `engine.dispose()` would still hang on a dead connection that was sitting idle in the
    pool and had never been handed out. Measured: bare `await engine.dispose()` in that
    state never returns; with this listener it returns in 0.00s.
    """
    _neutralise_dead_worker(dbapi_connection)


@event.listens_for(engine.sync_engine, "close_detached")
def _neutralise_dead_worker_on_close_detached(dbapi_connection):  # noqa: ANN001, ANN201
    """The same neutralisation for the one close path that does not dispatch `close`.

    DELIBERATELY UNREACHABLE IN THE HUB TODAY, and kept anyway. `_finalize_fairy` closes
    a *detached* connection through `pool/base.py:999-1000`, which dispatches
    `close_detached` rather than `close`, so the listener above never sees it. Nothing in
    `hub/` calls `.detach()`, and a probe's `close_detached` counter fired zero times
    across both checkout invalidation and dispose -- so this is not evidence that the
    state occurs, and it should not be cited as such. It is here because putting a
    dead-worker connection beyond use has to cover every path that closes one, and this
    is the fifth path.
    """
    _neutralise_dead_worker(dbapi_connection)


async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an async database session."""
    async with async_session_factory() as session:
        yield session


def _generate_api_key() -> str:
    """Generate a secure API key: aw_live_<32 hex chars>."""
    return f"aw_live_{secrets.token_hex(16)}"


async def _run_alembic_upgrade() -> None:
    """Run `alembic upgrade head` programmatically (PR 7 / H5).

    Closes H5: a deployment that only invokes `init_db` (e.g. for tests or
    for a one-shot setup) used to miss schema changes that lived in
    Alembic migrations. We now run `alembic upgrade head` after
    `create_all`, wrapped in try/except so dev mode (in-memory SQLite,
    missing alembic.ini, schema drift, etc.) doesn't crash startup.

    - Skipped for in-memory SQLite — alembic creates its own async engine
      in `env.py`, and an in-memory SQLite database is per-connection, so
      alembic would see an empty database and fail with `no such table`.
    - Wrapped in try/except — any failure is logged at WARNING level and
      swallowed, so `init_db` always completes the create_all + bootstrap
      path. A deployment can still re-run `alembic upgrade head` manually
      to recover.
    - Run in a worker thread — `command.upgrade` is synchronous but
      `env.py` uses `asyncio.run` internally to drive the async engine.
      Calling it directly from within a running event loop (e.g. an async
      test) raises "asyncio.run() cannot be called from a running event
      loop", so we delegate to a thread.
    """
    if ":memory:" in settings.database_url:
        logger.debug("Skipping alembic upgrade for in-memory database")
        return

    try:
        import asyncio

        from alembic import command
        from alembic.config import Config

        # hub/hub/db/engine.py → hub/hub/db/ → hub/hub/
        # alembic.ini is packaged inside the `hub` package (task 3.12) so it ships
        # with a plain `pip install agentweave-hub`, not just a source checkout.
        alembic_cfg_path = Path(__file__).parent.parent / "alembic.ini"
        if not alembic_cfg_path.exists():
            logger.warning("alembic.ini not found at %s; skipping migrations", alembic_cfg_path)
            return

        cfg = Config(str(alembic_cfg_path))
        cfg.set_main_option("sqlalchemy.url", settings.database_url)

        # Run alembic in a thread so its internal `asyncio.run` call
        # doesn't conflict with a parent event loop (e.g. async tests,
        # FastAPI lifespan).
        def _do_upgrade() -> None:
            command.upgrade(cfg, "head")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _do_upgrade)
        logger.info("Alembic migrations applied to %s", settings.database_url)
    except Exception as exc:
        logger.warning("Alembic upgrade failed (continuing startup): %s", exc)


async def _seed_default_runners(session: AsyncSession) -> None:
    """Seed one default runner per supported CLI for every project that has none.

    Runs on every `init_db()` call, not just first boot — idempotent per project (a
    project with any existing runner rows is left untouched). See
    openspec/changes/runner-agent-charter-separation/specs/runner-registry/spec.md's
    "Built-in runners are seeded on first use" requirement.
    """
    from sqlalchemy import func, select

    from ..utils import short_id
    from .models import RUNNER_CLIS

    projects = (await session.execute(select(Project.id))).scalars().all()
    for project_id in projects:
        count = await session.scalar(
            select(func.count()).select_from(Runner).where(Runner.project_id == project_id)
        )
        if count:
            continue
        for cli in RUNNER_CLIS:
            session.add(
                Runner(
                    id=f"runner-{short_id()}",
                    project_id=project_id,
                    name=f"{cli.capitalize()} (default)",
                    cli=cli,
                )
            )
    await session.commit()


async def _seed_default_charters(session: AsyncSession) -> None:
    """Seed bundled starter charters for projects that have not been seeded."""
    from sqlalchemy import func, select

    from ..utils import short_id

    charters_dir = Path(__file__).parent.parent / "data" / "charters"
    charter_manifest = json.loads((charters_dir / "charters.json").read_text(encoding="utf-8"))
    projects = (await session.execute(select(Project))).scalars().all()
    for project in projects:
        if project.charters_seeded:
            continue
        count = await session.scalar(
            select(func.count()).select_from(Charter).where(Charter.project_id == project.id)
        )
        if count == 0:
            for charter_key, metadata in charter_manifest["charters"].items():
                session.add(
                    Charter(
                        id=f"charter-{short_id()}",
                        project_id=project.id,
                        name=metadata["name"],
                        content=(charters_dir / f"{charter_key}.md").read_text(encoding="utf-8"),
                    )
                )
        project.charters_seeded = True
    await session.commit()


async def _seed_operator_credential(session: AsyncSession) -> None:
    """Promote the legacy bootstrap secret onto the instance operator plane.

    Alembic performs the durable upgrade for file databases. This idempotent path
    also covers fresh databases and in-memory development databases where Alembic is
    deliberately skipped.
    """
    from sqlalchemy import func, select

    if await session.scalar(select(func.count()).select_from(OperatorCredential)):
        return

    candidate = None
    if settings.aw_bootstrap_api_key:
        candidate = await session.get(ApiKey, settings.aw_bootstrap_api_key)
    if candidate is None:
        candidate = await session.scalar(
            select(ApiKey)
            .where(ApiKey.label.in_(("bootstrap", "auto-generated")))
            .order_by(ApiKey.created_at, ApiKey.id)
        )
    if candidate is None:
        result = await session.execute(select(ApiKey).order_by(ApiKey.created_at, ApiKey.id))
        keys = result.scalars().all()
        if len(keys) == 1:
            candidate = keys[0]

    if candidate is not None:
        session.add(
            OperatorCredential(
                id=candidate.id,
                label=candidate.label,
                revoked=candidate.revoked,
                created_at=candidate.created_at,
            )
        )
        await session.commit()
        return

    # A genuinely fresh install has no legacy ApiKey to promote — mint the instance
    # operator credential directly so the local app can authenticate before any
    # project exists.
    api_key = settings.aw_bootstrap_api_key
    if not api_key or api_key == _PLACEHOLDER_API_KEY:
        api_key = _generate_api_key()
        logger.info("Bootstrap API key auto-generated")
    session.add(OperatorCredential(id=api_key, label="bootstrap", revoked=False))
    await session.commit()


async def init_db() -> None:
    """Create tables and bootstrap API key if none exist."""
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
        dir_part = os.path.dirname(db_path)
        if dir_part:
            os.makedirs(dir_part, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await _run_alembic_upgrade()

    async with async_session_factory() as session:
        # Startup creates no project. A Hub with nothing in it is the correct empty state:
        # the operator opens a directory and that registers the project, which is the only
        # path that can bind a project id to a working directory. A seeded "Default Project"
        # bound to nothing was an artefact of the single-project era — it survived the move
        # to a project collection as an env-gated leftover (AW_BOOTSTRAP_PROJECT_ID), which
        # was enough for an old .env carried forward to keep conjuring one. The gate, the
        # settings behind it and the project it made are all gone; tests that want a project
        # create one (see hub/tests/conftest.py).
        await _seed_operator_credential(session)
        await _seed_default_runners(session)
        await _seed_default_charters(session)
