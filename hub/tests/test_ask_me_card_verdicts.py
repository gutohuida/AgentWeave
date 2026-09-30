"""An "Ask me" card from an RPC runner carries what "Workspace only" would decide
(`an-ask-me-card-says-what-workspace-only-would-decide`, design D1 and D5).

Codex and Copilot ask the operator through one function, `_await_operator_permission`, which writes
the row the card reads. Each runner's own Workspace-only check produces the advice, so the advice and
the answer that posture enforces cannot disagree. The turns are entered through
`POST /agent/trigger` with the runner's `run_turn` replaced by a fake that calls the real
`request_approval` the trigger handed it, so the wiring between the two is what is tested.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

import hub.codex_appserver as codex_appserver
from hub.db.engine import async_session_factory
from hub.db.models import PermissionRequest

from ._background_runs import await_background_runs


@pytest.fixture(autouse=True)
def _answer_nobody_quickly(monkeypatch):
    """The operator never answers here; the wait runs out at once and the row stays to be read."""
    monkeypatch.setattr("hub.api.v1.agent_trigger._codex_decision_timeout", lambda env: 0.1)
    monkeypatch.setattr("hub.api.v1.agent_trigger.CODEX_OPERATOR_POLL_SECONDS", 0.02)


async def _cards():
    async with async_session_factory() as db:
        rows = (await db.execute(select(PermissionRequest))).scalars().all()
    return {row.tool_input.get("cwd") or row.tool_name: row for row in rows}


def test_codex_verdict_is_the_workspace_check(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "sub").mkdir(parents=True)
    command = codex_appserver.COMMAND_APPROVAL_METHOD
    file_change = codex_appserver.FILE_CHANGE_APPROVAL_METHOD
    cases = [
        (command, {"cwd": str(workspace / "sub")}),
        (command, {"cwd": str(tmp_path)}),
        (command, {}),
        (file_change, {"grantRoot": str(workspace)}),
        (file_change, {"grantRoot": str(tmp_path)}),
        (file_change, {}),
    ]
    for method, params in cases:
        subject = codex_appserver.approval_subject(method, params)
        verdict = codex_appserver.workspace_verdict(subject, str(workspace))
        enforced = codex_appserver.decide_approval(
            method,
            params,
            yolo=False,
            own_server_name="agentweave",
            posture="workspace",
            workspace=str(workspace),
        )
        assert verdict["allow"] == (enforced == {"decision": "accept"}), (method, params)
        assert "checked by working directory only" in verdict["reason"]
        assert "read, not sandboxed" not in verdict["reason"]


@pytest.mark.asyncio
async def test_a_codex_card_stores_the_verdict(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"askme-codex": {"runner": "codex"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("askme-codex", cli="codex")
    outside = None

    async def _run(**kwargs):
        nonlocal outside
        # At the drive root: `tmp_path` holds the test project's own workspace.
        outside = str(Path(Path(kwargs["cwd"]).anchor) / "aw-not-any-workspace")
        method = codex_appserver.COMMAND_APPROVAL_METHOD
        await kwargs["request_approval"](method, {"cwd": kwargs["cwd"], "command": "ls"})
        await kwargs["request_approval"](method, {"cwd": outside, "command": "ls"})
        return codex_appserver.TurnOutcome(thread_id="t-1", status="completed", error=None)

    with patch("hub.api.v1.agent_trigger.codex_run_turn", AsyncMock(side_effect=_run)):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "askme-codex", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert response.status_code == 200, response.text
            await await_background_runs()

    cards = await _cards()
    assert cards[outside].workspace_verdict["allow"] is False
    [inside] = [row for key, row in cards.items() if key != outside]
    assert inside.workspace_verdict["allow"] is True
    assert "checked by working directory only" in inside.workspace_verdict["reason"]


@pytest.mark.asyncio
async def test_a_copilot_card_stores_the_verdict_its_turn_worked_out(
    app, auth_headers, bind_runner, tmp_path, monkeypatch
):
    from hub.copilot_acp import TurnOutcome

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    exe = tmp_path / "copilot.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr("hub.copilot_probe.resolve_copilot_executable", lambda override: exe)
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"askme-copilot": {"runner": "copilot"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("askme-copilot", cli="copilot")
    verdict = {"allow": False, "reason": "writes outside your workspace"}

    async def _run(**kwargs):
        subject = {
            "tool_name": "Edit file",
            "tool_input": {"path": "C:/elsewhere/a.txt"},
            "workspace_verdict": verdict,
        }
        await kwargs["request_approval"]("session/request_permission", subject)
        return TurnOutcome(session_id="sess-1", status="completed")

    with patch("hub.api.v1.agent_trigger.copilot_run_turn", AsyncMock(side_effect=_run)):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "askme-copilot", "message": "hi", "session_mode": "new"},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        await await_background_runs()

    assert (await _cards())["Edit file"].workspace_verdict == verdict
