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
from unittest.mock import MagicMock, patch

import pytest

import hub.api.v1.agent_trigger as agent_trigger
from hub import worktrees
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


def _fake_pty(lines, exit_code=0, pid=4242):
    """Build a mock PtySession.spawn() replacement streaming `lines` then EOF."""
    session = MagicMock()
    session.pid = pid
    session.read.side_effect = [*lines, ""]
    session.wait.return_value = exit_code
    return MagicMock(return_value=session)


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
    # Nested, not parenthesized multi-context `with`: this suite's linter targets
    # Python 3.8 (see test_hub_commands.py's identical comment) — parenthesized
    # multi-context managers are 3.9+ only.
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
    assert "Live Context Project" in context
    assert "## Charter: Live Charter" in context
    assert "LIVE_CHARTER_MARKER" in context


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
async def test_writing_agent_is_not_spawned_when_isolation_cannot_be_prepared(
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
    assert response.json()["status"] == "queued"
    assert "isolated worktree" in response.json()["waiting_reason"].lower()


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
    # The Hub's own environment must be inherited, not replaced, by adding these keys.
    assert "PATH" in spawned_env or "Path" in spawned_env

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
async def test_codex_trigger_uses_headless_pipe_instead_of_pty(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"trigger-codex": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("trigger-codex", cli="codex")

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
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn), patch(
        "hub.launchability.shutil.which", return_value="/usr/bin/claude"
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

        returned = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(
                        InboundQueueEntry.delivered_in_run_id.is_(None),
                        InboundQueueEntry.agent == "missing-claude",
                        InboundQueueEntry.state == "queued",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert [entry.content for entry in returned] == ["hi"]


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
    assert len(failed) == 1
    assert failed[0]["exit_code"] == 1
    assert not [d for t, d in events if t == "run_completed"]


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
    assert len(failed) == 1
    assert "not found in PATH" in failed[0]["error"]
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
        assert queued_entry.state == "delivered"
        assert queued_entry.delivered_in_run_id != run_id

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
        conversation = new_conversation(project_id="proj-test", agent="no-addr-agent")
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

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


# test_trigger_unsupported_runner_accumulates_queue (kimi-agent, runner="kimi") was
# removed here: since runner-agent-charter-separation phase 1, Runner.cli is
# schema-constrained to claude|codex (POST /api/v1/projects/proj-test/runners rejects anything else, see
# test_runners_api.py::test_create_runner_rejects_unsupported_cli) — there is no longer
# any way, through the real API, to bind an agent to a "kimi" runner and reach the
# "unimplemented runner" 501 path this test exercised. The equivalent "cannot launch,
# queues with a stated reason" behavior for an agent with no execution capability
# configured is covered by test_unbound_agent_accumulates_queue_with_visible_reason above.
