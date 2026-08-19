"""Tests for design D16-D18 (change `2026-08-18-a-loop-writes-its-own-queue`, tasks B2.2/B2.3/B2.6):
a loop archives instead of deleting, operator-only, and only once it has ended.
"""

import pytest
from fastapi import HTTPException

from hub.api.v1.loops import _require_operator
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, JobRun, Loop, Task
from hub.utils import persist_event


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
    # A4.1/A4.2: the archive action itself is in this loop's own audit trail.
    assert any(event["event_type"] == "loop_archived" for event in body["events"])


@pytest.mark.asyncio
async def test_loop_history_is_isolated_from_other_loops(app, auth_headers):
    """Design D13, task A4.2: retrieving one loop's history must not surface another loop's
    events, even for the same project and the same event_type."""
    async with async_session_factory() as db:
        job_a = await _make_job(db, suffix="isolation-a")
        job_b = await _make_job(db, suffix="isolation-b")
        loop_a = await _make_loop(db, job_id=job_a.id, purpose="a's own work")
        loop_b = await _make_loop(db, job_id=job_b.id, purpose="b's own work")

        await persist_event(
            db,
            "proj-test",
            "loop_control_changed",
            {"id": loop_a.id, "from": "operator", "to": "creator"},
            loop_id=loop_a.id,
        )
        await persist_event(
            db,
            "proj-test",
            "loop_control_changed",
            {"id": loop_b.id, "from": "operator", "to": "creator"},
            loop_id=loop_b.id,
        )
        # An event about neither loop (agent-scoped, not loop-scoped) must not leak in either.
        await persist_event(db, "proj-test", "job_created", {"id": job_a.id})

    detail_a = await app.get(f"/api/v1/projects/proj-test/loops/{loop_a.id}", headers=auth_headers)
    detail_b = await app.get(f"/api/v1/projects/proj-test/loops/{loop_b.id}", headers=auth_headers)
    assert detail_a.status_code == 200
    assert detail_b.status_code == 200

    events_a = detail_a.json()["events"]
    events_b = detail_b.json()["events"]

    assert len(events_a) == 1
    assert events_a[0]["data"]["id"] == loop_a.id
    assert len(events_b) == 1
    assert events_b[0]["data"]["id"] == loop_b.id


@pytest.mark.asyncio
async def test_firing_active_reflects_an_in_progress_job_run(app, auth_headers):
    """Design D13, task A4.4: `firing_active` is true only while a `JobRun` for this loop's job
    is `"in_progress"` — not for `"fired"` (merely enqueued) or a terminal status, and not for
    another loop's job entirely."""
    async with async_session_factory() as db:
        job_a = await _make_job(db, suffix="firing-a")
        job_b = await _make_job(db, suffix="firing-b")
        loop_a = await _make_loop(db, job_id=job_a.id, purpose="a is firing")
        loop_b = await _make_loop(db, job_id=job_b.id, purpose="b is idle")

        db.add(
            JobRun(
                id="run-firing-a-1",
                job_id=job_a.id,
                project_id="proj-test",
                status="in_progress",
                trigger="scheduled",
            )
        )
        db.add(
            JobRun(
                id="run-firing-b-1",
                job_id=job_b.id,
                project_id="proj-test",
                status="fired",
                trigger="scheduled",
            )
        )
        await db.commit()

    detail_a = await app.get(f"/api/v1/projects/proj-test/loops/{loop_a.id}", headers=auth_headers)
    detail_b = await app.get(f"/api/v1/projects/proj-test/loops/{loop_b.id}", headers=auth_headers)
    assert detail_a.status_code == 200
    assert detail_b.status_code == 200
    assert detail_a.json()["firing_active"] is True
    assert detail_b.json()["firing_active"] is False

    listing = await app.get("/api/v1/projects/proj-test/loops", headers=auth_headers)
    assert listing.status_code == 200
    by_id = {row["id"]: row for row in listing.json()}
    assert by_id[loop_a.id]["firing_active"] is True
    assert by_id[loop_b.id]["firing_active"] is False


@pytest.mark.asyncio
async def test_archive_missing_loop_is_404(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/loops/loop-does-not-exist/archive", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_assigned_task_is_seen_as_the_current_task(app, auth_headers):
    """B4.1 (design D21): a task in `assigned` — the status D3's claim sets — was absent from the
    `current_task` candidates query before this change, so a freshly claimed task vanished from
    the loop summary the moment a firing picked it up."""
    async with async_session_factory() as db:
        job = await _make_job(db, suffix="assigned", agent="loop-assigned-agent")
        loop = await _make_loop(db, job_id=job.id, purpose="claim and go")
        db.add(
            Task(
                id="task-loop-assigned-1",
                project_id="proj-test",
                title="claimed by the firing",
                status="assigned",
                loop_id=loop.id,
            )
        )
        await db.commit()

    resp = await app.get(f"/api/v1/projects/proj-test/loops/{loop.id}", headers=auth_headers)
    assert resp.status_code == 200
    current = resp.json()["current_task"]
    assert current is not None
    assert current["id"] == "task-loop-assigned-1"
    assert current["status"] == "assigned"


@pytest.mark.asyncio
async def test_list_loops_is_project_scoped_and_excludes_archived_by_default(app, auth_headers):
    """B4.3/B5.1/B5.4: a project-wide list, no conversation id required (D20), labelled by the
    loop's job name (B4.2, D20), archived loops hidden unless asked for (D16 — nothing is
    deleted, so `include_archived=true` can always still see it)."""
    async with async_session_factory() as db:
        other_project = AIJob(
            id="job-archival-other-project",
            project_id="proj-other",
            name="Other Project Job",
            agent="loop-archival-agent",
            message="hello",
            cron="0 9 * * *",
            enabled=True,
        )
        db.add(other_project)
        await db.commit()
        listed_job = await _make_job(db, suffix="listed")
        listed_loop = await _make_loop(db, job_id=listed_job.id, purpose="show up in the list")
        stopped_job = await _make_job(db, suffix="to-archive")
        stopped_loop = await _make_loop(
            db,
            job_id=stopped_job.id,
            purpose="hidden once archived",
            stop_reason="done",
            ending_state="stopped",
        )
        # `_make_loop` hardcodes `project_id="proj-test"` (see its definition above), which would
        # not actually exercise cross-project scoping — build this one directly, in `proj-other`,
        # matching its job.
        db.add(
            Loop(
                id="loop-archival-other-project",
                project_id="proj-other",
                job_id=other_project.id,
                purpose="a different project's loop",
            )
        )
        await db.commit()

    archive_resp = await app.post(
        f"/api/v1/projects/proj-test/loops/{stopped_loop.id}/archive", headers=auth_headers
    )
    assert archive_resp.status_code == 200, archive_resp.text

    default_list = await app.get("/api/v1/projects/proj-test/loops", headers=auth_headers)
    assert default_list.status_code == 200
    default_ids = {row["id"] for row in default_list.json()}
    assert listed_loop.id in default_ids
    assert stopped_loop.id not in default_ids
    listed_row = next(row for row in default_list.json() if row["id"] == listed_loop.id)
    assert listed_row["label"] == listed_job.name

    full_list = await app.get(
        "/api/v1/projects/proj-test/loops?include_archived=true", headers=auth_headers
    )
    full_ids = {row["id"] for row in full_list.json()}
    assert stopped_loop.id in full_ids
    assert not any(row["label"] == "Other Project Job" for row in full_list.json())


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
