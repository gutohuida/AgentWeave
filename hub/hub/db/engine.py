"""Async SQLAlchemy engine, session factory, and init_db."""

import os
import secrets
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings
from .models import Base, ApiKey, Project

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False}
    if "sqlite" in settings.database_url
    else {},
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an async database session."""
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """Create tables and bootstrap API key if none exist."""
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
        dir_part = os.path.dirname(db_path)
        if dir_part:
            os.makedirs(dir_part, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Bootstrap: insert project + API key from env if no keys exist
    if settings.aw_bootstrap_api_key:
        async with async_session_factory() as session:
            from sqlalchemy import select, func

            count = await session.scalar(select(func.count()).select_from(ApiKey))
            if count == 0:
                project = Project(
                    id=settings.aw_bootstrap_project_id,
                    name=settings.aw_bootstrap_project_name,
                )
                session.add(project)

                key = ApiKey(
                    id=settings.aw_bootstrap_api_key,
                    project_id=settings.aw_bootstrap_project_id,
                    label="bootstrap",
                    revoked=False,
                )
                session.add(key)
                await session.commit()
