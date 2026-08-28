"""Integration tests for the rewritten POST /api/v1/projects/proj-test/agent/trigger (task 3.5).

`PtySession.spawn` is mocked throughout — these tests exercise the endpoint's request
handling, pre-flight checks, and background execution/recording loop, not the real CLIs
(those are covered live — see tasks.md's task 3.5 entry — and by test_runner_parsing.py's
fixtures, which use real captured output).
"""

import asyncio
import json
import subprocess
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import hub.api.v1.agent_trigger as agent_trigger
from hub import worktrees
from hub.inbound_queue import DELIVERY_ATTEMPT_LIMIT
from hub.sse import sse_manager

_REAL_RESOLVE_AGENT_WORKSPACE = worktrees.resolve_agent_workspace


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


async def _await_background_run():
    """Wait for whatever background run task(s) the last trigger call started."""
    while agent_trigger._background_runs:
        tasks = list(agent_trigger._background_runs)
        for task in tasks:
            await task


async def _wait_for_active_pty(run_id, timeout=2.0):
    """Poll until `_execute_run` has registered *run_id*'s PtySession.

    The stop endpoint can only reach a run's process via `agent_trigger._active_ptys`,
    which the background task populates asynchronously after `trigger_agent`'s HTTP
    response has already returned (unlike the Run row's "running" status, which is
    committed synchronously in the request handler itself) — so a test calling stop
    right after trigger must wait for this, not assume it's already there.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if run_id in agent_trigger._active_ptys:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} never registered an active pty")


async def _wait_for_active_app_server_run(run_id, timeout=2.0):
    """Poll until `_execute_codex_appserver_run` has registered *run_id* as in-flight.

    App-server equivalent of `_wait_for_active_pty` above: this path has no PtySession to
    register in `_active_ptys`, only membership in `_active_app_server_runs`.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if run_id in agent_trigger._active_app_server_runs:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} never registered as an active app-server run")


