"""A permission request never outlives the run that raised it.

The seam nothing covered: `test_permission_approver.py` asserts the run's *local* decision
against a stubbed Hub, and the route tests never open a request at all. Between them sat the
defect — a run that stops waiting writes nothing back, so the row stays "pending", the card
stays on screen, and the operator's Allow returns 200 while nothing runs.

These tests speak to the real HTTP routes on both sides: the run's under its own run-bound
credential, the operator's under the project key. That is the only place the two views of one
decision can be seen to disagree.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, PermissionRequest, Run

RUN_ID = "run-perm-lifecycle"
CONVERSATION_ID = "conv-perm-lifecycle"
AGENT = "lead"


async def _waiting_run(run_id: str = RUN_ID, conversation_id: str = CONVERSATION_ID) -> dict:
    """A running run inside a conversation, and the credential it speaks to the Hub with."""
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Conversation(id=conversation_id, project_id="proj-test", agent=AGENT, lifecycle="open")
        )
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=AGENT,
                status="running",
                turn_depth=0,
                conversation_id=conversation_id,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _open_request(app, headers) -> str:
    opened = await app.post(
        "/api/v1/agent-actions/permission-requests",
        headers=headers,
        json={"tool_name": "Bash", "tool_use_id": "toolu_1", "tool_input": {"command": "ls"}},
    )
    assert opened.status_code == 201, opened.text
    assert opened.json()["status"] == "pending"
    return opened.json()["id"]


async def _status(request_id: str) -> str:
    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(PermissionRequest).where(PermissionRequest.id == request_id)
            )
        ).scalar_one()
        return row.status


@pytest.mark.asyncio
async def test_a_run_that_stops_waiting_leaves_no_answerable_request(app, auth_headers):
    """Task 1.1 — the whole defect, at the seam where it lives.

    The run's wait lapses with no decision. Today `_ask_operator` returns its local denial and
    writes nothing back, so every assertion after the expire call describes what an operator
    is shown: a live card for a decision that can no longer take effect, and an Allow that
    succeeds without doing anything.
    """
    headers = await _waiting_run()
    request_id = await _open_request(app, headers)

    # The run stops waiting. It reports that — it is not reporting a decision, only that
    # nobody is listening any more.
    expired = await app.post(
        f"/api/v1/agent-actions/permission-requests/{request_id}/expire", headers=headers
    )
    assert expired.status_code == 200, expired.text
    assert expired.json()["status"] == "expired"

    assert await _status(request_id) != "pending"

    # The operator is no longer offered it...
    listed = await app.get("/api/v1/projects/proj-test/permission-requests", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert request_id not in [row["id"] for row in listed.json()]

    # ...and answering it anyway is refused rather than absorbed. A 200 here would write a
    # false record that the operator authorised an action that never occurred (design D3).
    decided = await app.post(
        f"/api/v1/projects/proj-test/permission-requests/{request_id}/decide",
        headers=auth_headers,
        json={"allow": True},
    )
    assert decided.status_code == 409, decided.text
    assert "moved on" in decided.json()["detail"]
    assert await _status(request_id) == "expired"


@pytest.mark.asyncio
async def test_a_request_does_not_survive_the_run_that_raised_it(app, auth_headers):
    """Task 1.1, the second half — the run never reports at all.

    Reporting is best-effort by design, and a killed run never gets to report. This is the
    same defect reached without touching the expire route, so it fails on the defect itself
    rather than on an absent endpoint: the run is over, and the operator can still "approve".
    """
    headers = await _waiting_run()
    request_id = await _open_request(app, headers)

    async with async_session_factory() as session:
        run = await session.get(Run, RUN_ID)
        run.status = "stopped"
        await session.commit()

    assert await _status(request_id) != "pending"

    decided = await app.post(
        f"/api/v1/projects/proj-test/permission-requests/{request_id}/decide",
        headers=auth_headers,
        json={"allow": True},
    )
    assert decided.status_code == 409, decided.text


@pytest.mark.asyncio
async def test_an_expired_request_stops_pinning_its_conversation_as_waiting(app, auth_headers):
    """Task 1.2 — the second symptom of the same cause.

    `conversations.conversation_attention` counts a pending permission request as a reason a
    conversation is waiting on the operator, so a row that never reaches a terminal status pins
    its conversation as "waiting" permanently — long after the run has gone.
    """
    headers = await _waiting_run()
    request_id = await _open_request(app, headers)

    async def attention() -> str:
        listed = await app.get(
            f"/api/v1/projects/proj-test/agent/{AGENT}/conversations", headers=auth_headers
        )
        assert listed.status_code == 200, listed.text
        row = next(row for row in listed.json() if row["id"] == CONVERSATION_ID)
        return row["attention"]

    assert await attention() == "waiting"

    expired = await app.post(
        f"/api/v1/agent-actions/permission-requests/{request_id}/expire", headers=headers
    )
    assert expired.status_code == 200, expired.text

    async with async_session_factory() as session:
        run = await session.get(Run, RUN_ID)
        run.status = "completed"
        await session.commit()

    assert await attention() != "waiting"
