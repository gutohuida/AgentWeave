"""F361 and F289: the sender of a held message is told, and a wait is explained as it stands now.

Two reads that were true when written and false when read. `POST /agent-actions/messages` answered
`201` with the stored message for a message the hop budget was holding, so an agent reported it
delivered (F361). And `GET /queue/{agent}/status` returned the stored refusal sentence bare after
the turn it named had ended (F289).
"""

import subprocess
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Project, Run
from hub.inbound_queue import new_entry
from hub.turn_scheduler import schedule_agent

from .test_task_turn_collision import (
    CHALLENGER,
    HELD_TASK,
    HOLDER,
    _agent,
    _conversation,
    _end_run,
    _holding_run,
    _init_repo,
    _task,
)

pytestmark = pytest.mark.asyncio

BUDGET = 3


async def _run_at_depth(run_id: str, agent: str, depth: int) -> dict[str, str]:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.hop_budget = BUDGET
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=depth,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _sync(app, auth_headers, name: str) -> None:
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text


async def _send(app, headers):
    return await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "peer", "content": "hello"},
    )


async def test_a_message_held_by_the_hop_budget_says_so_to_its_sender(app, auth_headers):
    await _sync(app, auth_headers, "peer")
    headers = await _run_at_depth("run-held-sender", "author", BUDGET)

    response = await _send(app, headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["held_by_hop_budget"] is True
    note = body["delivery_note"]
    assert f"{BUDGET + 1} of {BUDGET}" in note
    assert "continues the chain" in note
    assert body["id"] in note
    assert "send it again" not in note.lower()


async def test_a_message_within_the_budget_carries_no_note(app, auth_headers):
    await _sync(app, auth_headers, "peer")
    headers = await _run_at_depth("run-free-sender", "author", BUDGET - 1)

    response = await _send(app, headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert not body["held_by_hop_budget"]
    assert body["delivery_note"] is None


async def test_the_message_list_does_not_claim_a_hold_either_way(app, auth_headers):
    await _sync(app, auth_headers, "peer")
    headers = await _run_at_depth("run-listed-sender", "author", BUDGET)
    sent = (await _send(app, headers)).json()

    listed = await app.get(
        "/api/v1/projects/proj-test/messages",
        params={"history": "true"},
        headers=auth_headers,
    )
    assert listed.status_code == 200, listed.text
    row = next(m for m in listed.json() if m["id"] == sent["id"])
    assert row["held_by_hop_budget"] is None
    assert row["delivery_note"] is None


async def test_send_message_tool_carries_the_hold_and_stays_a_success():
    from hub import mcp_server

    held = {"id": "msg-1", "held_by_hop_budget": True, "delivery_note": "Recorded as msg-1, but"}
    with patch.object(mcp_server, "_hub_request", return_value=held):
        reply = mcp_server.send_message(to_agent="peer", subject="s", content="x")
    assert reply["success"] is True
    assert reply["message_id"] == "msg-1"
    assert reply["held_by_hop_budget"] is True
    assert reply["delivery_note"] == "Recorded as msg-1, but"

    free = {"id": "msg-2", "held_by_hop_budget": None, "delivery_note": None}
    with patch.object(mcp_server, "_hub_request", return_value=free):
        reply = mcp_server.send_message(to_agent="peer", subject="s", content="x")
    assert reply == {"success": True, "message_id": "msg-2"}


async def test_the_held_entry_stores_no_waiting_reason(app, auth_headers):
    """D2: the reason is derived wherever shown, so a raised budget cannot leave a stale copy."""
    await _sync(app, auth_headers, "peer")
    headers = await _run_at_depth("run-nostore-sender", "author", BUDGET)
    await _send(app, headers)

    async with async_session_factory() as session:
        entries = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == "peer")
                )
            )
            .scalars()
            .all()
        )
        assert len(entries) == 1
        assert entries[0].waiting_reason is None


async def _stage_collision(app, auth_headers, bind_runner, bind_project_workspace, tmp_path):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _agent(app, auth_headers, bind_runner, CHALLENGER)
    conversation_id = await _conversation(CHALLENGER)
    await _task(HELD_TASK)
    run_id = await _holding_run(HOLDER, HELD_TASK)
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.hop_budget = 6
        session.add(
            new_entry(
                project_id="proj-test",
                agent=CHALLENGER,
                origin_type="operator",
                content="please start this",
                hop_depth=0,
                conversation_id=conversation_id,
                task_id=HELD_TASK,
            )
        )
        await session.commit()
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        result = await schedule_agent("proj-test", CHALLENGER)
        assert result.terminal_failure is False
    return run_id


async def _status(app, auth_headers) -> str:
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        response = await app.get(
            f"/api/v1/projects/proj-test/queue/{CHALLENGER}/status", headers=auth_headers
        )
    assert response.status_code == 200, response.text
    return response.json()["waiting_reason"]


async def test_a_refusal_naming_an_ended_holder_is_told_as_the_last_attempt(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    run_id = await _stage_collision(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path
    )
    live = await _status(app, auth_headers)
    assert HOLDER in live and "is already running a turn" in live

    await _end_run(run_id)  # no re-drain: the entry keeps the stored sentence

    after = await _status(app, auth_headers)
    # The stored sentence survives inside the label, as a record; it is not told as the present.
    assert after.startswith("the last delivery attempt was refused:")


async def test_a_stored_refusal_with_nothing_live_is_labelled(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    await _agent(app, auth_headers, bind_runner, CHALLENGER)
    conversation_id = await _conversation(CHALLENGER)
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.hop_budget = 6
        entry = new_entry(
            project_id="proj-test",
            agent=CHALLENGER,
            origin_type="operator",
            content="x",
            hop_depth=0,
            conversation_id=conversation_id,
        )
        entry.waiting_reason = "the reviewer commit is not in the checkout"
        session.add(entry)
        await session.commit()

    reason = await _status(app, auth_headers)
    assert (
        reason
        == "the last delivery attempt was refused: the reviewer commit is not in the checkout"
    )


@pytest.mark.parametrize(
    "target",
    [
        "hub.api.v1.inbound_queue.resolve_bound_task",
        "hub.api.v1.inbound_queue.tasks_held_by_a_running_turn",
        "hub.api.v1.inbound_queue.task_workspace.takes_own_checkout",
        "hub.api.v1.inbound_queue.worktrees.takes_task_workspace",
    ],
)
async def test_a_failing_holder_check_falls_back_and_never_500s(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, target
):
    await _stage_collision(app, auth_headers, bind_runner, bind_project_workspace, tmp_path)
    with patch(target, side_effect=RuntimeError("boom")):
        reason = await _status(app, auth_headers)
    assert reason.startswith("the last delivery attempt was refused:")


async def test_the_holder_check_spawns_no_task_integration_git(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    await _stage_collision(app, auth_headers, bind_runner, bind_project_workspace, tmp_path)
    with patch(
        "hub.task_integration._git", side_effect=subprocess.TimeoutExpired("git", 1)
    ) as spawned:
        reason = await _status(app, auth_headers)
    assert HOLDER in reason
    spawned.assert_not_called()