def _bind_codex_runner_with_flags(app, auth_headers, flags):
    """Returns an async helper: `await _bind(agent_name)` binding a codex Runner carrying
    *flags*, mirroring `bind_runner`'s shape but going through the raw runners API (like
    `test_trigger_command_uses_bound_runner_model_and_flags`) since `bind_runner` has no way
    to set `flags`.
    """

    async def _bind(agent_name):
        created = await app.post(
            "/api/v1/projects/proj-test/runners",
            json={"name": f"{agent_name}-runner", "cli": "codex", "flags": list(flags)},
            headers=auth_headers,
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


def _bind_codex_app_server_runner(app, auth_headers):
    """Codex on the app-server transport. Explicit here, though it is also the default."""
    return _bind_codex_runner_with_flags(app, auth_headers, ["--app-server"])


def _bind_codex_exec_runner(app, auth_headers):
    """Codex opted out to the legacy `exec` transport."""
    return _bind_codex_runner_with_flags(app, auth_headers, ["--no-app-server"])


def _fake_run_turn(
    *,
    thread_id="thread-appserver-1",
    status="completed",
    error=None,
    events=(),
    usage=None,
    accounting=None,
):
    """Build an `AsyncMock` replacement for `codex_appserver.run_turn` that drives the
    caller's own callbacks the way a real turn would (thread bound before any event,
    events before usage/accounting, outcome last) — real behavior via `side_effect`, call
    recording via `AsyncMock` itself, exactly like `_fake_pty` does for the PTY path.
    """
    from hub.codex_appserver import TurnOutcome

    async def _run(**kwargs):
        if kwargs.get("on_thread_started") is not None:
            await kwargs["on_thread_started"](thread_id)
        for event in events:
            await kwargs["on_event"](event)
        if usage is not None and kwargs.get("on_usage") is not None:
            await kwargs["on_usage"](usage)
        if accounting is not None and kwargs.get("on_accounting") is not None:
            await kwargs["on_accounting"](accounting)
        return TurnOutcome(thread_id=thread_id, status=status, error=error)

    return AsyncMock(side_effect=_run)


def _fake_pty(lines, exit_code=0, pid=4242):
    """Build a mock PtySession.spawn() replacement streaming `lines` then EOF.

    A **fresh** session per call. Since a failed run hands its input back and schedules the retry
    itself, a test whose run exits non-zero spawns again — and a single reused mock has an
    exhausted `read.side_effect` by then. The `StopIteration` that raises inside the executor does
    not surface as a failure; it hangs the run loop, which is how this was found.
    """

    def _spawn(*args, **kwargs):
        session = MagicMock()
        session.pid = pid
        # EOF **forever** after the scripted lines, not a finite `side_effect` list. A list runs
        # out, and the docstring above already records what running out costs: `StopIteration`
        # raised inside the executor does not surface as a failure, it hangs the run loop — and a
        # hung run loop is a `Run` row stuck at `running`, which then makes the *next* trigger for
        # that agent return 200/"queued" instead of running. One extra read is enough, and how
        # many reads happen is a timing detail that differed between this machine and CI.
        remaining = iter([*lines, ""])
        session.read.side_effect = lambda *a, **k: next(remaining, "")
        session.wait.return_value = exit_code
        return session

    return MagicMock(side_effect=_spawn)


@pytest.mark.asyncio
async def test_unbound_agent_accumulates_queue_with_visible_reason(app, auth_headers):
    """An agent with no bound Runner cannot be spawned — it queues with a stated reason
    rather than failing the request outright. Replaces the old "manual runner" scenario:
    Runner.cli only supports claude/codex now, so "no execution capability configured" is
    expressed as no binding at all, not a runner value of "manual"."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"offline-agent": {}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    resp = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline-agent", "message": "hi", "session_mode": "new"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    assert "runner" in resp.json()["waiting_reason"].lower()
    assert "bound" in resp.json()["waiting_reason"].lower()

    queue_status = await app.get(
        "/api/v1/projects/proj-test/queue/offline-agent/status",
        headers=auth_headers,
    )
    assert queue_status.status_code == 200
    assert queue_status.json()["waiting_reason"] == resp.json()["waiting_reason"]


@pytest.mark.asyncio
async def test_resume_without_session_id_is_rejected(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "claude", "message": "hi", "session_mode": "resume"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "session_id" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_session_mode_is_rejected(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "claude", "message": "hi", "session_mode": "sideways"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_successful_trigger_returns_run_id_and_spawns(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"trigger-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("trigger-claude", cli="claude")

    fake_spawn = _fake_pty(
        [
            '{"type":"system","subtype":"init","session_id":"sess-live-1"}\n',
            '{"type":"assistant","message":{"content":[{"type":"text","text":"Hi there"}]},'
            '"session_id":"sess-live-1"}\n',
            '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-live-1"}\n',
        ]
    )
    # Nested rather than combined: SIM117 is disabled for this suite as a style choice
    # (see pyproject.toml's per-file-ignores), not a compatibility requirement.
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "trigger-claude", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["status"] == "running"
            assert data["run_id"].startswith("run-")
            run_id = data["run_id"]

            await _await_background_run()

    output_resp = await app.get(
        "/api/v1/projects/proj-test/agents/trigger-claude/output", headers=auth_headers
    )
    assert output_resp.status_code == 200
    rows = output_resp.json()
    assert any(row["content"] == "Hi there" for row in rows)
    assert any(row["run_id"] == run_id for row in rows)
    assert fake_spawn.call_args.kwargs["dimensions"] == (24, 32_767)


@pytest.mark.asyncio
async def test_trigger_refuses_an_archived_agent(app, auth_headers, bind_runner):
    """D15 (autonomous run P5, 2026-08-20): nothing between a trigger and a spawned `Run` used
    to consult `Agent.lifecycle`, so an archived agent — reachable directly by name even though
    it is no longer offered anywhere — could still be spawned and its `Run` would still carry
    loop/job creator authority in its name's stead. `agent-configuration`'s spec states "nothing
    runs an archived agent" as an existing fact; this is what makes it one.
    """
    reg = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "retired", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert reg.status_code == 200
    await bind_runner("retired", cli="claude")
    archived = await app.post(
        "/api/v1/projects/proj-test/agents/retired/archive", headers=auth_headers
    )
    assert archived.status_code == 200

    resp = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "retired", "message": "hi", "session_mode": "new"},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "archived" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_trigger_command_uses_bound_runner_model_and_flags(app, auth_headers):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"runner-options": {"runner": "codex", "model": "legacy-model"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    runner = (
        await app.post(
            "/api/v1/projects/proj-test/runners",
            json={
                "name": "Configured Claude",
                "cli": "claude",
                "model": "claude-opus-5",
                "flags": ["--effort", "high"],
            },
            headers=auth_headers,
        )
    ).json()
    bound = await app.patch(
        "/api/v1/projects/proj-test/agents/runner-options",
        json={"runner_id": runner["id"]},
        headers=auth_headers,
    )
    assert bound.status_code == 200

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "runner-options", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert response.status_code == 200
            await _await_background_run()

    command = fake_spawn.call_args.args[0]
    assert command[command.index("--model") + 1] == "claude-opus-5"
    assert command[command.index("--effort") + 1] == "high"
    assert "legacy-model" not in command


@pytest.mark.asyncio
async def test_trigger_materializes_bound_charter_context(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={
            "data": {
                "name": "Live Context Project",
                "agents": {"chartered": {"runner": "claude", "read_only": True}},
            }
        },
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("chartered", cli="claude")
    create = await app.post(
        "/api/v1/projects/proj-test/charters",
        json={"name": "Live Charter", "content": "LIVE_CHARTER_MARKER"},
        headers=auth_headers,
    )
    assert create.status_code == 201
    charter_id = create.json()["id"]
    bind = await app.patch(
        "/api/v1/projects/proj-test/agents/chartered",
        json={"charter_id": charter_id},
        headers=auth_headers,
    )
    assert bind.status_code == 200

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "chartered", "message": "verify context", "session_mode": "new"},
                headers=auth_headers,
            )
            assert response.status_code == 200
            assert response.json()["status"] == "running"
            await _await_background_run()

    command = fake_spawn.call_args.args[0]
    context_flag = command.index("--append-system-prompt-file")
    context_path = Path(command[context_flag + 1])
    assert context_path.exists()
    context = context_path.read_text(encoding="utf-8")
    # The profile names the Hub's own project record. It used to name the synced session's
    # "Live Context Project" instead, but nothing writes that table any more — see
    # 2026-08-06-hub-collaboration-and-conversation-fixes.
    assert "- Project: Test Project" in context
    assert "## Charter: Live Charter" in context
    assert "LIVE_CHARTER_MARKER" in context

    # The agent is told the directory it is actually running in. Without this it resolved paths
    # against the project root while executing in a worktree, and every read and write outside
    # that worktree was refused (2026-08-06-agent-permissions-tool-schemas-and-base-knowledge).
    work_dir = str(context_path.parent.parent.parent)
    assert "### Your workspace" in context
    assert f"- Working directory: `{work_dir}`" in context
    assert "Resolve every path against this directory" in context


@pytest.mark.asyncio
async def test_writing_agent_worktree_exists_before_first_spawn(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
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
    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "writer", "message": "write"},
                headers=auth_headers,
            )
            assert response.status_code == 200
            await _await_background_run()

    expected = worktrees.worktree_path(repo, "writer")
    assert expected.is_dir()
    assert Path(fake_spawn.call_args.kwargs["cwd"]) == expected


@pytest.mark.asyncio
async def test_f52_writing_agent_gets_the_auto_snapshot_notice(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """F52 (`scripts/drive/FINDINGS.md`, 2026-08-26): a writing agent with a real worktree to
    snapshot must be told, before it can spend its turn fighting a refused git command, that the
    Hub commits its worktree automatically at the end of every turn regardless."""
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
    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )
    captured_kwargs = {}
    real_build_command = agent_trigger.build_command

    def _capturing_build_command(**kwargs):
        captured_kwargs.update(kwargs)
        return real_build_command(**kwargs)

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with patch("hub.api.v1.agent_trigger.build_command", _capturing_build_command):
                response = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "writer", "message": "write"},
                    headers=auth_headers,
                )
                assert response.status_code == 200
                await _await_background_run()

    assert "do not need to" in captured_kwargs["prompt"].lower()
    assert "record_evidence" in captured_kwargs["prompt"]


@pytest.mark.asyncio
async def test_f52_read_only_agent_gets_no_auto_snapshot_notice(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """The read-only companion to the test above: an agent with no worktree has nothing for
    `snapshot_worktree` to commit, so the notice — which promises exactly that — must not
    appear and imply a guarantee this turn cannot back up."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"reader": {"runner": "claude", "read_only": True}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("reader", cli="claude")
    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )
    captured_kwargs = {}
    real_build_command = agent_trigger.build_command

    def _capturing_build_command(**kwargs):
        captured_kwargs.update(kwargs)
        return real_build_command(**kwargs)

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with patch("hub.api.v1.agent_trigger.build_command", _capturing_build_command):
                response = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "reader", "message": "inspect"},
                    headers=auth_headers,
                )
                assert response.status_code == 200
                await _await_background_run()

    assert "do not need to" not in captured_kwargs["prompt"].lower()


@pytest.mark.asyncio
async def test_read_only_agent_spawns_in_primary_checkout(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"reader": {"runner": "claude", "read_only": True}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("reader", cli="claude")
    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "reader", "message": "inspect"},
                headers=auth_headers,
            )
            assert response.status_code == 200
            await _await_background_run()

    assert Path(fake_spawn.call_args.kwargs["cwd"]) == repo
    assert not worktrees.worktree_path(repo, "reader").exists()


