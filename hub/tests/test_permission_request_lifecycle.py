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


async def _row(request_id: str) -> PermissionRequest:
    async with async_session_factory() as session:
        return (
            await session.execute(
                select(PermissionRequest).where(PermissionRequest.id == request_id)
            )
        ).scalar_one()


async def _status(request_id: str) -> str:
    return (await _row(request_id)).status


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

    # Task 4.1 — the refusal leaves no trace of a decision. `decided_at` is what tells an answer
    # apart from a timeout (db/models.py), so a refused click must not be what sets it.
    row = await _row(request_id)
    assert row.status == "expired"
    assert row.decided_at is None
    assert row.decided_by is None


@pytest.mark.asyncio
async def test_a_request_does_not_survive_the_run_that_raised_it(app, auth_headers):
    """Task 1.1, the second half — the run never reports at all.

    Reporting is best-effort by design, and a killed or crashed run never gets to report. The
    defect is reached here without the expire route, through the run-end path that costs the
    operator most: the Hub is bounced while a card is on screen, and the row it leaves behind
    outlives not just its run but the process that served it.
    """
    from hub.run_reconciliation import reconcile_interrupted_runs

    headers = await _waiting_run()
    request_id = await _open_request(app, headers)

    # No pid: the restarted Hub has no process to check, which is what makes the run orphaned.
    assert await reconcile_interrupted_runs() == 1

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


