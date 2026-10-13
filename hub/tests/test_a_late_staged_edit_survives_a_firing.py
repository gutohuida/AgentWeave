"""A firing that applied a staged edit must not clear an edit staged after it loaded the loop.

F457. The firing loads the `Loop` row with edit E1 pending; a `PATCH /jobs/{id}` then stages E2;
the firing's commit used to write `pending_edit_at = NULL` (and NULL pending columns) from its
stale copy, stranding E2 behind a cleared marker.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop
from hub.scheduler import _apply_staged_edit_if_idle

from .test_a_flow_is_configured_from_its_own_tab import BASE, _loop_job, _roster

pytestmark = pytest.mark.asyncio


async def test_an_edit_staged_while_a_firing_applies_the_previous_one_stays_staged(
    app, auth_headers
):
    await _roster(app, auth_headers, "agent-a", "agent-b")
    job_id, loop_id = await _loop_job(app, auth_headers)
    first = await app.patch(f"{BASE}/jobs/{job_id}", json={"purpose": "E1"}, headers=auth_headers)
    assert first.status_code == 200, first.text

    async with async_session_factory() as firing:
        job = await firing.get(AIJob, job_id)
        loop = await firing.get(Loop, loop_id)  # the firing's copy: E1 pending

        # Another session stages E2 and commits while the firing is under way.
        second = await app.patch(
            f"{BASE}/jobs/{job_id}",
            json={"purpose": "E2", "agent": "agent-b"},
            headers=auth_headers,
        )
        assert second.status_code == 200, second.text

        payload = await _apply_staged_edit_if_idle(firing, loop, job)
        assert payload is not None and payload["changes"]["purpose"]["to"] == "E1"
        await firing.commit()

    async with async_session_factory() as check:
        loop = await check.get(Loop, loop_id)
        assert loop.purpose == "E1"
        assert loop.pending_edit_at is not None, "E2's marker was cleared by the firing's commit"
        assert loop.pending_purpose == "E2"
        assert loop.pending_agent == "agent-b"


async def test_a_firing_with_nothing_staged_later_still_clears_its_own_edit(app, auth_headers):
    await _roster(app, auth_headers, "agent-a")
    job_id, loop_id = await _loop_job(app, auth_headers)
    await app.patch(f"{BASE}/jobs/{job_id}", json={"purpose": "E1"}, headers=auth_headers)

    async with async_session_factory() as firing:
        job = await firing.get(AIJob, job_id)
        loop = await firing.get(Loop, loop_id)
        assert await _apply_staged_edit_if_idle(firing, loop, job) is not None
        assert loop.pending_edit_at is None and loop.pending_purpose is None
        await firing.commit()

    async with async_session_factory() as check:
        loop = await check.get(Loop, loop_id)
        assert loop.purpose == "E1"
        assert loop.pending_edit_at is None and loop.pending_purpose is None