@pytest.mark.asyncio
async def test_writing_agent_cannot_bypass_isolation_with_work_dir(
    app, auth_headers, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"writer": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "writer", "message": "write", "work_dir": "."},
            headers=auth_headers,
        )

    assert response.status_code == 400
    assert "isolation" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_writing_agent_runs_in_place_when_the_project_is_not_a_repository(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    await bind_project_workspace(plain)
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"writer": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("writer", cli="claude")

    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "writer", "message": "write"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] != "queued", body.get("waiting_reason")
    assert not (plain / ".git").exists()


@pytest.mark.asyncio
async def test_writing_agent_is_not_spawned_when_a_real_repository_cannot_be_prepared(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """The half of fail-closed that survives: the project has isolation and cannot get it."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)

    def fail(*args, **kwargs):
        raise worktrees.IsolationUnavailableError("worktree registered to the wrong ref")

    monkeypatch.setattr(worktrees, "ensure_worktree", fail)
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"writer": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("writer", cli="claude")

    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "writer", "message": "write"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert "wrong ref" in response.json()["waiting_reason"]


@pytest.mark.asyncio
async def test_work_dir_is_accepted_for_a_writer_when_there_is_no_isolation_to_override(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    plain = tmp_path / "not-a-repo"
    (plain / "sub").mkdir(parents=True)
    await bind_project_workspace(plain)
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"writer": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("writer", cli="claude")

    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "writer", "message": "write", "work_dir": "sub"},
            headers=auth_headers,
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_trigger_injects_identity_env_and_tells_agent_the_access_path(
    app, auth_headers, bind_runner, monkeypatch
):
    """Task 4.1: the Hub — not the agent — establishes identity at spawn, as an env var
    the tool surface reads rather than a caller-supplied parameter. Task 4.5: the agent is
    told, in its very first prompt, which access path (MCP vs. CLI commands) is in use.
    Claude accepts per-run MCP configuration, so the Hub injects the canonical surface
    without relying on a global client registration.
    """
    monkeypatch.setenv("HUB_API_KEY", "aw_live_parent-secret")
    monkeypatch.setenv("HUB_PROJECT_ID", "parent-project")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///C:/live/agentweave.db")
    monkeypatch.setenv("AW_BOOTSTRAP_API_KEY", "aw_live_parent-bootstrap")
    monkeypatch.setenv("AW_TICKET_SECRET", "parent-ticket-secret")
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"identity-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("identity-claude", cli="claude")

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"sess-identity-1"}\n']
    )
    captured_kwargs = {}
    real_build_command = agent_trigger.build_command

    def _capturing_build_command(**kwargs):
        captured_kwargs.update(kwargs)
        return real_build_command(**kwargs)

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with patch("hub.api.v1.agent_trigger.build_command", _capturing_build_command):
                resp = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={
                        "agent": "identity-claude",
                        "message": "do the thing",
                        "session_mode": "new",
                    },
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                run_id = resp.json()["run_id"]
                await _await_background_run()

    spawned_env = fake_spawn.call_args.kwargs["env"]
    assert spawned_env["AW_AGENT_IDENTITY"] == "identity-claude"
    assert spawned_env["AW_RUN_ID"] == run_id
    run_token = spawned_env["AW_RUN_TOKEN"]
    assert run_token.startswith("aw_run_")
    assert run_token not in resp.text
    assert "HUB_API_KEY" not in spawned_env
    assert "HUB_PROJECT_ID" not in spawned_env
    # Service configuration is not run authority either. DATABASE_URL is the destructive
    # one: an agent that inherits it gets a writable handle to the operator's live
    # database, and `pytest hub/tests/` drops every table in whatever it names.
    assert "DATABASE_URL" not in spawned_env
    assert "AW_BOOTSTRAP_API_KEY" not in spawned_env
    assert "AW_TICKET_SECRET" not in spawned_env
    # The Hub's own environment must be inherited, not replaced, by adding these keys.
    assert "PATH" in spawned_env or "Path" in spawned_env
    # The boundary the "Workspace only" posture enforces is the directory the run actually
    # executes in — the same value the context renderer names as "Your workspace". If these ever
    # diverge, an agent is refused at a line it was never shown.
    assert spawned_env["AW_WORKSPACE_DIR"] == fake_spawn.call_args.kwargs["cwd"]

    prompt = captured_kwargs["prompt"]
    assert "do the thing" in prompt
    assert "the `agentweave` MCP tools are available" in prompt
    assert captured_kwargs["mcp_command"][-1].endswith("mcp_server.py")

    from hub.agent_auth import hash_run_token
    from hub.db.engine import async_session_factory
    from hub.db.models import Run

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.capability_token_hash == hash_run_token(run_token)
        assert run.capability_token_hash != run_token


@pytest.mark.asyncio
async def test_trigger_stamps_the_new_run_with_this_hub_instances_id(
    app, auth_headers, bind_runner, monkeypatch
):
    """Task 4.1: every newly minted run carries this process's own stable instance
    identity, so `agent_auth.get_agent_actor` can later refuse a credential minted by a
    different Hub instance (see design.md Decision 3)."""
    from hub import instance_identity

    monkeypatch.setattr(instance_identity, "_instance_id", "test-instance-id")

    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"instance-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("instance-claude", cli="claude")

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"sess-instance-1"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "instance-claude", "message": "do the thing"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            run_id = resp.json()["run_id"]
            await _await_background_run()

    from hub.db.engine import async_session_factory
    from hub.db.models import Run

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.instance_id == "test-instance-id"


@pytest.mark.asyncio
async def test_trigger_respects_explicit_mcp_override_without_probing(
    app, auth_headers, bind_runner, monkeypatch
):
    """An operator's explicit `hub_client: "mcp"` override must be honored even though
    conftest's autouse fixture defaults the probe to False — the override skips probing
    entirely rather than merely outvoting it."""

    def _boom(cli):
        raise AssertionError("override must skip probing entirely")

    monkeypatch.setattr("hub.launchability.probe_mcp_registered", _boom)

    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"override-claude": {"runner": "claude", "hub_client": "mcp"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("override-claude", cli="claude")

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"sess-override-1"}\n']
    )
    captured_kwargs = {}
    real_build_command = agent_trigger.build_command

    def _capturing_build_command(**kwargs):
        captured_kwargs.update(kwargs)
        return real_build_command(**kwargs)

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with patch("hub.api.v1.agent_trigger.build_command", _capturing_build_command):
                resp = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "override-claude", "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                await _await_background_run()

    assert "the `agentweave` MCP tools are available" in captured_kwargs["prompt"]


@pytest.mark.asyncio
async def test_codex_exec_trigger_uses_headless_pipe_instead_of_pty(app, auth_headers):
    """The `exec` transport runs headless through a pipe, never a PTY.

    Codex now defaults to app-server, so this must opt out explicitly to exercise `exec`.
    """
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"trigger-codex": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await _bind_codex_exec_runner(app, auth_headers)("trigger-codex")

    fake_spawn = _fake_pty(
        [
            '{"type":"thread.started","thread_id":"thread-codex-1"}\n',
            '{"type":"item.completed","item":{"id":"item-1",'
            '"type":"agent_message","text":"headless"}}\n',
            '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n',
        ]
    )
    with patch("hub.api.v1.agent_trigger.PipeSession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.api.v1.agent_trigger.PtySession.spawn") as pty_spawn:
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
                resp = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "trigger-codex", "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                run_id = resp.json()["run_id"]
                await _await_background_run()

    fake_spawn.assert_called_once()
    pty_spawn.assert_not_called()

    from sqlalchemy import select

    from hub.db.engine import async_session_factory
    from hub.db.models import TurnUsage

    async with async_session_factory() as session:
        result = await session.execute(select(TurnUsage).where(TurnUsage.run_id == run_id))
        usage = result.scalar_one()
        assert usage.status == "measured"
        assert usage.input_tokens == 1
        assert usage.output_tokens == 1
        assert usage.total_tokens == 2


@pytest.mark.asyncio
async def test_run_without_usage_records_unavailable_once(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"no-usage": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("no-usage", cli="claude")

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s-none"}\n']
    )
    with (
        patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
    ):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "no-usage", "message": "hi"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        await _await_background_run()

    from sqlalchemy import func, select

    from hub.db.engine import async_session_factory
    from hub.db.models import TurnUsage

    async with async_session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(TurnUsage).where(TurnUsage.run_id == run_id)
        )
        result = await session.execute(select(TurnUsage).where(TurnUsage.run_id == run_id))
        usage = result.scalar_one()
        assert count == 1
        assert usage.status == "unavailable"
        assert usage.total_tokens is None


@pytest.mark.asyncio
async def test_second_trigger_while_first_is_running_is_queued(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"busy-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("busy-claude", cli="claude")

    # A spawn whose read() never returns EOF on its own — simulates a run still in
    # progress when the second trigger request arrives.
    # Genuinely blocks .read() in the executor thread until released — a MagicMock
    # returning "" immediately completes the background task before the second request
    # even runs (it's all one event loop, no real process), which would make this test
    # flaky/meaningless. A real block is the only way to deterministically catch the Run
    # row still in "running" state when the second request's concurrency guard reads it.
    import threading

    release = threading.Event()

    def _blocking_read(size=4096):
        release.wait()
        return ""

    hanging_session = MagicMock()
    hanging_session.pid = 999
    hanging_session.read.side_effect = _blocking_read
    hanging_session.wait.return_value = 0

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=hanging_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            try:
                first = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "busy-claude", "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert first.status_code == 200

                second = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "busy-claude", "message": "again", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert second.status_code == 200
                assert second.json()["status"] == "queued"
                assert "already running" in second.json()["waiting_reason"]
            finally:
                release.set()
                await _await_background_run()


@pytest.mark.asyncio
async def test_spawn_failure_marks_run_failed(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"missing-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("missing-claude", cli="claude")

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn",
        MagicMock(side_effect=FileNotFoundError("claude was not found in PATH")),
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "missing-claude", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            # The pre-flight probe (mocked to report present) accepts the request; the
            # actual spawn failure happens in the background task and is reflected on the
            # Run row, not the HTTP response — matches "spawn directly, return an
            # identifier" (the identifier's outcome is observable via the run record, not
            # blocking the response).
            assert resp.status_code == 200
            run_id = resp.json()["run_id"]

            await _await_background_run()

    from hub.db.engine import async_session_factory
    from hub.db.models import Run

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.status == "failed"
        assert "not found in PATH" in run.error
        from sqlalchemy import select

        from hub.db.models import InboundQueueEntry

        # The input goes back rather than being consumed by a run that never started. It no longer
        # *rests* in `queued`, because a returned entry now schedules its own retry — this spawn
        # fails identically every time, so the entry is handed back, retried to the cap, and then
        # abandoned with a stated reason. What must hold either way is that the message is
        # accounted for rather than silently eaten.
        entries = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == "missing-claude")
                )
            )
            .scalars()
            .all()
        )
        assert [entry.content for entry in entries] == ["hi"]
        assert entries[0].delivery_attempts == DELIVERY_ATTEMPT_LIMIT
        assert entries[0].state == "withdrawn"
        assert "stopped retrying" in entries[0].abandoned_reason


def _drain(queue):
    """Collect every SSE event currently queued as (event_type, parsed_data)."""
    events = []
    while True:
        try:
            item = queue.get_nowait()
        except Exception:  # asyncio.QueueEmpty
            break
        events.append((item.event, json.loads(item.data)))
    return events


@pytest.mark.asyncio
async def test_successful_run_broadcasts_started_and_completed_lifecycle_events(
    app, auth_headers, bind_runner
):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"lifecycle-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("lifecycle-claude", cli="claude")
    project_id = (await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)).json()[
        "project_id"
    ]
    queue = sse_manager.subscribe(project_id)

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"sess-lc-1"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "lifecycle-claude", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            run_id = resp.json()["run_id"]
            await _await_background_run()

    events = _drain(queue)
    started = [d for t, d in events if t == "run_started"]
    completed = [d for t, d in events if t == "run_completed"]
    assert len(started) == 1
    assert started[0]["agent"] == "lifecycle-claude"
    assert started[0]["run_id"] == run_id
    assert started[0]["runner"] == "claude"
    assert len(completed) == 1
    assert completed[0]["exit_code"] == 0
    assert completed[0]["session_id"] == "sess-lc-1"
    assert not [d for t, d in events if t == "run_failed"]

    from hub.db.engine import async_session_factory
    from hub.db.models import EventLog

    async with async_session_factory() as db:
        from sqlalchemy import select

        rows = (
            (
                await db.execute(
                    select(EventLog).where(
                        EventLog.project_id == project_id, EventLog.agent == "lifecycle-claude"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert any(r.event_type == "run_started" for r in rows)
    assert any(r.event_type == "run_completed" for r in rows)


@pytest.mark.asyncio
async def test_nonzero_exit_broadcasts_run_failed_not_run_completed(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"failing-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("failing-claude", cli="claude")
    project_id = (await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)).json()[
        "project_id"
    ]
    queue = sse_manager.subscribe(project_id)

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"error","is_error":true,"session_id":"sess-fail-1"}\n'],
        exit_code=1,
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "failing-claude", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            await _await_background_run()

    events = _drain(queue)
    failed = [d for t, d in events if t == "run_failed"]
    # One per attempt: a failed run hands its input back and schedules the retry, and this spawn
    # fails identically each time, so the cap is what ends it. The subject of this test is that a
    # non-zero exit is reported as `run_failed` and never as `run_completed`.
    assert len(failed) == DELIVERY_ATTEMPT_LIMIT
    assert {d["exit_code"] for d in failed} == {1}
    assert not [d for t, d in events if t == "run_completed"]


@pytest.mark.asyncio
async def test_an_unexpectedly_failed_run_still_gets_an_accounting_outcome(
    app, auth_headers, bind_runner
):
    """F92. `_execute_run` has five terminal sites and this one — the catch-all for an error
    nothing anticipated — was the only one that ended a run without recording an accounting
    outcome. The spec asks for "exactly one accounting outcome for every Hub-owned run after that
    run ends", not for the runs whose ending we predicted. `RuntimeError` rather than
    `FileNotFoundError` on purpose: the latter has its own branch, which already recorded one."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"unexpected-boom": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("unexpected-boom", cli="claude")

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn",
        MagicMock(side_effect=RuntimeError("something nobody wrote a branch for")),
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "unexpected-boom", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            run_id = resp.json()["run_id"]
            await _await_background_run()

    from sqlalchemy import select

    from hub.db.engine import async_session_factory
    from hub.db.models import Run, TurnUsage

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.status == "failed"
        usage = (await db.execute(select(TurnUsage).where(TurnUsage.run_id == run_id))).scalar_one()
        assert usage.status == "unavailable"
        assert usage.total_tokens is None


@pytest.mark.asyncio
async def test_spawn_failure_broadcasts_run_failed_event(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"missing-claude-2": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("missing-claude-2", cli="claude")
    project_id = (await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)).json()[
        "project_id"
    ]
    queue = sse_manager.subscribe(project_id)

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn",
        MagicMock(side_effect=FileNotFoundError("claude was not found in PATH")),
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "missing-claude-2", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            await _await_background_run()

    events = _drain(queue)
    failed = [d for t, d in events if t == "run_failed"]
    # One per attempt — the pre-spawn branch now schedules the retry itself rather than leaving the
    # entry for an unrelated request to drain. Nothing ever spawns, so no run ever starts.
    assert len(failed) == DELIVERY_ATTEMPT_LIMIT
    assert all("not found in PATH" in d["error"] for d in failed)
    assert not [d for t, d in events if t == "run_started"]


def _stoppable_pty(pid=555, exit_code=15):
    """A fake PtySession whose `.read()` blocks until `.terminate()` is called.

    Mirrors `test_second_trigger_while_first_is_running_is_rejected`'s blocking-read
    pattern, but here `.terminate()` itself is what releases the block — simulating a
    stop request actually reaching and killing the real process. `exit_code` defaults
    non-zero (a forced kill rarely exits 0) specifically to prove the stop endpoint's
    "stopped" classification wins over the exit-code-based "failed" classification.
    """
    import threading

    released = threading.Event()

    def _blocking_read(size=4096):
        released.wait()
        return ""

    def _terminate(force=False):
        released.set()

    session = MagicMock()
    session.pid = pid
    session.read.side_effect = _blocking_read
    session.terminate.side_effect = _terminate
    session.wait.return_value = exit_code
    return session


@pytest.mark.asyncio
async def test_stop_endpoint_marks_run_stopped_and_broadcasts_run_stopped(
    app, auth_headers, bind_runner
):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"stoppable-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("stoppable-claude", cli="claude")
    project_id = (await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)).json()[
        "project_id"
    ]
    queue = sse_manager.subscribe(project_id)

    fake_session = _stoppable_pty()
    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            trigger = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "stoppable-claude", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert trigger.status_code == 200
            run_id = trigger.json()["run_id"]

            await _wait_for_active_pty(run_id)

            queued = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "stoppable-claude", "message": "survive the stop"},
                headers=auth_headers,
            )
            assert queued.json()["status"] == "queued"
            queued_entry_id = queued.json()["queue_entry_id"]

            stop = await app.post(
                "/api/v1/projects/proj-test/agent/stoppable-claude/stop", headers=auth_headers
            )
            assert stop.status_code == 200
            assert stop.json()["run_id"] == run_id
            assert stop.json()["status"] == "stopping"

            await _await_background_run()

    fake_session.terminate.assert_called_once_with(force=True)

    from hub.db.engine import async_session_factory
    from hub.db.models import InboundQueueEntry, Run

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.status == "stopped"
        from sqlalchemy import select

        delivered = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.delivered_in_run_id == run_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(delivered) == 1
        assert delivered[0].state == "delivered"
        assert run.exit_code == 15
        queued_entry = (
            await db.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.id == queued_entry_id)
            )
        ).scalar_one()
        # What this test is about: the entry waiting behind the stopped run survived the stop and
        # was picked up by a *different* run. Its final state is not pinned — the successor here
        # inherits the same already-terminated fake session, so it fails, hands the entry back and
        # retries to the cap. That is the retry rule working on an artefact of this fixture, not
        # anything to do with stopping. `delivered_in_run_id` is kept even once abandoned, which is
        # what keeps the assertion below meaningful.
        assert queued_entry.delivered_in_run_id is not None
        assert queued_entry.delivered_in_run_id != run_id
        # The stopped run itself returned nothing: a stop is not a failure.
        assert delivered[0].delivery_attempts == 0

    events = _drain(queue)
    stopped = [d for t, d in events if t == "run_stopped"]
    assert len(stopped) == 1
    assert stopped[0]["run_id"] == run_id
    assert not [
        data
        for event_type, data in events
        if event_type in ("run_completed", "run_failed") and data["run_id"] == run_id
    ]


