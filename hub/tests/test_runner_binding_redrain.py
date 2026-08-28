"""F96: binding a runner is the repair the "no runner is bound" refusal names.

Measured live against the trial Hub on 2026-08-28. An agent with no bound runner was sent a
message; the Hub queued it and answered with the remedy in words — *"No runner is bound to this
agent. Bind one in the Hub UI before it can run."* The operator then did exactly that, and the
entry did not move. Thirty seconds of polling later it still read `waiting_count: 1`, and its
`waiting_reason` had become `"delivery failed 1 time; 2 attempts left"` — the retry counter had
taken the place of the reason, so the status no longer even mentioned the runner that had just
been bound. An unrelated `PUT /settings` then delivered it within six seconds, which is what
proves the message had been deliverable from the moment of the rebind.

The sibling case has had this since 2026-08-03: `POST /relocate` redrains, because relocation is
the repair for "project workspace is unavailable". Binding was the one repair route with no
redrain behind it.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Run

_TERMINAL_RUN_STATUSES = ("completed", "failed", "stopped", "error", "cancelled")


async def _settled_runs(agent_trigger, *, deadline: float = 10.0):
    """Wait for the work the rebind scheduled, by condition rather than by snapshot (F40)."""
    loop = asyncio.get_running_loop()
    end = loop.time() + deadline
    runs = []
    while True:
        pending = list(agent_trigger._background_runs)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        async with async_session_factory() as session:
            runs = (
                (
                    await session.execute(
                        select(Run).where(Run.project_id == "proj-test", Run.agent == "claude")
                    )
                )
                .scalars()
                .all()
            )
        if runs and all(run.status in _TERMINAL_RUN_STATUSES for run in runs):
            return runs
        if loop.time() >= end:
            raise AssertionError(
                f"the rebound agent's run never settled within {deadline}s: "
                f"{[(run.id, run.status) for run in runs]}"
            )
        await asyncio.sleep(0.05)


def _fake_pty(pid=4242):
    session = MagicMock()
    session.pid = pid
    session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-1"}\n',
        "",
    ]
    session.wait.return_value = 0
    return MagicMock(return_value=session)


async def _sync_agent(app, auth_headers, agent_name):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent_name: {}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text


@pytest.mark.asyncio
async def test_binding_a_runner_delivers_the_message_that_was_waiting_for_one(
    app, auth_headers, bind_project_workspace, tmp_path
):
    import hub.api.v1.agent_trigger as agent_trigger

    directory = tmp_path / "proj"
    directory.mkdir(parents=True, exist_ok=True)
    await bind_project_workspace(directory)
    await _sync_agent(app, auth_headers, "claude")

    created = await app.post(
        "/api/v1/projects/proj-test/runners",
        json={"name": "claude-runner", "cli": "claude"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    runner_id = created.json()["id"]

    # Deliberately unbound: this is the state a fresh roster entry is in before the operator
    # picks a runner for it, and the state the live measurement started from.
    queued = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        headers=auth_headers,
        json={"agent": "claude", "message": "hello"},
    )
    assert queued.status_code == 200, queued.text
    assert queued.json()["status"] == "queued"
    assert "runner" in (queued.json()["waiting_reason"] or "")

    with (
        patch("hub.api.v1.agent_trigger.PtySession.spawn", _fake_pty()),
        patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"),
    ):
        bound = await app.patch(
            "/api/v1/projects/proj-test/agents/claude",
            json={"runner_id": runner_id},
            headers=auth_headers,
        )
        assert bound.status_code == 200, bound.text
        # Awaited inside the patch for F40's reason: the redrain spawns as a background task.
        runs = await _settled_runs(agent_trigger)

    assert len(runs) == 1
    assert runs[0].status == "completed"

    async with async_session_factory() as session:
        entries = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(
                        InboundQueueEntry.project_id == "proj-test",
                        InboundQueueEntry.agent == "claude",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert [entry.state for entry in entries] == ["delivered"]


@pytest.mark.asyncio
async def test_rebinding_the_same_runner_schedules_nothing(
    app, auth_headers, bind_project_workspace, bind_runner, tmp_path
):
    """The redrain is gated on the binding actually changing, not on the field being present.

    The Hub UI submits the whole agent form, so a PATCH carrying the runner the agent already
    has is the ordinary case — renaming an agent, or changing its permission posture, must not
    start a turn as a side effect.
    """
    import hub.api.v1.agent_trigger as agent_trigger

    directory = tmp_path / "proj"
    directory.mkdir(parents=True, exist_ok=True)
    await bind_project_workspace(directory)
    await _sync_agent(app, auth_headers, "claude")
    runner_id = await bind_runner("claude", cli="claude")

    # Block delivery so that anything scheduled would have to leave the entry queued rather than
    # run it — the assertion below is then about scheduling, not about spawn success.
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-blocking",
                project_id="proj-test",
                agent="claude",
                status="running",
                turn_depth=0,
            )
        )
        await session.commit()

    queued = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        headers=auth_headers,
        json={"agent": "claude", "message": "hello"},
    )
    assert queued.status_code == 200, queued.text
    assert queued.json()["status"] == "queued"

    with patch("hub.turn_scheduler.schedule_agent") as scheduled:
        again = await app.patch(
            "/api/v1/projects/proj-test/agents/claude",
            json={"runner_id": runner_id, "description": "same runner, new description"},
            headers=auth_headers,
        )
        assert again.status_code == 200, again.text
    scheduled.assert_not_called()

    assert not list(agent_trigger._background_runs)
