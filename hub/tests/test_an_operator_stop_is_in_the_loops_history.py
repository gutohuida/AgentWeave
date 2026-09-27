"""An operator's stop, archive and delegation are in the loop's own history, and an ending is final.

Change `a-loop-is-stopped-archived-and-delegated-from-its-own-tab`, design D2, D2a, D3, D3a, D3b.
Before it, `PATCH /jobs/{id} {stop_reason}` ended a loop and wrote no `loop_stopped` event; a second
stop reworded how, why and when the loop had ended; and the archive and control routes committed
before their event write, so a failed write answered 500 for a change that had landed.
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub import sse as sse_module
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop
from hub.loop_ending import ARCHIVED_WITH_JOB_REASON, end_loop

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/projects/proj-test"


async def _loop_job(app, auth_headers):
    resp = await app.post(
        f"{BASE}/jobs",
        json={
            "name": "Stoppable Loop",
            "agent": "kimi",
            "message": "work the queue",
            "cron": "*/5 * * * *",
            "enabled": True,
            "purpose": "keep developing",
            "stop_when_queue_empties": True,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["id"], body["loop"]["id"]


async def _loop_row(loop_id):
    async with async_session_factory() as session:
        return await session.get(Loop, loop_id)


async def _events(app, auth_headers, loop_id, event_type):
    resp = await app.get(f"{BASE}/loops/{loop_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return [e for e in resp.json()["events"] if e["event_type"] == event_type]


@pytest.fixture
def published(monkeypatch):
    frames: list = []
    real = sse_module.sse_manager.publish

    def spy(project_id, event_type, payload):
        frames.append((event_type, payload))
        return real(project_id, event_type, payload)

    monkeypatch.setattr(sse_module.sse_manager, "publish", spy)
    return frames


async def test_an_operator_stop_writes_a_loop_stopped_event(app, auth_headers):
    job_id, loop_id = await _loop_job(app, auth_headers)
    resp = await app.patch(
        f"{BASE}/jobs/{job_id}", json={"stop_reason": "enough"}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text

    stopped = await _events(app, auth_headers, loop_id, "loop_stopped")
    assert len(stopped) == 1
    assert stopped[0]["data"]["reason"] == "enough"
    assert stopped[0]["data"]["loop_id"] == loop_id


async def test_an_operator_stop_announces_loop_stopped(app, auth_headers, published):
    job_id, loop_id = await _loop_job(app, auth_headers)
    await app.patch(f"{BASE}/jobs/{job_id}", json={"stop_reason": "enough"}, headers=auth_headers)

    stopped = [p for kind, p in published if kind == "loop_stopped"]
    assert len(stopped) == 1
    assert stopped[0]["loop_id"] == loop_id
    assert stopped[0]["reason"] == "enough"
    kinds = [kind for kind, _ in published]
    assert kinds.index("loop_stopped") < kinds.index("job_updated")


async def test_a_second_stop_is_refused_and_changes_nothing(app, auth_headers):
    job_id, loop_id = await _loop_job(app, auth_headers)
    await app.patch(f"{BASE}/jobs/{job_id}", json={"stop_reason": "enough"}, headers=auth_headers)
    first = await _loop_row(loop_id)

    second = await app.patch(
        f"{BASE}/jobs/{job_id}", json={"stop_reason": "reworded"}, headers=auth_headers
    )
    assert second.status_code == 409, second.text
    detail = second.json()["detail"]
    assert detail["code"] == "loop_already_ended"
    assert "already ended" in detail["message"]
    assert "enough" in detail["message"]

    after = await _loop_row(loop_id)
    assert (after.ending_state, after.stop_reason, after.stopped_at) == (
        first.ending_state,
        first.stop_reason,
        first.stopped_at,
    )
    assert len(await _events(app, auth_headers, loop_id, "loop_stopped")) == 1


async def test_a_stop_for_a_loop_that_ended_by_itself_is_refused_whole(app, auth_headers):
    job_id, loop_id = await _loop_job(app, auth_headers)
    async with async_session_factory() as session:
        loop = await session.get(Loop, loop_id)
        loop.ending_state = "completed"
        loop.stop_reason = "loop queue is empty"
        loop.stopped_at = datetime.now(timezone.utc)
        await session.commit()

    resp = await app.patch(
        f"{BASE}/jobs/{job_id}",
        json={"stop_reason": "x", "name": "renamed"},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
    async with async_session_factory() as session:
        assert (await session.get(AIJob, job_id)).name == "Stoppable Loop"


async def test_archiving_an_ended_loops_job_still_works_and_keeps_its_ending(app, auth_headers):
    """A control: D2a's guards must leave `archive_job` working on an ended loop."""
    job_id, loop_id = await _loop_job(app, auth_headers)
    await app.patch(f"{BASE}/jobs/{job_id}", json={"stop_reason": "enough"}, headers=auth_headers)
    before = await _loop_row(loop_id)

    resp = await app.post(f"{BASE}/jobs/{job_id}/archive", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    after = await _loop_row(loop_id)
    assert after.archived_at is not None
    assert (after.ending_state, after.stop_reason, after.stopped_at) == (
        before.ending_state,
        before.stop_reason,
        before.stopped_at,
    )


async def test_end_loop_is_write_once():
    t0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    job = AIJob(enabled=True)
    ended = Loop(ending_state="completed", stop_reason="loop queue is empty", stopped_at=t0)

    assert (
        end_loop(job, ended, reason="loop stop time reached (x)", when=t1, completed=False) is False
    )
    assert (ended.ending_state, ended.stop_reason, ended.stopped_at) == (
        "completed",
        "loop queue is empty",
        t0,
    )
    assert job.enabled is False

    running = Loop(ending_state=None)
    job.enabled = True
    assert end_loop(job, running, reason="done", when=t1, completed=False) is True
    assert (running.ending_state, running.stop_reason, running.stopped_at) == (
        "stopped",
        "done",
        t1,
    )


async def test_a_failed_event_write_leaves_the_loop_running(app, auth_headers, monkeypatch):
    job_id, loop_id = await _loop_job(app, auth_headers)

    async def boom(*args, **kwargs):
        raise RuntimeError("event write failed")

    monkeypatch.setattr("hub.api.v1.jobs.persist_event", boom)
    with pytest.raises(RuntimeError):
        await app.patch(
            f"{BASE}/jobs/{job_id}", json={"stop_reason": "enough"}, headers=auth_headers
        )

    loop = await _loop_row(loop_id)
    assert loop.ending_state is None
    async with async_session_factory() as session:
        assert (await session.get(AIJob, job_id)).enabled is True


async def test_an_operator_stop_always_records_stopped(app, auth_headers):
    """Design D2: the ending is not read from the operator's prose."""
    job_id, loop_id = await _loop_job(app, auth_headers)
    await app.patch(
        f"{BASE}/jobs/{job_id}", json={"stop_reason": "loop queue is empty"}, headers=auth_headers
    )
    assert (await _loop_row(loop_id)).ending_state == "stopped"


async def test_archiving_a_running_loops_job_records_the_stop_and_the_archive(app, auth_headers):
    job_id, loop_id = await _loop_job(app, auth_headers)
    resp = await app.post(f"{BASE}/jobs/{job_id}/archive", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    stopped = await _events(app, auth_headers, loop_id, "loop_stopped")
    assert len(stopped) == 1
    assert stopped[0]["data"]["reason"] == ARCHIVED_WITH_JOB_REASON
    assert len(await _events(app, auth_headers, loop_id, "loop_archived")) == 1


async def test_archiving_an_ended_loops_job_adds_no_second_stop(app, auth_headers):
    job_id, loop_id = await _loop_job(app, auth_headers)
    await app.patch(f"{BASE}/jobs/{job_id}", json={"stop_reason": "enough"}, headers=auth_headers)
    await app.post(f"{BASE}/jobs/{job_id}/archive", headers=auth_headers)

    assert len(await _events(app, auth_headers, loop_id, "loop_stopped")) == 1
    assert len(await _events(app, auth_headers, loop_id, "loop_archived")) == 1


async def test_a_failed_event_write_leaves_control_and_archive_unchanged(
    app, auth_headers, monkeypatch
):
    job_id, loop_id = await _loop_job(app, auth_headers)

    async def boom(*args, **kwargs):
        raise RuntimeError("event write failed")

    monkeypatch.setattr("hub.api.v1.loops.persist_event", boom)
    with pytest.raises(RuntimeError):
        await app.post(
            f"{BASE}/loops/{loop_id}/control", json={"control": "creator"}, headers=auth_headers
        )
    assert (await _loop_row(loop_id)).control is None

    monkeypatch.undo()
    await app.patch(f"{BASE}/jobs/{job_id}", json={"stop_reason": "enough"}, headers=auth_headers)
    monkeypatch.setattr("hub.api.v1.loops.persist_event", boom)
    with pytest.raises(RuntimeError):
        await app.post(f"{BASE}/loops/{loop_id}/archive", headers=auth_headers)
    assert (await _loop_row(loop_id)).archived_at is None


async def test_control_and_archive_frames_follow_their_commit(app, auth_headers, published):
    job_id, loop_id = await _loop_job(app, auth_headers)
    await app.post(
        f"{BASE}/loops/{loop_id}/control", json={"control": "creator"}, headers=auth_headers
    )
    await app.patch(f"{BASE}/jobs/{job_id}", json={"stop_reason": "enough"}, headers=auth_headers)
    await app.post(f"{BASE}/loops/{loop_id}/archive", headers=auth_headers)

    kinds = [kind for kind, _ in published]
    assert "loop_control_changed" in kinds
    assert "loop_archived" in kinds
    assert len(await _events(app, auth_headers, loop_id, "loop_control_changed")) == 1
    assert len(await _events(app, auth_headers, loop_id, "loop_archived")) == 1
