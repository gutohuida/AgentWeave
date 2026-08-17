"""Shared test fixtures for AgentWeave Hub."""

import asyncio
import os
import time
from collections import deque

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

# Use in-memory SQLite for tests
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("AW_BOOTSTRAP_API_KEY", "aw_live_testkey_abcdefgh")
os.environ.setdefault("AW_BOOTSTRAP_PROJECT_ID", "proj-test")
os.environ.setdefault("AW_BOOTSTRAP_PROJECT_NAME", "Test Project")

from hub.db.engine import async_session_factory, engine, init_db  # noqa: E402
from hub.db.models import Base  # noqa: E402
from hub.main import create_app  # noqa: E402 — env must be set first
from hub.project_workspace import (
    # A module-level constant holding the unpatched original, not a function alias.
    resolve_project_workspace as _REAL_RESOLVE_PROJECT_WORKSPACE,  # noqa: N812
)  # noqa: E402

# --- temporary diagnostic, remove once the model-switch flake is closed ---------------
#
# `sqlite+aiosqlite:///:memory:` resolves to a **StaticPool**: one DBAPI connection shared by
# every session in the process. SQLAlchemy tracks transaction state per Session, SQLite tracks
# it per connection, so a second session opening and closing concurrently ends the transaction
# out from under the first and discards its pending UPDATE — the first session's `commit()`
# still returns cleanly. Measured in isolation at 105/200 lost with a concurrent poller against
# 0/200 without, which matches the CI failure rate of the one test still red on master.
#
# That establishes the mechanism. This names the culprit: every ROLLBACK on the shared
# connection is recorded with the hub/tests frames that issued it, so the assertion in
# `_await_agent_idle` can print who ended the transaction rather than infer it.
connection_events: deque = deque(maxlen=250)


def _record(kind: str) -> None:
    # Identify by asyncio task and wall-clock, not by stack. These handlers run inside
    # SQLAlchemy's greenlet, so `traceback.extract_stack()` sees only the greenlet's own frames
    # and the application frames are not on it — measured on 0ffd376, where every captured frame
    # list came back empty. The awaiting task, by contrast, is still the current task across the
    # greenlet switch, and `_run_trace` stamps the same clock, so the two interleave exactly.
    try:
        task = asyncio.current_task()
        who = task.get_name() if task is not None else "no-task"
    except RuntimeError:
        who = "no-loop"
    connection_events.append(f"{time.monotonic():.6f} {kind} task={who}")


event.listens_for(engine.sync_engine, "rollback")(lambda conn: _record("ROLLBACK"))
event.listens_for(engine.sync_engine, "commit")(lambda conn: _record("COMMIT"))
# --- end temporary diagnostic ---------------------------------------------------------


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
