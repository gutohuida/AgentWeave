"""Async SQLAlchemy engine, session factory, and init_db."""

import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings
from .models import Base, ApiKey, Project, AIJob, JobRun

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


async def init_db() -> None:
    """Create tables and bootstrap API key if none exist."""
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
        dir_part = os.path.dirname(db_path)
        if dir_part:
            os.makedirs(dir_part, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
