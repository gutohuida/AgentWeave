"""F349: resolving a project's workspace is a read, and must not open a write transaction.

`resolve_project_workspace` stamped `project.last_seen_at = now` on every call. The routes that call
it first (`/agent/trigger` among them) autoflushed that UPDATE at their next query. That began
SQLite's write transaction there, and it was held through the rest of the route, including a
synchronous `git` subprocess, until the entry's commit. A second trigger arriving in that window waited out the busy
timeout on `UPDATE projects SET last_seen_at` and answered 500 "database is locked" (measured on the
trial Hub, 2026-09-13).

The suite never saw it because `_default_project_workspace` (conftest) replaces the resolver with a
fake in every test. Both tests here restore the real one through `bind_project_workspace`.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import event

from hub import project_workspace
from hub.db.engine import async_session_factory, engine
from hub.db.models import Project

from .test_agent_trigger import _await_background_run, _fake_pty, _init_repo


@pytest.mark.asyncio
async def test_resolving_an_available_workspace_leaves_the_project_unmodified(
    app, bind_project_workspace, tmp_path
):
    del app  # builds the schema
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)

    async with async_session_factory() as session:
        workspace = await project_workspace.resolve_project_workspace(session, "proj-test")
        project = await session.get(Project, "proj-test")

        assert workspace.root == repo.resolve()
        assert project.directory_state == "available"
        assert not session.is_modified(project), (
            "resolving an available workspace changed the project row, so the caller's next query "
            "autoflushes an UPDATE and opens a write transaction it never asked for"
        )


@pytest.mark.asyncio
async def test_a_trigger_writes_nothing_to_the_project_row(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"reader": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("reader", cli="claude")

    statements: list = []

    # Attached for the one request and removed after it: a listener registered at import would
    # judge every statement in the session (DEAD-ENDS 2026-09-10).
    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement)

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            event.listen(engine.sync_engine, "before_cursor_execute", _record)
            try:
                response = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "reader", "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
            finally:
                event.remove(engine.sync_engine, "before_cursor_execute", _record)
            assert response.status_code == 200
            await _await_background_run()

    project_writes = [s for s in statements if s.lstrip().upper().startswith("UPDATE PROJECTS")]
    assert project_writes == [], project_writes
