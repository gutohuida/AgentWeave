"""Shared test fixtures for AgentWeave Hub."""

import os
import warnings

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Use in-memory SQLite for tests.
#
# These are assignments, not `setdefault`. An inherited DATABASE_URL used to win here,
# and the `app` fixture below drops every table before each test — so running this suite
# from any shell that had one exported destroyed that database and still exited green.
# That is not a hypothetical shell: `_hub_native_start` (src/agentweave/cli.py) exports
# DATABASE_URL into the Hub's own environment, spawned agents inherited it, and this
# repository's instructions tell an agent to run `pytest hub/tests/`. So the environment
# most likely to run the suite was the one pointed at live operator data.
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_inherited_database_url = os.environ.get("DATABASE_URL")
if _inherited_database_url and _inherited_database_url != TEST_DATABASE_URL:
    warnings.warn(
        f"Ignoring inherited DATABASE_URL={_inherited_database_url!r}. The Hub suite "
        f"always runs on {TEST_DATABASE_URL} because its fixtures drop every table.",
        stacklevel=1,
    )

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["AW_BOOTSTRAP_API_KEY"] = TEST_API_KEY = "aw_live_testkey_abcdefgh"

# The project nearly every test addresses. It used to arrive as a side effect of
# `init_db`, which created a project when AW_BOOTSTRAP_PROJECT_ID was set — the same
# mechanism that put a "Default Project" in front of operators who had an older .env.
# Startup now creates no project at all, so the suite makes its own.
TEST_PROJECT_ID = "proj-test"
TEST_PROJECT_NAME = "Test Project"

from hub.db.engine import async_session_factory, engine, init_db  # noqa: E402
from hub.db.models import ApiKey, Base, Project  # noqa: E402
from hub.main import create_app  # noqa: E402 — env must be set first
from hub.project_workspace import (  # noqa: E402
    # A module-level constant holding the unpatched original, not a function alias.
    resolve_project_workspace as _REAL_RESOLVE_PROJECT_WORKSPACE,  # noqa: N812
)


def assert_engine_is_disposable() -> None:
    """Refuse to drop tables on anything but an in-memory database.

    The backstop for the assignment above: the environment is only one way the engine
    can end up bound to real data (an edited conftest, a `.env` discovered from the
    working directory, a future embedder). Whatever the route, the cost of being wrong
    is a destroyed database that no test failure reports — so the check lives next to
    the destruction, not only next to the configuration.
    """
    url = str(engine.url)
    if ":memory:" not in url:
        raise RuntimeError(
            f"Refusing to run the Hub suite against {url!r}: its fixtures drop every "
            f"table, and this is not an in-memory database. Unset DATABASE_URL (or set "
            f"it to {TEST_DATABASE_URL}) and run again."
        )


assert_engine_is_disposable()


async def seed_test_project() -> None:
    """Create `proj-test` and its API key, before the seeders that iterate projects.

    Ordering is load-bearing: `init_db` seeds default runners and charters for every
    project it finds, so a project created afterwards would come up with neither.
    """
    async with async_session_factory() as session:
        session.add(Project(id=TEST_PROJECT_ID, name=TEST_PROJECT_NAME))
        session.add(
            ApiKey(id=TEST_API_KEY, project_id=TEST_PROJECT_ID, label="bootstrap", revoked=False)
        )
        await session.commit()


@pytest_asyncio.fixture
async def app():
    application = create_app()
    # ASGITransport does not trigger the FastAPI lifespan, so we run init_db
    # (create_all + the instance operator credential) explicitly before each test.
    assert_engine_is_disposable()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    await seed_test_project()
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
        created = await app.post(
            "/api/v1/projects/proj-test/runners", json=payload, headers=auth_headers
        )
        assert created.status_code == 201, created.text
        runner_id = created.json()["id"]
        bound = await app.patch(
            f"/api/v1/projects/proj-test/agents/{agent_name}",
            json={"runner_id": runner_id},
            headers=auth_headers,
        )
        assert bound.status_code == 200, bound.text
        return runner_id

    return _bind


@pytest.fixture
def drain_conversation():
    """Returns an async helper: `await drain_conversation(conversation_id)`.

    Marks a conversation's queued inbound entries delivered, standing in for a turn that
    actually consumed them. Archiving refuses while a conversation holds undelivered entries,
    so any test about what happens *after* archiving has to get past that guard first — and
    faking the state is honest here in a way that faking the guard would not be.
    """
    from sqlalchemy import update

    from hub.db.models import InboundQueueEntry

    async def _drain(conversation_id):
        async with async_session_factory() as session:
            await session.execute(
                update(InboundQueueEntry)
                .where(InboundQueueEntry.conversation_id == conversation_id)
                .values(state="delivered")
            )
            await session.commit()

    return _drain


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
    # A review turn resolves its workspace through `ensure_review_checkout` instead, which shells
    # out to `git worktree add --detach` — same hazard, same default. `test_review_checkout.py`
    # restores the real function against a `tmp_path` repository.
    monkeypatch.setattr(
        worktrees, "ensure_review_checkout", lambda repo_root, agent, sha: repo_root
    )


@pytest.fixture(autouse=True)
def _default_project_workspace(monkeypatch, tmp_path):
    """Every agent-trigger, worktree, workspace-path, and session-sync endpoint now
    calls `project_workspace.resolve_project_workspace(session, project_id)` to root
    its filesystem operations in the project's real registered directory instead of
    the Hub process's `Path.cwd()`. The suite's bootstrap project (`proj-test`) is
    deliberately left unbound in the database by `init_db()` — `test_project_lifecycle.py`'s
    legacy-binding tests exercise binding it themselves via `ProjectLifecycleService`
    directly, bypassing this fixture entirely — so resolving it for real here would either
    break those tests or require every other test in the suite to explicitly register a
    directory just to trigger an agent.

    Default to resolving *any* project_id to this test's own disposable `tmp_path`,
    mirroring `_no_real_worktree_provision`'s "stub away the real thing by default"
    convention above. Tests exercising real, distinct project directories (worktrees,
    workspace paths, context materialization, session-sync worktree release) use the
    `bind_project_workspace` fixture below, which registers a real directory and
    restores the real resolver for that one test.
    """
    import hub.project_workspace as project_workspace

    async def _fake_resolve(session, project_id, *, hub_data_directory=None):
        del session, hub_data_directory
        return project_workspace.ProjectWorkspace(
            project_id=project_id, root=tmp_path, path_key=f"test:{project_id}"
        )

    monkeypatch.setattr(project_workspace, "resolve_project_workspace", _fake_resolve)


@pytest.fixture
def bind_project_workspace(monkeypatch):
    """Returns an async helper: `await bind_project_workspace(directory)`.

    Registers *directory* as the single unbound legacy project's (`proj-test`) real
    working directory through the same lifecycle path a genuine `agentweave` bare
    invocation uses, then restores the real `resolve_project_workspace` for the rest
    of this test — undoing `_default_project_workspace`'s fake above. Use this in place
    of the old `monkeypatch.chdir(repo)` pattern for any test whose real git repository
    must be what the Hub resolves as its project root.
    """
    import hub.project_workspace as project_workspace_module
    from hub.project_lifecycle import ProjectLifecycleService

    async def _bind(directory):
        async with async_session_factory() as session:
            project = await ProjectLifecycleService(session).open_existing(directory)
        monkeypatch.setattr(
            project_workspace_module, "resolve_project_workspace", _REAL_RESOLVE_PROJECT_WORKSPACE
        )
        return project

    return _bind