@pytest.mark.asyncio
async def test_the_path_that_already_worked_still_works(app, auth_headers):
    """Task 6.2 — answering in time, over the real routes on both sides.

    The fix touches the timeout path; this is the one that was never broken, and the one an
    operator would notice regressing first.
    """
    headers = await _waiting_run()
    request_id = await _open_request(app, headers)

    decided = await app.post(
        f"/api/v1/projects/proj-test/permission-requests/{request_id}/decide",
        headers=auth_headers,
        json={"allow": True},
    )
    assert decided.status_code == 200, decided.text

    # What the run's poll loop reads to turn this into "allow".
    polled = await app.get(
        f"/api/v1/agent-actions/permission-requests/{request_id}", headers=headers
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["status"] == "allowed"

    row = await _row(request_id)
    assert row.decided_at is not None
    assert row.decided_by == "operator"


@pytest.mark.asyncio
async def test_an_answer_already_given_is_not_overwritten_by_the_sweep(app, auth_headers):
    """Task 6.3 — the race, in the order that would destroy an answer.

    Both transitions are guarded on "pending", so whichever lands first wins. If the sweep were
    an unconditional write, a decision the operator made and the run acted on would be recorded
    afterwards as never having been answered.
    """
    from hub.permission_requests import expire_pending_for_run

    headers = await _waiting_run()
    request_id = await _open_request(app, headers)

    allowed = await app.post(
        f"/api/v1/projects/proj-test/permission-requests/{request_id}/decide",
        headers=auth_headers,
        json={"allow": True},
    )
    assert allowed.status_code == 200

    async with async_session_factory() as session:
        assert await expire_pending_for_run(session, RUN_ID) == 0
        await session.commit()

    row = await _row(request_id)
    assert row.status == "allowed"
    assert row.decided_by == "operator"


@pytest.mark.asyncio
async def test_expiring_twice_is_not_an_error(app):
    """Task 6.3 — the run reports after the sweep already ran, which is the normal case.

    Reporting is best-effort and unordered with respect to the sweep, so arriving second must be
    a silent no-op. Raising here would put an exception on the path whose whole contract is that
    it never raises.
    """
    from hub.permission_requests import expire_pending_for_run

    headers = await _waiting_run()
    request_id = await _open_request(app, headers)

    async with async_session_factory() as session:
        assert await expire_pending_for_run(session, RUN_ID) == 1
        await session.commit()

    again = await app.post(
        f"/api/v1/agent-actions/permission-requests/{request_id}/expire", headers=headers
    )
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "expired"


@pytest.mark.asyncio
async def test_one_run_cannot_close_another_runs_request(app):
    """Scoping, per D6. Narrower than the poll route beside it, which scopes on agent: two runs
    of the same agent must not be able to answer for each other."""
    owner = await _waiting_run()
    request_id = await _open_request(app, owner)

    other = await _waiting_run(run_id="run-other", conversation_id="conv-other")
    refused = await app.post(
        f"/api/v1/agent-actions/permission-requests/{request_id}/expire", headers=other
    )
    assert refused.status_code == 404, refused.text
    assert await _status(request_id) == "pending"


@pytest.mark.asyncio
async def test_an_expired_request_stays_visible_but_an_answered_one_does_not(app, auth_headers):
    """Task 5.1 — what the operator is still shown.

    Expired stays: a card that vanished would be indistinguishable from a bug. Answered goes:
    they dealt with it, and re-showing it would bury the one they missed.
    """
    headers = await _waiting_run()
    expired_id = await _open_request(app, headers)
    answered_id = await _open_request(app, headers)

    await app.post(
        f"/api/v1/projects/proj-test/permission-requests/{answered_id}/decide",
        headers=auth_headers,
        json={"allow": True},
    )
    await app.post(
        f"/api/v1/agent-actions/permission-requests/{expired_id}/expire", headers=headers
    )

    listed = await app.get(
        "/api/v1/projects/proj-test/permission-requests?include_expired=true", headers=auth_headers
    )
    ids = [row["id"] for row in listed.json()]
    assert expired_id in ids
    assert answered_id not in ids

    # The default is unchanged: only what can still be acted on.
    default = await app.get("/api/v1/projects/proj-test/permission-requests", headers=auth_headers)
    assert [row["id"] for row in default.json()] == []


async def _visible(app, auth_headers) -> list:
    listed = await app.get(
        "/api/v1/projects/proj-test/permission-requests?include_expired=true", headers=auth_headers
    )
    assert listed.status_code == 200, listed.text
    return [row["id"] for row in listed.json()]


@pytest.mark.asyncio
async def test_the_operator_can_clear_an_expired_request_they_have_seen(app, auth_headers):
    """Expired cards accumulate on purpose, but a pile that cannot be cleared stops being a
    signal. Dismissing acknowledges one without pretending it was decided."""
    headers = await _waiting_run()
    request_id = await _open_request(app, headers)
    await app.post(
        f"/api/v1/agent-actions/permission-requests/{request_id}/expire", headers=headers
    )
    assert request_id in await _visible(app, auth_headers)

    dismissed = await app.post(
        f"/api/v1/projects/proj-test/permission-requests/{request_id}/dismiss",
        headers=auth_headers,
    )
    assert dismissed.status_code == 200, dismissed.text
    assert dismissed.json()["dismissed"] is True
    assert request_id not in await _visible(app, auth_headers)

    # Dismissal is housekeeping, not a decision: the run-facing record is untouched.
    row = await _row(request_id)
    assert row.status == "expired"
    assert row.decided_at is None
    assert row.decided_by is None
    assert row.dismissed_at is not None


@pytest.mark.asyncio
async def test_a_request_still_being_waited_on_cannot_be_cleared_away(app, auth_headers):
    """Clearing a pending card off the screen would deny it by neglect while the run still
    waits for an answer. It has to be answered, not tidied."""
    headers = await _waiting_run()
    request_id = await _open_request(app, headers)

    refused = await app.post(
        f"/api/v1/projects/proj-test/permission-requests/{request_id}/dismiss",
        headers=auth_headers,
    )
    assert refused.status_code == 409, refused.text
    assert "still waiting on you" in refused.json()["detail"]
    assert await _status(request_id) == "pending"
    assert request_id in await _visible(app, auth_headers)


@pytest.mark.asyncio
async def test_dismissing_twice_is_not_an_error(app, auth_headers):
    """The card can be clicked again from a stale render, and the second click asks for the
    state the row is already in."""
    headers = await _waiting_run()
    request_id = await _open_request(app, headers)
    await app.post(
        f"/api/v1/agent-actions/permission-requests/{request_id}/expire", headers=headers
    )

    for _ in range(2):
        again = await app.post(
            f"/api/v1/projects/proj-test/permission-requests/{request_id}/dismiss",
            headers=auth_headers,
        )
        assert again.status_code == 200, again.text
        assert again.json()["dismissed"] is True


@pytest.mark.asyncio
async def test_dismissing_does_not_revive_the_conversation_or_the_request(app, auth_headers):
    """A dismissed request must not come back through any of the surfaces that read these
    rows — neither the operator's list nor the run's own poll."""
    headers = await _waiting_run()
    request_id = await _open_request(app, headers)
    await app.post(
        f"/api/v1/agent-actions/permission-requests/{request_id}/expire", headers=headers
    )
    await app.post(
        f"/api/v1/projects/proj-test/permission-requests/{request_id}/dismiss",
        headers=auth_headers,
    )

    # The run still reads the terminal status it acted on; dismissal is not its business.
    polled = await app.get(
        f"/api/v1/agent-actions/permission-requests/{request_id}", headers=headers
    )
    assert polled.json()["status"] == "expired"

    decided = await app.post(
        f"/api/v1/projects/proj-test/permission-requests/{request_id}/decide",
        headers=auth_headers,
        json={"allow": True},
    )
    assert decided.status_code == 409, decided.text