@pytest.mark.asyncio
async def test_stop_with_no_run_in_progress_returns_404(app, auth_headers):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"idle-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    resp = await app.post("/api/v1/projects/proj-test/agent/idle-claude/stop", headers=auth_headers)
    assert resp.status_code == 404
    assert "no run in progress" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_shutdown_terminates_all_active_runs(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"shutdown-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("shutdown-claude", cli="claude")

    import threading

    released = threading.Event()

    def _blocking_read(size=4096):
        released.wait()
        return ""

    fake_session = MagicMock()
    fake_session.pid = 7777
    fake_session.read.side_effect = _blocking_read
    fake_session.wait.return_value = 0

    terminated_pids = []

    def _fake_terminate_process_tree(pid, force=True):
        terminated_pids.append(pid)
        released.set()

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with patch(
                "hub.api.v1.agent_trigger.terminate_process_tree",
                side_effect=_fake_terminate_process_tree,
            ):
                trigger = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "shutdown-claude", "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert trigger.status_code == 200

                await _wait_for_active_pty(trigger.json()["run_id"])

                count = await agent_trigger.terminate_all_active_runs()
                assert count == 1
                assert terminated_pids == [7777]

                await _await_background_run()

    assert trigger.json()["run_id"] not in agent_trigger._active_ptys


@pytest.mark.asyncio
async def test_terminate_all_active_runs_with_nothing_running_returns_zero(app, auth_headers):
    count = await agent_trigger.terminate_all_active_runs()
    assert count == 0


@pytest.mark.asyncio
async def test_trigger_resolves_claude_proxy_env_at_spawn_time(
    app, auth_headers, bind_runner, monkeypatch
):
    """Task 3.11: the Hub resolves a claude_proxy agent's provider env at spawn time —
    no `eval $(agentweave switch <agent>)` needed first."""
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax-secret")

    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={
            "data": {
                "agents": {
                    "minimax-env-agent": {
                        "runner": "claude_proxy",
                        "env_vars": {
                            "ANTHROPIC_BASE_URL": "https://api.minimax.io/anthropic",
                            "ANTHROPIC_API_KEY_VAR": "MINIMAX_API_KEY",
                        },
                    }
                }
            }
        },
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("minimax-env-agent", cli="claude")

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"sess-env-1"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "minimax-env-agent", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            await _await_background_run()

    assert fake_spawn.call_count == 1
    _, kwargs = fake_spawn.call_args
    spawned_env = kwargs["env"]
    assert spawned_env is not None
    assert spawned_env["ANTHROPIC_API_KEY"] == "sk-minimax-secret"
    assert spawned_env["ANTHROPIC_BASE_URL"] == "https://api.minimax.io/anthropic"


@pytest.mark.asyncio
async def test_trigger_derives_hub_url_from_observed_address_not_configured_port(
    app, auth_headers, bind_runner, monkeypatch
):
    """Task 3.2/3.4/3.7: `HUB_URL` is built from the address the Hub actually observed a
    connection arrive on (`hub.bound_address`), never from `settings.aw_port` — which
    describes configured intent and can silently diverge from where uvicorn really bound
    (CLI flag, env var, or `port=0` all bypass `settings`). Poisoning `aw_port` with an
    obviously-wrong value and asserting it never appears in the spawned env is the
    regression check that no code path still reaches it.
    """
    monkeypatch.delenv("HUB_URL", raising=False)
    from hub.config import settings

    monkeypatch.setattr(settings, "aw_port", 1)

    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"bound-addr-agent": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("bound-addr-agent", cli="claude")

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"sess-bound-1"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with patch("hub.bound_address.get", return_value=("127.0.0.1", 9310)):
                resp = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "bound-addr-agent", "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                await _await_background_run()

    assert fake_spawn.call_count == 1
    _, kwargs = fake_spawn.call_args
    assert kwargs["env"]["HUB_URL"] == "http://127.0.0.1:9310"


@pytest.mark.asyncio
async def test_trigger_prefers_explicit_hub_url_over_observed_address(
    app, auth_headers, bind_runner, monkeypatch
):
    """Task 3.5: an explicit `HUB_URL` in the Hub's own environment is an intentional
    operator override — a reverse proxy or container publishing a different external
    address is a real deployment — and keeps precedence over the observed bound
    address."""
    monkeypatch.setenv("HUB_URL", "http://hub.example.internal:443")

    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"explicit-url-agent": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("explicit-url-agent", cli="claude")

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"sess-explicit-1"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with patch("hub.bound_address.get", return_value=("127.0.0.1", 9310)):
                resp = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "explicit-url-agent", "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                await _await_background_run()

    assert fake_spawn.call_count == 1
    _, kwargs = fake_spawn.call_args
    assert kwargs["env"]["HUB_URL"] == "http://hub.example.internal:443"


@pytest.mark.asyncio
async def test_trigger_directly_refuses_when_no_address_is_known(
    app, auth_headers, bind_runner, monkeypatch
):
    """Task 3.3/3.6: with no explicit `HUB_URL` and no bound address ever observed,
    starting a run is refused with a stated reason instead of guessing — the same
    typed-rejection contract every other `trigger_agent_directly` pre-flight check
    uses, so the scheduler's `except TriggerAgentError` handling (`turn_scheduler.py`)
    covers it without a special case."""
    from hub.conversations import new_conversation
    from hub.db.engine import async_session_factory

    monkeypatch.delenv("HUB_URL", raising=False)

    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"no-addr-agent": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("no-addr-agent", cli="claude")

    async with async_session_factory() as db:
        conversation = new_conversation(
            project_id="proj-test", agent="no-addr-agent", origin="operator"
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

        # The launchability patch its 33 siblings in this file all carry, and this one lacked.
        # Without it the turn fails earlier, on `claude` not being installed, and the assertion
        # below reads "Runner CLI 'claude' was not found in PATH" instead of the address error the
        # test exists to pin. Green on any developer machine, red anywhere else.
        with patch(
            "hub.launchability.shutil.which", return_value="/usr/bin/claude"
        ):  # noqa: SIM117
            with patch("hub.bound_address.get", return_value=None):
                with pytest.raises(agent_trigger.TriggerAgentError) as excinfo:
                    await agent_trigger.trigger_agent_directly(
                        project_id="proj-test",
                        agent="no-addr-agent",
                        message="hi",
                        conversation_id=conversation.id,
                        session=db,
                    )

    assert excinfo.value.status_code == 409
    assert "HUB_URL" in excinfo.value.detail
    # F91. The refusal's own last sentence — "retry once the Hub has served at least one
    # request" — is a description of a condition that clears on its own, which is exactly what
    # `transient` means (see `TriggerAgentError.transient`). Left False, `schedule_agent` charged
    # a delivery attempt for it, and the startup re-drain in `run_reconciliation` runs before any
    # request has been served, so every Hub restart with a run in flight spent one of the
    # operator's three attempts on a condition that had already passed.
    assert excinfo.value.transient is True


@pytest.mark.asyncio
async def test_trigger_reports_its_own_conversation_when_an_older_one_is_scheduled(
    app, auth_headers, bind_runner
):
    """The scheduler picks the conversation of the oldest eligible entry across the whole
    agent queue, which may not be the one this request just appended to. When that happens
    the caller's input is still queued, and the response must say so — reporting the other
    conversation's run as if it were this request's would tell the operator their message
    is running when it is not (`agent-conversation-workspace`: "the response contains the
    new conversation_id whether its status is running or queued").

    `_execute_run` is patched out: this is a scheduling/reporting question, so the prompt
    the Hub built is asserted on directly rather than through a spawned process.
    """
    from hub.conversations import new_conversation
    from hub.db.engine import async_session_factory
    from hub.inbound_queue import new_entry

    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"backlog-claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("backlog-claude", cli="claude")

    # A leftover queued entry in an older, still-open conversation — e.g. a peer agent's
    # message that arrived while this agent was busy, or one left by an interrupted run.
    async with async_session_factory() as db:
        stale_conversation = new_conversation(
            project_id="proj-test", agent="backlog-claude", origin="operator"
        )
        db.add(stale_conversation)
        await db.flush()
        stale_conversation_id = stale_conversation.id
        db.add(
            new_entry(
                project_id="proj-test",
                agent="backlog-claude",
                origin_type="operator",
                content="STALE BACKLOG",
                hop_depth=0,
                conversation_id=stale_conversation_id,
            )
        )
        await db.commit()

    executed = AsyncMock()
    with patch("hub.api.v1.agent_trigger._execute_run", executed):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "backlog-claude", "message": "FRESH INPUT"},
                headers=auth_headers,
            )

    assert resp.status_code == 200
    body = resp.json()
    # The response describes the input this request accepted, not the older run.
    assert body["conversation_id"] != stale_conversation_id
    assert body["status"] == "queued"
    assert body["run_id"] is None
    assert "older conversation" in body["waiting_reason"]

    # The older conversation's turn is what actually started, and it carries only its own
    # entry — the fresh input is not silently folded into another conversation's prompt.
    assert executed.call_args.kwargs["prompt"].count("STALE BACKLOG") == 1
    assert "FRESH INPUT" not in executed.call_args.kwargs["prompt"]

    from sqlalchemy import select

    from hub.db.models import InboundQueueEntry

    async with async_session_factory() as db:
        states = {
            row.content: (row.state, row.conversation_id)
            for row in (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == "backlog-claude")
                )
            )
            .scalars()
            .all()
        }
    assert states["STALE BACKLOG"][0] == "delivered"
    assert states["FRESH INPUT"] == ("queued", body["conversation_id"])


