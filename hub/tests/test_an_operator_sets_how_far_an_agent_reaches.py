"""`an-operator-sets-how-far-an-agent-reaches` (reach-1019): the acceptance test, at the seam.

Each case goes through the real routes -- the project's settings, the agent's PATCH, the trigger --
and then judges a call with exactly what the run received: the Copilot run's posture and
environment handed to `copilot_acp.decide_permission`, and the Claude run's spawn environment
installed as the spawned MCP server's own (`mcp_server._decide` with its defaults). Written before
the build, and failing on it: the settings route refused both fields, and a Copilot spec turn under
Full access was judged as Workspace only.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from hub import mcp_server
from hub.copilot_acp import TurnOutcome, decide_permission
from hub.model_catalog import FULL_ACCESS_PERMISSION_MODE, WORKSPACE_PERMISSION_MODE
from hub.runner_events import text_event
from tests.test_agent_trigger import _await_background_run, _fake_pty

from ._background_runs import await_background_runs

PROJECT = "proj-test"
HUB_URL = "http://127.0.0.1:8010"


@pytest.fixture(autouse=True)
def _copilot_installed(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    exe = home / "copilot.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr("hub.copilot_probe.resolve_copilot_executable", lambda override: exe)


def _fake_copilot_turn():
    # A session id of its own per run: each `_copilot_run` starts a new conversation.
    session_id = f"sess-{uuid.uuid4().hex[:8]}"

    async def _run(**kwargs):
        await kwargs["on_session"](session_id)
        await kwargs["on_event"](text_event("hello from copilot"))
        return TurnOutcome(session_id=session_id, status="completed")

    return AsyncMock(side_effect=_run)


async def _agents(app, auth_headers, bind_runner, **clis: str) -> None:
    """One sync naming every agent (a sync replaces the roster it describes), then a runner each."""
    sync = await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {name: {"runner": cli} for name, cli in clis.items()}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    for name, cli in clis.items():
        await bind_runner(name, cli=cli)


async def _settings(app, auth_headers, **body):
    resp = await app.put(f"/api/v1/projects/{PROJECT}/settings", json=body, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _patch(app, auth_headers, name: str, **body):
    resp = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/{name}", json=body, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _copilot_run(app, auth_headers, name: str) -> dict:
    """Trigger a Copilot agent through the route; what its `run_turn` was given."""
    fake = _fake_copilot_turn()
    with patch("hub.copilot_acp.run_turn", fake):
        resp = await app.post(
            f"/api/v1/projects/{PROJECT}/agent/trigger",
            json={"agent": name, "message": "hi", "session_mode": "new"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        await await_background_runs()
    assert fake.await_count == 1
    return fake.await_args.kwargs


async def _claude_run(app, auth_headers, name: str):
    """Trigger a Claude agent through the route; its argv and environment."""
    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                f"/api/v1/projects/{PROJECT}/agent/trigger",
                json={"agent": name, "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200, resp.text
            await _await_background_run()
    return fake_spawn.call_args.args[0], fake_spawn.call_args.kwargs["env"]


def _read(path: str, call_id: str = "call_1") -> dict:
    return {
        "sessionId": "sess-1",
        "toolCall": {
            "toolCallId": call_id,
            "title": "probe",
            "kind": "read",
            "status": "pending",
            "rawInput": {"path": path},
        },
        "options": [
            {"optionId": "allow_once", "kind": "allow_once", "name": "Allow once"},
            {"optionId": "reject_once", "kind": "reject_once", "name": "Deny"},
        ],
    }


def _told(run: dict) -> str:
    """Every context text the Copilot run was handed."""
    return "\n".join(
        str(run.get(name) or "")
        for name in ("per_turn_context", "tool_surface_context", "stable_context", "prompt")
    )


def _copilot_decides(run: dict, params: dict, *, spec_turn: bool = False) -> str:
    return decide_permission(
        params,
        posture=run["permission_mode"],
        workspace=run["workspace"],
        hub_url=HUB_URL,
        calls={},
        spec_turn=spec_turn,
        grants=(run.get("env") or {}).get("AW_REACH_GRANTS"),
    )["outcome"]


def _claude_decides(monkeypatch, env: dict, tool: str, tool_input: dict) -> bool:
    """As the run's spawned MCP server decides: from its own environment, nothing passed."""
    for name in ("AW_WORKSPACE_DIR", "HUB_URL", "AW_REACH_GRANTS"):
        if name in env:
            monkeypatch.setenv(name, env[name])
        else:
            monkeypatch.delenv(name, raising=False)
    return bool(mcp_server._decide(tool, tool_input)["allow"])


