"""Async SQLAlchemy engine, session factory, and init_db."""

import json
import logging
import os
import secrets
from pathlib import Path
from typing import AsyncGenerator

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