@pytest.mark.asyncio
async def test_codex_defaults_to_app_server_with_no_flags_at_all(app, auth_headers, bind_runner):
    """A codex runner carrying no flags routes through `run_turn`, not `codex exec`.

    The Add-agent dialog creates runners with no flags, so this is the shape every codex agent
    an operator actually creates has. Under the previous opt-in it silently got the exec
    transport, whose MCP tool calls are always denied.
    """
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"default-codex": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("default-codex", cli="codex")

    fake_run_turn = _fake_run_turn()
    with patch("hub.api.v1.agent_trigger.codex_run_turn", fake_run_turn):  # noqa: SIM117
        with patch("hub.api.v1.agent_trigger.PipeSession.spawn") as pipe_spawn:
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
                resp = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "default-codex", "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                await _await_background_run()

    pipe_spawn.assert_not_called()
    fake_run_turn.assert_called_once()


@pytest.mark.asyncio
async def test_codex_exec_argv_never_carries_a_transport_sentinel(app, auth_headers):
    """Neither sentinel is a real `codex` argument, so neither may reach argv."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"sentinel-codex": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await _bind_codex_exec_runner(app, auth_headers)("sentinel-codex")

    fake_spawn = _fake_pty(
        [
            '{"type":"thread.started","thread_id":"thread-sentinel"}\n',
            '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n',
        ]
    )
    with patch("hub.api.v1.agent_trigger.PipeSession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "sentinel-codex", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            await _await_background_run()

    command = fake_spawn.call_args.args[0]
    assert "--no-app-server" not in command
    assert "--app-server" not in command


@pytest.mark.asyncio
async def test_codex_app_server_opt_in_flag_selects_run_turn_not_exec(app, auth_headers):
    """Task 2.8: `--app-server` in a bound codex Runner's flags routes the run through
    `codex_appserver.run_turn` instead of `PipeSession`/`codex exec` — and never leaks into
    a `codex exec` argv, since no exec ever happens on this path."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"appserver-codex": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await _bind_codex_app_server_runner(app, auth_headers)("appserver-codex")

    fake_run_turn = _fake_run_turn()
    with patch("hub.api.v1.agent_trigger.codex_run_turn", fake_run_turn):  # noqa: SIM117
        with patch("hub.api.v1.agent_trigger.PipeSession.spawn") as pipe_spawn:
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
                resp = await app.post(
                    "/api/v1/projects/proj-test/agent/trigger",
                    json={"agent": "appserver-codex", "message": "hi", "session_mode": "new"},
                    headers=auth_headers,
                )
                assert resp.status_code == 200
                run_id = resp.json()["run_id"]
                await _await_background_run()

    pipe_spawn.assert_not_called()
    fake_run_turn.assert_called_once()
    assert fake_run_turn.call_args.kwargs["cli"] == "codex"

    from hub.db.engine import async_session_factory
    from hub.db.models import Run

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.status == "completed"
        assert run.session_id == "thread-appserver-1"


