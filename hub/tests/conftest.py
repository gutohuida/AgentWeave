"""Shared test fixtures for AgentWeave Hub."""

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Use in-memory SQLite for tests
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("AW_BOOTSTRAP_API_KEY", "aw_live_testkey_abcdefgh")
os.environ.setdefault("AW_BOOTSTRAP_PROJECT_ID", "proj-test")
os.environ.setdefault("AW_BOOTSTRAP_PROJECT_NAME", "Test Project")

from hub.db.engine import init_db  # noqa: E402
from hub.main import create_app  # noqa: E402 — env must be set first


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


@pytest.fixture(autouse=True)
def _no_real_mcp_probe(monkeypatch):
    """Every agent trigger calls launchability.resolve_access_path, which (for
    claude/claude_proxy/native/codex) shells out to ``<cli> mcp list`` to check whether
    the agentweave MCP server is actually registered. The suite must not depend on a real
    CLI being installed/authenticated on the machine running it — default the probe to
    "not registered" (deterministic, no subprocess) so every test gets the "cli" access
    path unless it explicitly overrides this fixture's patch.
    """
    import hub.launchability as launchability

    monkeypatch.setattr(launchability, "probe_mcp_registered", lambda cli: False)
