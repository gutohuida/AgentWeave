"""Tests for design D16-D18 (change `2026-08-18-a-loop-writes-its-own-queue`, tasks B2.2/B2.3/B2.6):
a loop archives instead of deleting, operator-only, and only once it has ended.
"""

import pytest
from fastapi import HTTPException

from hub.api.v1.loops import _require_operator
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop


async def _make_job(db, *, suffix, agent="loop-archival-agent"):
    job = AIJob(
        id=f"job-archival-{suffix}",
        project_id="proj-test",
        name=f"Archival Job {suffix}",
        agent=agent,
        message="hello",
        cron="0 9 * * *",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    return job


async def _make_loop(db, *, job_id, **fields):
    loop = Loop(id=f"loop-archival-{job_id}", project_id="proj-test", job_id=job_id, **fields)
    db.add(loop)
    await db.commit()
    return loop


def test_require_operator_refuses_agent_attribution():
    """B2.2: mirrors `spec_lifecycle.py`'s own operator-only check for documents. Unreachable via
    HTTP today (no agent-actions wrapper exists for this route, and its own auth dependency
    already requires an operator credential no run token can satisfy) — this is the explicit,
    defence-in-depth guard `spec_lifecycle.transition` also keeps despite similar protection
    elsewhere."""
    _require_operator(None, None)  # no attribution: does not raise

    with pytest.raises(HTTPException) as excinfo:
        _require_operator("some-agent", "run-123")
    assert excinfo.value.status_code == 403

    with pytest.raises(HTTPException):
        _require_operator("some-agent", None)

    with pytest.raises(HTTPException):
        _require_operator(None, "run-123")


@pytest.mark.asyncio
async def test_archive_refuses_a_running_loop(app, auth_headers):
    """B2.3: `ending_state` is NULL while a loop is still running — archiving must refuse."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="running")
        loop = await _make_loop(db, job_id=job.id, purpose="still going")

    resp = await app.post(
        f"/api/v1/projects/proj-test/loops/{loop.id}/archive", headers=auth_headers
    )
    assert resp.status_code == 400
    assert "stop or complete" in resp.json()["detail"]

    async with async_session_factory() as db:
        refreshed = await db.get(Loop, loop.id)
        assert refreshed.archived_at is None


@pytest.mark.asyncio
async def test_archive_a_stopped_loop_then_it_still_answers_its_own_history(app, auth_headers):
    """B2.2 + B2.6 (design D16's guarantee): a loop archived after stopping still returns its
    purpose, queue history, firings, and stop reason — archiving hides it from default listings,
    it destroys nothing."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="stopped")
        loop = await _make_loop(
            db,
            job_id=job.id,
            purpose="finished work",
            stop_reason="loop stop time reached (manually recorded for this test)",
            ending_state="stopped",
        )

    detail_before = await app.get(
        f"/api/v1/projects/proj-test/loops/{loop.id}", headers=auth_headers
    )
    assert detail_before.status_code == 200
    assert detail_before.json()["archived_at"] is None

    archived = await app.post(
        f"/api/v1/projects/proj-test/loops/{loop.id}/archive", headers=auth_headers
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived_at"] is not None
    assert archived.json()["ending_state"] == "stopped"

    # Archiving again is refused, not a silent no-op.
    twice = await app.post(
        f"/api/v1/projects/proj-test/loops/{loop.id}/archive", headers=auth_headers
    )
    assert twice.status_code == 400

    # D16's guarantee: the archived loop is still fully readable by id.
    detail_after = await app.get(
        f"/api/v1/projects/proj-test/loops/{loop.id}", headers=auth_headers
    )
    assert detail_after.status_code == 200
    body = detail_after.json()
    assert body["purpose"] == "finished work"
    assert body["stop_reason"] == "loop stop time reached (manually recorded for this test)"
    assert body["ending_state"] == "stopped"
    assert body["archived_at"] is not None
    assert body["job_id"] == job.id
    assert isinstance(body["history"], list)


@pytest.mark.asyncio
async def test_archive_missing_loop_is_404(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/loops/loop-does-not-exist/archive", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_operator_supplied_stop_reason_records_a_stopped_ending(app, auth_headers):
    """B2.5: an operator explicitly stating why a loop stopped, via `PATCH .../jobs/{id}`, is
    itself "an operator stop" — the one ending path `scheduler.py`'s own check cannot see."""
    create = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Operator Stopped",
            "agent": "kimi",
            "message": "x",
            "cron": "0 9 * * *",
            "purpose": "manual stop test",
            "stop_when_queue_empties": True,
        },
        headers=auth_headers,
    )
    assert create.status_code == 201, create.text
    job_id = create.json()["id"]

    patched = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"stop_reason": "operator decided to stop it", "enabled": False},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["loop"]["ending_state"] == "stopped"
    assert patched.json()["loop"]["stop_reason"] == "operator decided to stop it"

    # A later edit to the prose must not overwrite the governance fact already recorded.
    edited = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"stop_reason": "operator decided to stop it, revised"},
        headers=auth_headers,
    )
    assert edited.status_code == 200
    assert edited.json()["loop"]["ending_state"] == "stopped"
