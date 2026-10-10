"""F567: a shared dependency directory that could not be linked into a checkout is shown.

`worktrees._symlink_shared_dependencies` used to log a failed link at INFO and go on, so an agent
worked in a checkout without `node_modules` and its builds failed as if by its own fault. The
decision (`overhaul-symlink-failure`): the operator sees it on the run, with the reason and the
remedy, and the agent is told in the turn's own prompt.

Driven through `POST /agent/trigger` with `Path.symlink_to` raising the error Windows gives an
account without the privilege, because a unit test of the helper alone cannot show the run records it.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import AgentOutput
from tests.test_agent_trigger import (
    _REAL_RESOLVE_AGENT_WORKSPACE,
    _await_background_run,
    _fake_pty,
    _fake_run_turn,
    _init_repo,
)

_PRIVILEGE = "[WinError 1314] A required privilege is not held by the client"


def _refuse_symlinks(self, target, target_is_directory=False):  # noqa: ANN001, ANN202
    raise OSError(_PRIVILEGE)


def test_a_failed_link_is_returned_with_its_reason(tmp_path):
    repo = _init_repo(tmp_path / "repo")
    (repo / "node_modules").mkdir()
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    with patch.object(Path, "symlink_to", _refuse_symlinks):
        failures = worktrees._symlink_shared_dependencies(repo, checkout)

    assert [(f.name, f.reason) for f in failures] == [("node_modules", _PRIVILEGE)]
    # Read back from the disk, so it holds for a later turn and after a Hub restart.
    assert [f.name for f in worktrees.shared_dependency_link_failures(repo, checkout)] == [
        "node_modules"
    ]
    (checkout / "node_modules").mkdir()  # the operator installed into the checkout
    assert worktrees.shared_dependency_link_failures(repo, checkout) == []


@pytest.mark.asyncio
async def test_a_failed_link_reaches_the_prompt_and_the_run(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = _init_repo(tmp_path / "repo")
    (repo / "node_modules").mkdir()
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"linker": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("linker", cli="claude")
    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )

    with patch.object(Path, "symlink_to", _refuse_symlinks):  # noqa: SIM117
        with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
            with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
                response = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "linker", "message": "build it"},
                    headers=auth_headers,
                )
                assert response.status_code == 200, response.text
                run_id = response.json()["run_id"]
                await _await_background_run()

    # The agent: told in the prompt it was spawned with, with the reason and a way out.
    argv = fake_spawn.call_args.args[0]
    prompt = next(part for part in argv if "build it" in part)
    assert "node_modules" in prompt and _PRIVILEGE in prompt
    assert "npm install" in prompt or "install" in prompt.lower()

    # The operator: a warning diagnostic in the run's own timeline, coded and carrying the facts.
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(AgentOutput).where(
                        AgentOutput.run_id == run_id, AgentOutput.kind == "diagnostic"
                    )
                )
            )
            .scalars()
            .all()
        )
    found = [r for r in rows if (r.payload or {}).get("code") == "workspace.dependency_link_failed"]
    assert len(found) == 1, [r.payload for r in rows]
    payload = found[0].payload
    assert payload["severity"] == "warning"
    assert "node_modules" in found[0].content and _PRIVILEGE in found[0].content
    assert payload["facts"]["failed"] == [{"name": "node_modules", "reason": _PRIVILEGE}]


@pytest.mark.asyncio
async def test_a_failed_link_is_recorded_on_a_codex_run_too(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """The RPC path records through a different executor from the stream path above."""
    repo = _init_repo(tmp_path / "repo")
    (repo / "node_modules").mkdir()
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"coder": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("coder", cli="codex")

    with patch.object(Path, "symlink_to", _refuse_symlinks):  # noqa: SIM117
        with patch("hub.codex_appserver.run_turn", _fake_run_turn()):  # noqa: SIM117
            with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/codex"):
                response = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "coder", "message": "build it", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert response.status_code == 200, response.text
                run_id = response.json()["run_id"]
                await _await_background_run()

    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(AgentOutput).where(
                        AgentOutput.run_id == run_id, AgentOutput.kind == "diagnostic"
                    )
                )
            )
            .scalars()
            .all()
        )
    codes = [(r.payload or {}).get("code") for r in rows]
    assert codes == ["workspace.dependency_link_failed"], codes