@pytest.mark.asyncio
async def test_allow_all_at_project_level_reaches_copilot_a_spec_turn_and_claude(
    app, auth_headers, bind_runner, tmp_path_factory
):
    """reach-D2: one project setting, every agent -- Copilot and a spec turn included."""
    outside = str(tmp_path_factory.mktemp("elsewhere") / "notes.txt")
    await _agents(app, auth_headers, bind_runner, **{"reach-cop": "copilot", "reach-cla": "claude"})

    saved = await _settings(app, auth_headers, default_permission_mode=FULL_ACCESS_PERMISSION_MODE)
    assert saved["default_permission_mode"] == FULL_ACCESS_PERMISSION_MODE

    run = await _copilot_run(app, auth_headers, "reach-cop")
    assert run["permission_mode"] == FULL_ACCESS_PERMISSION_MODE
    # And the agent is told so: told "files outside it are refused", a Copilot agent refused itself
    # the work without trying (drive 2026-10-19).
    assert "posture is Full access" in _told(run)
    assert _copilot_decides(run, _read(outside)) == "ALLOW"
    # Supersedes ghcp-a-spec-turn-full-access: a spec turn is no longer judged as Workspace only.
    assert _copilot_decides(run, _read(outside), spec_turn=True) == "ALLOW"

    command, _env = await _claude_run(app, auth_headers, "reach-cla")
    assert command[command.index("--permission-mode") + 1] == FULL_ACCESS_PERMISSION_MODE

    # The roster says what the next run gets.
    roster = (await app.get(f"/api/v1/projects/{PROJECT}/agents", headers=auth_headers)).json()
    row = next(a for a in roster if a["name"] == "reach-cop")
    assert row["permission_mode_at_rest"] == FULL_ACCESS_PERMISSION_MODE

    # An agent's own default overrides the project's, narrowing it.
    await _patch(app, auth_headers, "reach-cop", default_permission_mode=WORKSPACE_PERMISSION_MODE)
    narrowed = await _copilot_run(app, auth_headers, "reach-cop")
    assert narrowed["permission_mode"] == WORKSPACE_PERMISSION_MODE
    assert _copilot_decides(narrowed, _read(outside)) == "REJECT"


@pytest.mark.asyncio
async def test_the_middle_setting_allows_what_is_granted_and_refuses_the_rest(
    app, auth_headers, bind_runner, tmp_path_factory, monkeypatch
):
    """reach-D3: Workspace only plus granted roots and hosts, set on the project, overridden by
    an agent."""
    writable = tmp_path_factory.mktemp("granted-rw")
    readable = tmp_path_factory.mktemp("granted-ro")
    ungranted = tmp_path_factory.mktemp("not-granted")
    await _agents(app, auth_headers, bind_runner, **{"reach-mid": "claude", "reach-mcp": "copilot"})

    grants = {
        "roots": [
            {"path": str(writable), "access": "readwrite"},
            {"path": str(readable), "access": "read"},
        ],
        "hosts": ["localhost:*"],
    }
    saved = await _settings(
        app,
        auth_headers,
        default_permission_mode=WORKSPACE_PERMISSION_MODE,
        reach_grants=grants,
    )
    assert saved["reach_grants"]["hosts"] == ["localhost:*"]

    _command, env = await _claude_run(app, auth_headers, "reach-mid")
    assert json.loads(env["AW_REACH_GRANTS"])["roots"]
    w = os.path.join(str(writable), "out.txt")
    r = os.path.join(str(readable), "in.txt")
    u = os.path.join(str(ungranted), "x.txt")
    assert _claude_decides(monkeypatch, env, "Write", {"file_path": w, "content": "x"})
    assert _claude_decides(monkeypatch, env, "Bash", {"command": f"cp a.txt '{w}'"})
    assert _claude_decides(monkeypatch, env, "Read", {"file_path": r})
    assert _claude_decides(monkeypatch, env, "Bash", {"command": "curl http://localhost:5173/"})
    # A shell word cannot say whether it reads or writes, so a read root is not enough for it.
    assert not _claude_decides(monkeypatch, env, "Bash", {"command": f"cp a.txt '{r}'"})
    assert not _claude_decides(monkeypatch, env, "Write", {"file_path": r, "content": "x"})
    assert not _claude_decides(monkeypatch, env, "Read", {"file_path": u})
    assert not _claude_decides(monkeypatch, env, "Bash", {"command": "curl https://example.com/"})

    # The same grants reach a Copilot run's in-process judge.
    copilot = await _copilot_run(app, auth_headers, "reach-mcp")
    assert str(writable) in _told(copilot) and "localhost:*" in _told(copilot)
    assert _copilot_decides(copilot, _read(r)) == "ALLOW"
    assert _copilot_decides(copilot, _read(u)) == "REJECT"

    # An agent's own grants replace the project's whole: empty narrows it back to the workspace.
    await _patch(app, auth_headers, "reach-mid", reach_grants={"roots": [], "hosts": []})
    _command, env = await _claude_run(app, auth_headers, "reach-mid")
    assert not _claude_decides(monkeypatch, env, "Write", {"file_path": w, "content": "x"})
    # And null inherits the project's again.
    await _patch(app, auth_headers, "reach-mid", reach_grants=None)
    _command, env = await _claude_run(app, auth_headers, "reach-mid")
    assert _claude_decides(monkeypatch, env, "Write", {"file_path": w, "content": "x"})


