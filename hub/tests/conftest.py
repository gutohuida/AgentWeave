"""Shared test fixtures for AgentWeave Hub."""

import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Use in-memory SQLite for tests
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("AW_BOOTSTRAP_API_KEY", "aw_live_testkey_abcdefgh")
os.environ.setdefault("AW_BOOTSTRAP_PROJECT_ID", "proj-test")
os.environ.setdefault("AW_BOOTSTRAP_PROJECT_NAME", "Test Project")

from hub.main import create_app  # noqa: E402 — env must be set first
from hub.db.engine import init_db  # noqa: E402


@pytest_asyncio.fixture
async def app():
    application = create_app()
    # ASGITransport does not trigger the FastAPI lifespan, so we run init_db
    # (create_all + bootstrap key) explicitly before each test.
    await init_db()
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer aw_live_testkey_abcdefgh"}
