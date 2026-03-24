"""Async SQLAlchemy engine, session factory, and init_db."""

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings
from .models import Base, ApiKey, Project, AgentConfig

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


# Re-export helper functions for convenience
from ..utils import create_agent_context_file, get_context_file_for_agent


async def _create_default_agent_configs(session: AsyncSession, project: Project) -> None:
    """Create default agent configs based on AW_INIT_AGENTS setting."""
    from sqlalchemy import select
    from .models import AgentConfig as AgentConfigModel
    from ..utils import short_id, create_agent_context_file
    
    init_agents_str = settings.aw_init_agents.strip()
    if not init_agents_str:
        return
    
    init_agents = [a.strip().lower() for a in init_agents_str.split(",") if a.strip()]
    
    for agent_name in init_agents:
        # Check if config already exists
        result = await session.execute(
            select(AgentConfigModel).where(
                AgentConfigModel.project_id == project.id,
                AgentConfigModel.agent_name == agent_name,
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"Agent config for '{agent_name}' already exists, skipping...")
            continue
        
        # Create context file for the agent
        context_file = create_agent_context_file(
            agent_name=agent_name,
            role="principal",
            project_name=project.name,
        )
        
        # Create agent config as principal
        config = AgentConfigModel(
            id=f"acfg-{short_id()}",
            project_id=project.id,
            agent_name=agent_name,
            role="principal",
            yolo_enabled=False,
            context_file=context_file,
        )
        session.add(config)
        print(f"Created principal config for '{agent_name}' with context file '{context_file}'")
    
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

    # Bootstrap: insert project + API key from env if no keys exist
    if settings.aw_bootstrap_api_key:
        async with async_session_factory() as session:
            from sqlalchemy import select, func

            count = await session.scalar(select(func.count()).select_from(ApiKey))
            if count == 0:
                project = Project(
                    id=settings.aw_bootstrap_project_id,
                    name=settings.aw_bootstrap_project_name,
                    settings={
                        "allow_add_agents": settings.aw_allow_add_agents,
                    },
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
                
                # Create default agent configs
                await _create_default_agent_configs(session, project)
                print(f"Hub initialized with project '{project.name}'")
                print(f"Default agents: {settings.aw_init_agents}")
                print(f"Allow adding agents later: {settings.aw_allow_add_agents}")
