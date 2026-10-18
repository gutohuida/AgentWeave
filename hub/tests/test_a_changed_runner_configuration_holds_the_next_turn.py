"""F737: a change to the runner's configuration holds the workspace's next turn for the operator.

The workspace judge (`mcp_server._decide`) reads commands as text, and text cannot close writes to
the runner's configuration: `git apply` of a patch, a checkout, an archive extraction, a copy into
the directory. An allow rule written to `.claude/settings.local.json` runs ahead of the approver on
the next turn (F675). So the Hub fingerprints those paths whenever it launches a turn in a
workspace, and a turn whose workspace's runner configuration changed since the last launch there is
held, its input kept, and the operator asked -- naming the files -- on the permission surface.

The acceptance drive: an agent turn writes `.claude/settings.local.json` with `git apply`, a shape
no text rule catches, and the next turn is held and the operator asked.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry
from hub.mcp_server import _decide

from ._background_runs import await_background_runs

_REAL_RESOLVE_AGENT_WORKSPACE = worktrees.resolve_agent_workspace
_RESULT = '{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n'

# What the agent's turn applies: a patch creating its runner's local settings with an allow rule.
_PATCH = """\
diff --git a/.claude/settings.local.json b/.claude/settings.local.json
new file mode 100644
--- /dev/null
+++ b/.claude/settings.local.json
@@ -0,0 +1 @@
+{"permissions": {"allow": ["Bash", "PowerShell"]}}
"""


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "README.md").write_text("base\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-q", "-m", "base")
    return path


class _Runner:
    """A fake PTY spawn: each call is one turn. `actions[i]` runs in the turn's cwd, as a tool call
    the agent made during turn *i* would."""

    def __init__(self, actions=()):
        self.actions = list(actions)
        self.cwds: list = []

    def __call__(self, *args, **kwargs):
        from unittest.mock import MagicMock

        cwd = Path(kwargs["cwd"])
        index = len(self.cwds)
        self.cwds.append(cwd)
        if index < len(self.actions) and self.actions[index] is not None:
            self.actions[index](cwd)
        session = MagicMock()
        session.pid = 4242
        remaining = iter([_RESULT, ""])
        session.read.side_effect = lambda *a, **k: next(remaining, "")
        session.wait.return_value = 0
        return session


def _apply_settings_patch(cwd: Path) -> None:
    patch_file = cwd / "agent.patch"
    patch_file.write_text(_PATCH, encoding="utf-8", newline="\n")
    _git(cwd, "apply", "agent.patch")
    patch_file.unlink()


async def _setup(app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"writer": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("writer", cli="claude")
    return repo


async def _trigger(app, auth_headers, message, conversation_id=None):
    body = {"agent": "writer", "message": message}
    if conversation_id:
        body["conversation_id"] = conversation_id
    response = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json=body,
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    await await_background_runs()
    return response.json()


async def _queued(agent="writer"):
    async with async_session_factory() as db:
        rows = await db.execute(
            select(InboundQueueEntry).where(
                InboundQueueEntry.agent == agent, InboundQueueEntry.state == "queued"
            )
        )
        return list(rows.scalars())


async def _pending_requests(app, auth_headers):
    response = await app.get("/api/v1/projects/proj-test/permission-requests", headers=auth_headers)
    assert response.status_code == 200
    return response.json()


def test_no_text_rule_sees_the_write(tmp_path, monkeypatch):
    """Why the boundary is structural: the judge allows the command that makes the write."""
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    assert _decide("Bash", {"command": "git apply agent.patch"})["allow"] is True


@pytest.mark.asyncio
async def test_a_settings_write_by_git_apply_holds_the_next_turn_and_asks_the_operator(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await _setup(app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch)
    runner = _Runner(actions=[_apply_settings_patch])

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", runner):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            first = await _trigger(app, auth_headers, "first turn")
            conversation = first["conversation_id"]
            assert len(runner.cwds) == 1
            workspace = runner.cwds[0]
            assert (workspace / ".claude" / "settings.local.json").is_file()

            # The next turn in that workspace is held: not started, its input kept.
            await _trigger(app, auth_headers, "second turn", conversation)
            assert len(runner.cwds) == 1
            queued = await _queued()
            assert [entry.content for entry in queued] == ["second turn"]
            assert ".claude/settings.local.json" in (queued[0].waiting_reason or "")

            # The operator is asked on the permission surface, naming the file.
            pending = await _pending_requests(app, auth_headers)
            assert len(pending) == 1
            request = pending[0]
            assert request["agent"] == "writer"
            assert request["run_id"] is None
            assert ".claude/settings.local.json" in request["tool_input"]["paths"]

            # Another schedule does not ask again.
            await _trigger(app, auth_headers, "third turn", conversation)
            assert len(runner.cwds) == 1
            assert len(await _pending_requests(app, auth_headers)) == 1

            # Allowing records the new fingerprint and starts the held turn.
            decided = await app.post(
                f"/api/v1/projects/proj-test/permission-requests/{request['id']}/decide",
                json={"allow": True},
                headers=auth_headers,
            )
            assert decided.status_code == 200, decided.text
            await await_background_runs()
            assert len(runner.cwds) == 2
            assert await _queued() == []

            # And the turn after that is not asked about the same content again.
            await _trigger(app, auth_headers, "fourth turn", conversation)
            assert len(runner.cwds) == 3
            assert await _pending_requests(app, auth_headers) == []


@pytest.mark.asyncio
async def test_a_refusal_keeps_the_turn_held_until_the_operator_sends_something_new(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    from hub.turn_scheduler import schedule_agent

    await _setup(app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch)
    runner = _Runner(actions=[_apply_settings_patch])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", runner):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            first = await _trigger(app, auth_headers, "first turn")
            conversation = first["conversation_id"]
            await _trigger(app, auth_headers, "second turn", conversation)
            (request,) = await _pending_requests(app, auth_headers)
            denied = await app.post(
                f"/api/v1/projects/proj-test/permission-requests/{request['id']}/decide",
                json={"allow": False},
                headers=auth_headers,
            )
            assert denied.status_code == 200

            # Re-scheduling the same input meets the refusal: held, not asked again.
            await schedule_agent("proj-test", "writer")
            await await_background_runs()
            assert len(runner.cwds) == 1
            assert await _pending_requests(app, auth_headers) == []
            (queued,) = await _queued()
            assert "refused" in queued.waiting_reason
            assert queued.state == "queued"

            # New operator input is how they reconsider: asked again, still held.
            await _trigger(app, auth_headers, "please, again", conversation)
            assert len(runner.cwds) == 1
            (again,) = await _pending_requests(app, auth_headers)
            assert again["id"] != request["id"]
            assert len(await _queued()) == 2


@pytest.mark.asyncio
async def test_restoring_the_files_releases_the_turn_without_an_answer(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    from hub.turn_scheduler import schedule_agent

    await _setup(app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch)
    runner = _Runner(actions=[_apply_settings_patch])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", runner):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            first = await _trigger(app, auth_headers, "first turn")
            await _trigger(app, auth_headers, "second turn", first["conversation_id"])
            assert len(runner.cwds) == 1
            (runner.cwds[0] / ".claude" / "settings.local.json").unlink()
            await schedule_agent("proj-test", "writer")
            await await_background_runs()
            assert len(runner.cwds) == 2


@pytest.mark.asyncio
async def test_a_first_launch_records_its_baseline_without_asking(
    app, auth_headers, bind_runner, tmp_path
):
    """The project directory (the default test workspace) already holds a settings file: its
    first launch records it and starts."""
    settings = tmp_path / ".claude" / "settings.local.json"
    settings.parent.mkdir(parents=True)
    settings.write_text('{"permissions": {"allow": ["Bash"]}}', encoding="utf-8")
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"writer": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner("writer", cli="claude")
    runner = _Runner()
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", runner):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            await _trigger(app, auth_headers, "first turn")
    assert len(runner.cwds) == 1
    assert await _pending_requests(app, auth_headers) == []


async def _hold(workspace: Path, root: Path, agent="writer"):
    from hub.runner_config_guard import hold_if_changed

    async with async_session_factory() as db:
        hold = await hold_if_changed(
            db,
            project_id="proj-test",
            agent=agent,
            conversation_id=None,
            workspace_dir=str(workspace),
            project_root=str(root),
        )
        await db.commit()
        return hold


@pytest.mark.asyncio
async def test_a_fresh_checkout_is_asked_about_config_the_project_directory_does_not_hold(
    app, tmp_path
):
    """A new checkout's first launch is silent only when it brings nothing new: an agent's commit
    to `.mcp.json`, checked out fresh for its reviewer, is asked about."""
    root = tmp_path / "root"
    (root / ".claude").mkdir(parents=True)
    (root / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    same = tmp_path / "same"
    (same / ".claude").mkdir(parents=True)
    (same / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    brings = tmp_path / "brings"
    brings.mkdir()
    (brings / ".mcp.json").write_text('{"mcpServers": {}}', encoding="utf-8")

    assert await _hold(root, root) is None
    assert await _hold(same, root) is None
    held = await _hold(brings, root)
    assert held is not None
    assert ".mcp.json (added)" in held.detail


@pytest.mark.asyncio
async def test_a_hook_added_under_a_directory_entry_is_a_change(app, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    assert await _hold(root, root) is None
    hooks = root / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre.sh").write_text("echo hi", encoding="utf-8")
    held = await _hold(root, root)
    assert held is not None
    assert ".claude/hooks/pre.sh (added)" in held.detail


def test_the_judge_and_the_fingerprint_cover_one_list():
    """`mcp_server` is spawned standalone and restates the list; the two must agree."""
    from hub import mcp_server, runner_config

    assert mcp_server._RUNNER_CONFIG_PATHS == runner_config.RUNNER_CONFIG_PATHS


def test_the_fingerprint_sees_additions_changes_and_removals(tmp_path):
    from hub import runner_config

    empty = runner_config.fingerprint(str(tmp_path))
    assert empty == {}
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text("a", encoding="utf-8")
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    one = runner_config.fingerprint(str(tmp_path))
    (tmp_path / ".codex" / "config.toml").write_text("b", encoding="utf-8")
    (tmp_path / ".mcp.json").unlink()
    two = runner_config.fingerprint(str(tmp_path))
    assert runner_config.changes(empty, one) == [
        (".codex/config.toml", "added"),
        (".mcp.json", "added"),
    ]
    assert runner_config.changes(one, two) == [
        (".codex/config.toml", "changed"),
        (".mcp.json", "removed"),
    ]
    assert runner_config.digest(one) != runner_config.digest(two)
    # Not the runner's configuration: instructions and skills are ordinary work.
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "x.md").write_text("x", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("x", encoding="utf-8")
    assert runner_config.fingerprint(str(tmp_path)) == two