@pytest.mark.asyncio
async def test_codex_app_server_records_output_events_and_usage(app, auth_headers):
    """Task 2.5/2.8: events `on_event`/`on_usage`/`on_accounting` deliver during a turn are
    recorded the same way the `exec` path's parsed lines are — `AgentOutput` and
    `TurnUsage` rows indistinguishable from that path's, per implications.md §4's stated
    goal."""
    from hub.runner_events import AccountingSample, ContextUsageSample, text_event

    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"appserver-output": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await _bind_codex_app_server_runner(app, auth_headers)("appserver-output")

    fake_run_turn = _fake_run_turn(
        events=[text_event("hello from app-server")],
        usage=ContextUsageSample(
            status="measured", source="codex_appserver", context_tokens=10, limit_tokens=100
        ),
        accounting=AccountingSample(
            source="codex_appserver", input_tokens=7, output_tokens=3, total_tokens=10
        ),
    )
    with patch("hub.api.v1.agent_trigger.codex_run_turn", fake_run_turn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "appserver-output", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            run_id = resp.json()["run_id"]
            await _await_background_run()

    output_resp = await app.get(
        "/api/v1/projects/proj-test/agents/appserver-output/output", headers=auth_headers
    )
    assert output_resp.status_code == 200
    rows = output_resp.json()
    assert any(row["content"] == "hello from app-server" for row in rows)
    assert all(row["session_id"] == "thread-appserver-1" for row in rows if row["run_id"] == run_id)

    from sqlalchemy import select

    from hub.db.engine import async_session_factory
    from hub.db.models import TurnUsage

    async with async_session_factory() as db:
        usage = (await db.execute(select(TurnUsage).where(TurnUsage.run_id == run_id))).scalar_one()
        assert usage.input_tokens == 7
        assert usage.output_tokens == 3
        assert usage.total_tokens == 10


@pytest.mark.asyncio
async def test_codex_app_server_resume_passes_known_session_id_as_resume_thread_id(
    app, auth_headers
):
    """Task 2.6: resuming a conversation whose `provider_session_id` was recorded by
    either transport passes straight through as `run_turn`'s `resume_thread_id` — no
    translation layer, matching design.md Decision 1a's verified finding."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"appserver-resume": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await _bind_codex_app_server_runner(app, auth_headers)("appserver-resume")

    fake_run_turn = _fake_run_turn(thread_id="thread-appserver-1")
    with patch("hub.api.v1.agent_trigger.codex_run_turn", fake_run_turn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
            first = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "appserver-resume", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert first.status_code == 200
            await _await_background_run()

            second = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={
                    "agent": "appserver-resume",
                    "message": "again",
                    "session_mode": "resume",
                    "session_id": "thread-appserver-1",
                },
                headers=auth_headers,
            )
            assert second.status_code == 200
            await _await_background_run()

    assert fake_run_turn.call_count == 2
    assert fake_run_turn.call_args_list[0].kwargs["resume_thread_id"] is None
    assert fake_run_turn.call_args_list[1].kwargs["resume_thread_id"] == "thread-appserver-1"


@pytest.mark.asyncio
async def test_codex_app_server_binding_conflict_fails_run(app, auth_headers):
    """Mirrors the `exec` path's `conversation_binding_conflict` handling: a thread id that
    disagrees with the conversation's already-bound `provider_session_id` fails the run
    rather than silently overwriting which session the conversation is bound to."""
    from hub.conversations import new_conversation
    from hub.db.engine import async_session_factory

    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"appserver-conflict": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await _bind_codex_app_server_runner(app, auth_headers)("appserver-conflict")

    async with async_session_factory() as db:
        conversation = new_conversation(
            project_id="proj-test", agent="appserver-conflict", origin="operator"
        )
        conversation.provider_session_id = "thread-already-bound"
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        conversation_id = conversation.id

    fake_run_turn = _fake_run_turn(thread_id="thread-different")
    with patch("hub.api.v1.agent_trigger.codex_run_turn", fake_run_turn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={
                    "agent": "appserver-conflict",
                    "message": "hi",
                    "conversation_id": conversation_id,
                    "session_mode": "new",
                },
                headers=auth_headers,
            )
            assert resp.status_code == 200
            run_id = resp.json()["run_id"]
            await _await_background_run()

    from hub.db.models import Run

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.status == "failed"
        assert "binding conflict" in run.error.lower()


@pytest.mark.asyncio
async def test_codex_app_server_spawn_failure_fails_run_and_returns_queue_entries(
    app, auth_headers
):
    """Mirrors the `exec` path's `FileNotFoundError` handling (`test_...` above for
    claude/codex exec spawn failures): a codex binary missing at app-server spawn time
    fails the run with a stated reason and returns any delivered queue entries to
    "queued" rather than stranding them against a run that never started."""
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"appserver-missing": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await _bind_codex_app_server_runner(app, auth_headers)("appserver-missing")

    failing_run_turn = AsyncMock(side_effect=FileNotFoundError("codex not found in PATH"))
    with patch("hub.api.v1.agent_trigger.codex_run_turn", failing_run_turn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "appserver-missing", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            run_id = resp.json()["run_id"]
            await _await_background_run()

    from hub.db.engine import async_session_factory
    from hub.db.models import Run

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.status == "failed"
        assert "not found in PATH" in run.error


@pytest.mark.asyncio
async def test_codex_app_server_stop_signals_should_interrupt(app, auth_headers):
    """Task 2.7's remaining piece: the stop endpoint has no process handle for an
    app-server run, so it must reach `run_turn` purely through `_stop_requested` —
    `should_interrupt` here polls that exact set, mirroring `_stoppable_pty`'s
    terminate-releases-the-block pattern but through the poll-based interrupt contract
    `run_turn` actually implements instead of a direct process kill."""
    from hub.codex_appserver import TurnOutcome

    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"appserver-stoppable": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await _bind_codex_app_server_runner(app, auth_headers)("appserver-stoppable")

    async def _run_until_interrupted(**kwargs):
        should_interrupt = kwargs["should_interrupt"]
        while not should_interrupt():
            await asyncio.sleep(0.01)
        return TurnOutcome(thread_id="thread-stop-1", status="interrupted")

    fake_run_turn = AsyncMock(side_effect=_run_until_interrupted)
    with patch("hub.api.v1.agent_trigger.codex_run_turn", fake_run_turn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
            trigger = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "appserver-stoppable", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert trigger.status_code == 200
            run_id = trigger.json()["run_id"]

            await _wait_for_active_app_server_run(run_id)

            stop = await app.post(
                "/api/v1/projects/proj-test/agent/appserver-stoppable/stop", headers=auth_headers
            )
            assert stop.status_code == 200
            assert stop.json()["run_id"] == run_id
            assert stop.json()["status"] == "stopping"

            await _await_background_run()

    from hub.db.engine import async_session_factory
    from hub.db.models import Run

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.status == "stopped"


# test_trigger_unsupported_runner_accumulates_queue (kimi-agent, runner="kimi") was
# removed here: since runner-agent-charter-separation phase 1, Runner.cli is
# schema-constrained to claude|codex (POST /api/v1/projects/proj-test/runners rejects anything else, see
# test_runners_api.py::test_create_runner_rejects_unsupported_cli) — there is no longer
# any way, through the real API, to bind an agent to a "kimi" runner and reach the
# "unimplemented runner" 501 path this test exercised. The equivalent "cannot launch,
# queues with a stated reason" behavior for an agent with no execution capability
# configured is covered by test_unbound_agent_accumulates_queue_with_visible_reason above.


@pytest.mark.asyncio
async def test_a_batch_naming_a_review_and_work_is_refused(app, auth_headers, bind_runner):
    """1.5 (`every-run-knows-its-task`, D3, F66): defence in depth for a caller that hand-builds
    `queue_entry_ids` — the scheduler's own narrowing of `selected` keeps this from being
    assembled through the ordinary queue path (`test_turn_scheduler.py`), but a direct call
    naming both is still refused rather than delivered.
    """
    from sqlalchemy import select

    from hub.db.engine import async_session_factory
    from hub.db.models import InboundQueueEntry, Run, Task

    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"mixed-batch": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner("mixed-batch", cli="claude")

    async with async_session_factory() as session:
        from hub.api.v1.agent_trigger import TriggerAgentError, trigger_agent_directly
        from hub.conversations import new_conversation

        conversation = new_conversation(
            project_id="proj-test", agent="mixed-batch", origin="operator"
        )
        session.add(conversation)
        session.add(
            Task(id="task-review", project_id="proj-test", title="Reviewed", status="completed")
        )
        session.add(
            Task(id="task-work", project_id="proj-test", title="Worked on", status="pending")
        )
        session.add(
            InboundQueueEntry(
                id="entry-review",
                project_id="proj-test",
                agent="mixed-batch",
                origin_type="operator",
                content="review",
                hop_depth=0,
                state="queued",
                review_task_id="task-review",
                conversation_id=conversation.id,
            )
        )
        session.add(
            InboundQueueEntry(
                id="entry-work",
                project_id="proj-test",
                agent="mixed-batch",
                origin_type="operator",
                content="work",
                hop_depth=0,
                state="queued",
                task_id="task-work",
                conversation_id=conversation.id,
            )
        )
        await session.commit()

        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(TriggerAgentError) as excinfo:
                await trigger_agent_directly(
                    project_id="proj-test",
                    agent="mixed-batch",
                    message="review and work",
                    conversation_id=conversation.id,
                    session=session,
                    queue_entry_ids=["entry-review", "entry-work"],
                )

    assert "task-review" in excinfo.value.detail
    assert "task-work" in excinfo.value.detail
    assert excinfo.value.status_code == 409

    async with async_session_factory() as session:
        assert (await session.execute(select(Run.id))).first() is None
        entries = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(
                        InboundQueueEntry.id.in_(["entry-review", "entry-work"])
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {entry.state for entry in entries} == {"queued"}
        assert not any(entry.delivered_in_run_id for entry in entries)