@pytest.mark.asyncio
async def test_a_grant_that_is_not_an_absolute_root_is_refused(app, auth_headers):
    for bad in (
        {"roots": [{"path": "relative/dir", "access": "readwrite"}], "hosts": []},
        {"roots": [{"path": "C:/x" if os.name == "nt" else "/x", "access": "write"}], "hosts": []},
        {"roots": [], "hosts": ["http://localhost"]},
    ):
        resp = await app.put(
            f"/api/v1/projects/{PROJECT}/settings",
            json={"reach_grants": bad},
            headers=auth_headers,
        )
        assert resp.status_code == 422, (bad, resp.text)


@pytest.mark.asyncio
async def test_a_refused_agent_grant_names_the_field_and_the_bad_value(
    app, auth_headers, bind_runner
):
    """F795: the agent route's 400 detail was pydantic's raw dump with a docs URL; the page could
    show nothing of it. It is now the `field: message` sentence the project's Reach group shows."""
    await _agents(app, auth_headers, bind_runner, **{"reach-bad": "claude"})
    cases = (
        (
            {"roots": [{"path": "rel", "access": "read"}], "hosts": []},
            "reach_grants.roots.0.path: a granted root is an absolute path",
            "'rel'",
        ),
        (
            {"roots": [], "hosts": ["http://bad host"]},
            "reach_grants.hosts: a granted host is host, host:port, host:* or *.domain",
            "'http://bad host'",
        ),
    )
    for bad, field_and_words, value in cases:
        resp = await app.patch(
            f"/api/v1/projects/{PROJECT}/agents/reach-bad",
            json={"reach_grants": bad},
            headers=auth_headers,
        )
        assert resp.status_code == 400, resp.text
        detail = resp.json()["detail"]
        assert field_and_words in detail and value in detail, detail
        assert "errors.pydantic.dev" not in detail and "validation error" not in detail, detail


def test_the_judge_restates_the_hubs_host_pattern():
    """`mcp_server` imports only the stdlib, so it restates `reach.GRANT_HOST_RE`."""
    from hub import reach

    assert mcp_server._GRANT_HOST_RE.pattern == reach.GRANT_HOST_RE.pattern


@pytest.mark.parametrize(
    "hosts,command,allowed",
    [
        (["localhost:5173"], "curl http://localhost:5173/x", True),
        (["localhost:5173"], "curl http://localhost:8000/x", False),
        (["registry.npmjs.org"], "curl https://registry.npmjs.org/react", True),
        (["*.npmjs.org"], "curl https://registry.npmjs.org/react", True),
        (["*.npmjs.org"], "curl https://npmjs.org.evil.com/", False),
        (["localhost:*"], "curl localhost:3000/health", True),
        ([], "curl http://localhost:5173/", False),
    ],
)
def test_a_granted_host_is_matched_by_name_and_port(tmp_path, hosts, command, allowed):
    grants = json.dumps({"roots": [], "hosts": hosts})
    decided = mcp_server._decide(
        "Bash", {"command": command}, workspace=str(tmp_path), hub_url=HUB_URL, grants=grants
    )
    assert bool(decided["allow"]) is allowed, decided


def test_grants_render_tokens_and_nothing_granted_writes_no_variable(tmp_path):
    import tempfile

    from hub.reach import effective_grants, grants_env_value

    tokens = {
        "roots": [
            {"path": "{temp}", "access": "read"},
            {"path": "{project}", "access": "readwrite"},
        ]
    }
    rendered = json.loads(grants_env_value(tokens, project_root=str(tmp_path)))
    assert rendered["roots"] == [
        {"path": tempfile.gettempdir(), "access": "read"},
        {"path": str(tmp_path), "access": "readwrite"},
    ]
    assert grants_env_value({"roots": [], "hosts": []}, project_root=str(tmp_path)) is None
    assert grants_env_value(None, project_root=str(tmp_path)) is None
    project = {"roots": [], "hosts": ["localhost"]}
    assert effective_grants(project, None) == project
    assert effective_grants(project, {"roots": [], "hosts": []}) == {"roots": [], "hosts": []}
