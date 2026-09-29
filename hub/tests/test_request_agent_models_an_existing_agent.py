"""`request_agent` models a new agent on an existing open agent of this project (F378).

The route used to read its templates from `project_sessions`, a table with no writer since the
watchdog era — every call answered 400, live and in every test but one, which seeded the table by
hand. `openspec/changes/request-agent-models-the-new-agent-on-one-the-operator-made`.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
from hub.agent_auth import hash_run_token
from hub.api.v1.agent_trigger import (
    QUESTION_WAIT_DEFAULT,
    QUESTION_WAIT_ENV,
    effective_question_wait,
)
from hub.api.v1.agents import FULL_ACCESS_PERMISSION_MODE
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Charter, Conversation, Run
from hub.turn_scheduler import ScheduleResult, schedule_agent

from ._background_runs import await_background_runs as _await_background_run
from .test_agent_trigger import _fake_pty

REQUEST_URL = "/api/v1/agent-actions/agents/request"


@pytest.fixture(autouse=True)
def _request_starts_no_process():
    """`schedule_agent` made inert for every request in this file.

    A requested agent now inherits its template's runner, so the route's `schedule_agent` would
    really start its first turn -- a real `claude` process wherever one is on PATH, and a refused
    spawn that leaves the entry queued where one is not. What these tests assert is what the
    route *wrote and answered*, which is before any turn starts. `_capture_build_command` below
    restores the real scheduler for the one turn it measures.
    """
    with patch(
        "hub.turn_scheduler.schedule_agent",
        AsyncMock(return_value=ScheduleResult(waiting_reason=None, terminal_failure=False)),
    ):
        yield


async def _capture_build_command(app, auth_headers, agent, *, session_suffix):
    """Trigger `agent` once, with the real scheduler, and return *its* `build_command` kwargs.

    Not the shared `_trigger_and_capture_build_command`, which keeps whichever call came last: a
    turn ending re-drains every agent with input queued (`redrain_queued_agents`, F90), so the
    template's turn ending starts the requested agent's queued first turn inside the same window,
    and the last call is the wrong agent's. Each call is told apart by its context file,
    `.agentweave/context/<agent>.md`.
    """
    result_line = (
        '{"type":"result","subtype":"success","is_error":false,'
        f'"session_id":"sess-{session_suffix}"}}\n'
    )
    calls = []
    real_build_command = agent_trigger.build_command

    def _capturing_build_command(**kwargs):
        calls.append(kwargs)
        return real_build_command(**kwargs)

    with (
        patch("hub.turn_scheduler.schedule_agent", schedule_agent),
        patch("hub.api.v1.agent_trigger.PtySession.spawn", _fake_pty([result_line])),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
        patch("hub.api.v1.agent_trigger.build_command", _capturing_build_command),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": agent, "message": "hi", "session_mode": "new"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        await _await_background_run()
    mine = [kwargs for kwargs in calls if Path(str(kwargs["context_file"])).stem == agent]
    # At least one: a requested agent triggered here may run its queued first turn and then this
    # one, and both are its own runs.
    assert mine, [str(kwargs["context_file"]) for kwargs in calls]
    return mine[0]


async def _actor(agent: str = "lead", run_id: str = "run-req") -> dict[str, str]:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _register_template(app, auth_headers, bind_runner, name, *, config=None, charter_id=None):
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": name, "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    if config:
        patched = await app.patch(
            f"/api/v1/projects/proj-test/agents/{name}",
            json={"config": config},
            headers=auth_headers,
        )
        assert patched.status_code == 200, patched.text
    runner_id = await bind_runner(name, cli="claude")
    if charter_id:
        patched = await app.patch(
            f"/api/v1/projects/proj-test/agents/{name}",
            json={"charter_id": charter_id},
            headers=auth_headers,
        )
        assert patched.status_code == 200, patched.text
    return runner_id


async def _agent_row(name: str) -> Agent:
    async with async_session_factory() as session:
        result = await session.execute(select(Agent).where(Agent.name == name))
        return result.scalar_one()


@pytest.mark.asyncio
async def test_a_template_creates_a_runnable_agent(app, auth_headers, bind_runner):
    """Task 1.1. FAILS today (400 *not pre-approved*)."""
    async with async_session_factory() as session:
        session.add(
            Charter(id="charter-t1", project_id="proj-test", name="T1", content="Be helpful")
        )
        await session.commit()
    await _register_template(
        app, auth_headers, bind_runner, "worker-template", charter_id="charter-t1"
    )

    headers = await _actor(run_id="run-1.1")
    resp = await app.post(
        REQUEST_URL,
        headers=headers,
        json={"name": "worker", "template": "worker-template", "task": "help"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["requester"] == "lead"
    assert resp.json()["status"] == "queued"

    template = await _agent_row("worker-template")
    new_agent = await _agent_row("worker")
    assert new_agent.runner_id == template.runner_id
    assert new_agent.charter_id == "charter-t1"
    assert new_agent.created_by_run_id == "run-1.1"


@pytest.mark.asyncio
async def test_grants_are_not_inherited(app, auth_headers, bind_runner):
    """Task 1.2. FAILS today (400)."""
    await _register_template(app, auth_headers, bind_runner, "evidence-template")
    granted = await app.patch(
        "/api/v1/projects/proj-test/agents/evidence-template",
        json={"can_accept_evidence": True},
        headers=auth_headers,
    )
    assert granted.status_code == 200, granted.text

    headers = await _actor(run_id="run-1.2")
    resp = await app.post(
        REQUEST_URL,
        headers=headers,
        json={"name": "evidence-clone", "template": "evidence-template", "task": "help"},
    )
    assert resp.status_code == 201, resp.text

    new_agent = await _agent_row("evidence-clone")
    assert new_agent.can_accept_evidence is False


@pytest.mark.asyncio
async def test_a_full_access_template_does_not_produce_a_full_access_agent(
    app, auth_headers, bind_runner
):
    """Task 1.2a. FAILS today (400); would FAIL after a fix that copied `config` whole."""
    await _register_template(app, auth_headers, bind_runner, "yolo-template")
    posture = await app.patch(
        "/api/v1/projects/proj-test/agents/yolo-template",
        json={"default_permission_mode": FULL_ACCESS_PERMISSION_MODE},
        headers=auth_headers,
    )
    assert posture.status_code == 200, posture.text
    assert posture.json()["config"]["yolo"] is True

    headers = await _actor(run_id="run-1.2a")
    resp = await app.post(
        REQUEST_URL,
        headers=headers,
        json={"name": "yolo-clone", "template": "yolo-template", "task": "help"},
    )
    assert resp.status_code == 201, resp.text

    new_agent = await _agent_row("yolo-clone")
    assert new_agent.default_permission_mode is None
    assert not new_agent.config.get("yolo")

    captured = await _capture_build_command(app, auth_headers, "yolo-clone", session_suffix="1.2a")
    argv = agent_trigger.build_command(**captured)
    assert "--dangerously-skip-permissions" not in argv


@pytest.mark.asyncio
async def test_read_only_and_env_vars_are_copied_but_no_conversation_lends_a_posture(
    app, auth_headers, bind_runner
):
    """Task 1.2b, a control. FAILS today only because every call 400s."""
    await _register_template(
        app,
        auth_headers,
        bind_runner,
        "override-template",
        config={"read_only": True, "env_vars": {"OTHER": "kept"}},
    )
    async with async_session_factory() as session:
        session.add(
            Conversation(
                id="conv-override-template",
                project_id="proj-test",
                agent="override-template",
                lifecycle="open",
                origin="operator",
                lineage_id="conv-override-template",
                runtime_overrides={"permission_mode": FULL_ACCESS_PERMISSION_MODE},
            )
        )
        await session.commit()

    headers = await _actor(run_id="run-1.2b")
    resp = await app.post(
        REQUEST_URL,
        headers=headers,
        json={"name": "override-clone", "template": "override-template", "task": "help"},
    )
    assert resp.status_code == 201, resp.text

    new_agent = await _agent_row("override-clone")
    assert new_agent.config["read_only"] is True
    assert new_agent.config["env_vars"] == {"OTHER": "kept"}

    async with async_session_factory() as session:
        result = await session.execute(
            select(Conversation).where(Conversation.id == resp.json()["conversation_id"])
        )
        conversation = result.scalar_one()
        assert not conversation.runtime_overrides


@pytest.mark.asyncio
async def test_hub_client_is_not_inherited(app, auth_headers, bind_runner):
    """Task 1.2c (operator review: drop `hub_client`).

    FAILS today (400); would FAIL after a fix that dropped only `principal` and `yolo`.
    """
    await _register_template(
        app, auth_headers, bind_runner, "cli-template", config={"hub_client": "cli"}
    )

    headers = await _actor(run_id="run-1.2c")
    resp = await app.post(
        REQUEST_URL,
        headers=headers,
        json={"name": "cli-clone", "template": "cli-template", "task": "help"},
    )
    assert resp.status_code == 201, resp.text

    new_agent = await _agent_row("cli-clone")
    assert "hub_client" not in (new_agent.config or {})

    template_captured = await _capture_build_command(
        app, auth_headers, "cli-template", session_suffix="1-2c-template"
    )
    assert template_captured["mcp_command"] is None
    template_argv = agent_trigger.build_command(**template_captured)
    assert "--permission-mode" in template_argv
    assert template_argv[template_argv.index("--permission-mode") + 1] == "acceptEdits"

    new_captured = await _capture_build_command(
        app, auth_headers, "cli-clone", session_suffix="1-2c-clone"
    )
    assert new_captured["mcp_command"] is not None
    new_argv = agent_trigger.build_command(**new_captured)
    assert "--mcp-config" in new_argv
    if "--permission-mode" in new_argv:
        assert new_argv[new_argv.index("--permission-mode") + 1] != "acceptEdits"


@pytest.mark.asyncio
async def test_a_waiting_override_in_env_vars_is_not_inherited(
    app, auth_headers, bind_runner, monkeypatch
):
    """Task 1.2d. FAILS today (400); would FAIL after a fix that copied `env_vars` whole."""
    monkeypatch.delenv(QUESTION_WAIT_ENV, raising=False)
    await _register_template(
        app,
        auth_headers,
        bind_runner,
        "waiting-template",
        config={"env_vars": {QUESTION_WAIT_ENV: "5", "OTHER": "kept"}},
    )

    headers = await _actor(run_id="run-1.2d")
    resp = await app.post(
        REQUEST_URL,
        headers=headers,
        json={"name": "waiting-clone", "template": "waiting-template", "task": "help"},
    )
    assert resp.status_code == 201, resp.text

    new_agent = await _agent_row("waiting-clone")
    assert new_agent.config["env_vars"] == {"OTHER": "kept"}
    assert effective_question_wait(new_agent) == QUESTION_WAIT_DEFAULT

    template = await _agent_row("waiting-template")
    assert template.config["env_vars"] == {QUESTION_WAIT_ENV: "5", "OTHER": "kept"}


@pytest.mark.asyncio
async def test_an_unknown_template_names_what_would_work(app, auth_headers, bind_runner):
    """Task 1.3. FAILS today (the detail names no agent)."""
    await _register_template(app, auth_headers, bind_runner, "open-one")
    archived = await _register_template(app, auth_headers, bind_runner, "archived-one")
    del archived
    archive_resp = await app.post(
        "/api/v1/projects/proj-test/agents/archived-one/archive", headers=auth_headers
    )
    assert archive_resp.status_code == 200, archive_resp.text

    headers = await _actor(run_id="run-1.3")
    resp = await app.post(
        REQUEST_URL,
        headers=headers,
        json={"name": "nobody", "template": "no-such-agent", "task": "help"},
    )
    assert resp.status_code == 400, resp.text
    assert "open-one" in resp.json()["detail"]
    assert "archived-one" not in resp.json()["detail"]


@pytest.mark.asyncio
async def test_an_archived_template_names_archival(app, auth_headers, bind_runner):
    """Task 1.4. FAILS today (400)."""
    await _register_template(app, auth_headers, bind_runner, "will-archive")
    archive_resp = await app.post(
        "/api/v1/projects/proj-test/agents/will-archive/archive", headers=auth_headers
    )
    assert archive_resp.status_code == 200, archive_resp.text

    headers = await _actor(run_id="run-1.4")
    resp = await app.post(
        REQUEST_URL,
        headers=headers,
        json={"name": "wont-exist", "template": "will-archive", "task": "help"},
    )
    assert resp.status_code == 409, resp.text
    assert "archived" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_a_template_with_no_runner_is_refused(app, auth_headers):
    """Task 1.5. FAILS today (400)."""
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "runnerless-template", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    headers = await _actor(run_id="run-1.5")
    resp = await app.post(
        REQUEST_URL,
        headers=headers,
        json={"name": "wont-exist", "template": "runnerless-template", "task": "help"},
    )
    assert resp.status_code == 409, resp.text
    assert "no runner" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_the_budget_still_bounds_it(app, auth_headers, bind_runner):
    """Task 1.6, a control. FAILS today only because the template check comes first."""
    await _register_template(app, auth_headers, bind_runner, "budget-template")

    async with async_session_factory() as session:
        from hub.db.models import Project

        project = await session.get(Project, "proj-test")
        project.agent_budget = 1
        await session.commit()

    headers = await _actor(run_id="run-1.6")
    resp = await app.post(
        REQUEST_URL,
        headers=headers,
        json={"name": "over-budget", "template": "budget-template", "task": "help"},
    )
    assert resp.status_code == 409, resp.text
    assert "budget" in resp.json()["detail"]

    async with async_session_factory() as session:
        result = await session.execute(select(Agent).where(Agent.name == "over-budget"))
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_a_raise_from_scheduling_still_answers_queued(app, auth_headers, bind_runner):
    """Task 1.7. FAILS today (500)."""
    await _register_template(app, auth_headers, bind_runner, "raising-template")

    headers = await _actor(run_id="run-1.7")
    with patch("hub.turn_scheduler.schedule_agent", side_effect=RuntimeError("boom")):
        resp = await app.post(
            REQUEST_URL,
            headers=headers,
            json={"name": "queued-anyway", "template": "raising-template", "task": "help"},
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "queued"

    new_agent = await _agent_row("queued-anyway")
    assert new_agent is not None
