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

from hub.db.engine import engine, init_db  # noqa: E402
from hub.db.models import Base  # noqa: E402
from hub.main import create_app  # noqa: E402 — env must be set first


@pytest_asyncio.fixture
async def app():
    application = create_app()
    # ASGITransport does not trigger the FastAPI lifespan, so we run init_db
    # (create_all + bootstrap key) explicitly before each test.
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
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


@pytest.fixture
def bind_runner(app, auth_headers):
    """Returns an async helper: `await bind_runner(agent_name, cli="claude")`.

    Creates a Runner and binds it to *agent_name*. Since runner-agent-charter-separation
    phase 1.3, `trigger_agent_directly` refuses to spawn an agent with no bound Runner —
    the old session/sync `agents.<name>.runner` string no longer selects which CLI/model
    to launch, only `Agent.runner_id` does. Any test that expects a real spawn (or to
    reach spawn-adjacent pre-flight checks) must bind one first, after the agent row
    exists (self-registered or session-synced).
    """

    async def _bind(agent_name, cli="claude", model=None):
        payload = {"name": f"{agent_name}-runner", "cli": cli}
        if model:
            payload["model"] = model
        created = await app.post("/api/v1/runners", json=payload, headers=auth_headers)
        assert created.status_code == 201, created.text
        runner_id = created.json()["id"]
        bound = await app.patch(
            f"/api/v1/agents/{agent_name}",
            json={"runner_id": runner_id},
            headers=auth_headers,
        )
        assert bound.status_code == 200, bound.text
        return runner_id

    return _bind


@pytest.fixture(autouse=True)
def _no_real_worktree_provision(monkeypatch):
    """Every agent trigger calls worktrees.resolve_agent_workspace, which (for a
    writing agent) shells out to real `git worktree` commands against `Path.cwd()` —
    during this suite that's wherever `pytest` was invoked from, i.e. a real checkout,
    not a disposable fixture. Default to "no isolation" (return repo_root unchanged) so
    the suite never mutates real git state; `test_worktrees.py` and the dedicated
    integration tests in `test_agent_trigger.py`/`test_session_sync.py` restore the real
    function explicitly (via `monkeypatch.setattr`) against a `tmp_path` git repo instead.
    """
    import hub.worktrees as worktrees

    monkeypatch.setattr(
        worktrees, "resolve_agent_workspace", lambda repo_root, agent, config: repo_root
    )
