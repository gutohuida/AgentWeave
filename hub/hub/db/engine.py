"""Async SQLAlchemy engine, session factory, and init_db."""

import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings
from .models import Base, ApiKey, Project, AIJob, JobRun, ProjectInstructions

logger = logging.getLogger(__name__)

# The placeholder value from .env.example that triggers auto-generation
_PLACEHOLDER_API_KEY = "aw_live_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

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
        from functools import partial

        from alembic import command
        from alembic.config import Config

        # hub/hub/db/engine.py → hub/hub/db/ → hub/hub/ → hub/
        # The alembic.ini lives at the hub/ root.
        alembic_cfg_path = Path(__file__).parent.parent.parent / "alembic.ini"
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
        from sqlalchemy import select, func

        # Check if any keys exist
        count = await session.scalar(select(func.count()).select_from(ApiKey))
        if count > 0:
            return

        # No keys exist - need to bootstrap
        # Determine API key: use env value unless it's empty or placeholder
        api_key = settings.aw_bootstrap_api_key
        auto_generated = False

        if not api_key or api_key == _PLACEHOLDER_API_KEY:
            api_key = _generate_api_key()
            auto_generated = True
            logger.info("Bootstrap API key auto-generated")

        # Create project
        project = Project(
            id=settings.aw_bootstrap_project_id,
            name=settings.aw_bootstrap_project_name,
        )
        session.add(project)

        # Create API key
        key = ApiKey(
            id=api_key,
            project_id=settings.aw_bootstrap_project_id,
            label="bootstrap" if not auto_generated else "auto-generated",
            revoked=False,
        )
        session.add(key)
        await session.commit()

        if auto_generated:
            logger.info("Bootstrap API key stored in database")
