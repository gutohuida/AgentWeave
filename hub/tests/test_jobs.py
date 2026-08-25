"""Tests for job endpoints."""

import importlib.util

import pytest

# Check if croniter is available
CRONITER_AVAILABLE = importlib.util.find_spec("croniter") is not None


@pytest.mark.asyncio
async def test_create_job(app, auth_headers):
    """Test creating a new job."""
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Test Job",
            "agent": "kimi",
            "message": "Test message",
            "cron": "0 9 * * *",
            "session_mode": "new",
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("job-")
    assert data["name"] == "Test Job"
    assert data["agent"] == "kimi"
    assert data["cron"] == "0 9 * * *"
    assert data["enabled"] is True
    assert data["source"] == "hub"


@pytest.mark.asyncio
async def test_create_job_invalid_cron(app, auth_headers):
    """Test creating a job with invalid cron expression."""
    if not CRONITER_AVAILABLE:
        pytest.skip("croniter not available")
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Bad Job",
            "agent": "kimi",
            "message": "Test",
            "cron": "invalid cron",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "cron" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_jobs(app, auth_headers):
    """Test listing all jobs."""
    # Create a couple of jobs
    await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Job 1",
            "agent": "kimi",
            "message": "Message 1",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Job 2",
            "agent": "claude",
            "message": "Message 2",
            "cron": "0 10 * * *",
        },
        headers=auth_headers,
    )

    resp = await app.get("/api/v1/projects/proj-test/jobs", headers=auth_headers)
    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) >= 2
    job_names = {j["name"] for j in jobs}
    assert "Job 1" in job_names
    assert "Job 2" in job_names


@pytest.mark.asyncio
async def test_get_job_by_id(app, auth_headers):
    """Test getting a specific job by ID."""
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Get Job",
            "agent": "kimi",
            "message": "Get me",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    resp = await app.get(f"/api/v1/projects/proj-test/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == job_id
    assert data["name"] == "Get Job"
    assert data["history"] is not None  # Should include history


@pytest.mark.asyncio
async def test_get_job_not_found(app, auth_headers):
    """Test getting a non-existent job."""
    resp = await app.get("/api/v1/projects/proj-test/jobs/job-nonexistent123", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_job(app, auth_headers):
    """Test updating a job."""
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Update Job",
            "agent": "kimi",
            "message": "Original message",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    # Update the job
    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={
            "name": "Updated Name",
            "message": "Updated message",
            "cron": "0 10 * * *",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated Name"
    assert data["message"] == "Updated message"
    assert data["cron"] == "0 10 * * *"


@pytest.mark.asyncio
async def test_update_job_invalid_cron(app, auth_headers):
    """Test updating a job with invalid cron."""
    if not CRONITER_AVAILABLE:
        pytest.skip("croniter not available")
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Update Job",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"cron": "bad cron"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_pause_and_resume_job(app, auth_headers):
    """Test pausing and resuming a job."""
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Toggle Job",
            "agent": "kimi",
            "message": "Toggle me",
            "cron": "0 9 * * *",
            "enabled": True,
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]
    assert create_resp.json()["enabled"] is True

    # Pause the job
    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"enabled": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    # Resume the job
    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


@pytest.mark.asyncio
async def test_delete_job_refuses_and_archive_replaces_it(app, auth_headers):
    """Design D16 (B2.1/B2.2): nothing is deletable — a job archives instead."""
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Delete Job",
            "agent": "kimi",
            "message": "Delete me",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    # DELETE refuses, naming archiving as the alternative (B2.1) — nothing is removed.
    resp = await app.delete(f"/api/v1/projects/proj-test/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 400
    assert "archiv" in resp.json()["detail"].lower()

    get_resp = await app.get(f"/api/v1/projects/proj-test/jobs/{job_id}", headers=auth_headers)
    assert get_resp.status_code == 200

    # Archiving is the real alternative (B2.2): the job survives, but drops out of the default
    # list (B2.4) while remaining fully readable by id (D16's guarantee).
    archived = await app.post(
        f"/api/v1/projects/proj-test/jobs/{job_id}/archive", headers=auth_headers
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived_at"] is not None

    still_there = await app.get(f"/api/v1/projects/proj-test/jobs/{job_id}", headers=auth_headers)
    assert still_there.status_code == 200
    assert still_there.json()["archived_at"] is not None

    default_list = await app.get("/api/v1/projects/proj-test/jobs", headers=auth_headers)
    assert job_id not in {j["id"] for j in default_list.json()}

    with_archived = await app.get(
        "/api/v1/projects/proj-test/jobs?include_archived=true", headers=auth_headers
    )
    assert job_id in {j["id"] for j in with_archived.json()}

    # Archiving an already-archived job is refused, not a silent no-op.
    twice = await app.post(
        f"/api/v1/projects/proj-test/jobs/{job_id}/archive", headers=auth_headers
    )
    assert twice.status_code == 400


@pytest.mark.asyncio
async def test_run_job_disabled(app, auth_headers):
    """Test running a disabled job fails."""
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Disabled Job",
            "agent": "kimi",
            "message": "I'm disabled",
            "cron": "0 9 * * *",
            "enabled": False,
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    # Try to run the disabled job
    resp = await app.post(f"/api/v1/projects/proj-test/jobs/{job_id}/run", headers=auth_headers)
    assert resp.status_code == 400
    assert "disabled" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_run_job_not_found(app, auth_headers):
    """Test running a non-existent job."""
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs/job-nonexistent/run", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_job_with_custom_id_rejected(app, auth_headers):
    """Client-supplied IDs are rejected from Create schemas (S5)."""
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "id": "my-custom-job-id",
            "name": "Custom ID Job",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_job_ids_are_server_generated(app, auth_headers):
    """Job IDs are generated by the server, not accepted from clients."""
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Server Generated ID Job",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["id"].startswith("job-")


@pytest.mark.asyncio
async def test_job_source_field(app, auth_headers):
    """Test that source field is set correctly."""
    # Default should be "hub"
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Source Test",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    assert resp.json()["source"] == "hub"

    # Can set to "local"
    resp2 = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Local Job",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
            "source": "local",
        },
        headers=auth_headers,
    )
    assert resp2.json()["source"] == "local"


@pytest.mark.asyncio
async def test_job_session_modes(app, auth_headers):
    """Test creating jobs with different session modes."""
    # New session mode
    resp1 = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "New Session Job",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
            "session_mode": "new",
        },
        headers=auth_headers,
    )
    assert resp1.json()["session_mode"] == "new"

    # Resume session mode
    resp2 = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Resume Session Job",
            "agent": "claude",
            "message": "Test",
            "cron": "0 10 * * *",
            "session_mode": "resume",
        },
        headers=auth_headers,
    )
    assert resp2.json()["session_mode"] == "resume"


@pytest.mark.asyncio
async def test_job_history_tracks_runs(app, auth_headers):
    """Test that job history tracks runs."""
    # Create a job
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "History Job",
            "agent": "kimi",
            "message": "Track my runs",
            "cron": "0 9 * * *",
            "enabled": True,
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]
    assert create_resp.json()["run_count"] == 0

    # Run the job
    run_resp = await app.post(f"/api/v1/projects/proj-test/jobs/{job_id}/run", headers=auth_headers)

    # If scheduler not available, skip this test
    if run_resp.status_code == 503:
        pytest.skip("Scheduler not available in test environment")

    # Should succeed
    assert run_resp.status_code == 200
    assert run_resp.json()["success"] is True

    # Check that run_count increased
    get_resp = await app.get(f"/api/v1/projects/proj-test/jobs/{job_id}", headers=auth_headers)
    assert get_resp.json()["run_count"] == 1
    assert len(get_resp.json()["history"]) == 1


@pytest.mark.asyncio
async def test_update_job_not_found(app, auth_headers):
    """Test updating a non-existent job."""
    resp = await app.patch(
        "/api/v1/projects/proj-test/jobs/job-nonexistent",
        json={"name": "New Name"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_job_not_found(app, auth_headers):
    """Test deleting a non-existent job."""
    resp = await app.delete("/api/v1/projects/proj-test/jobs/job-nonexistent", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_plain_job_has_no_loop(app, auth_headers):
    """A job created with no loop fields carries loop: null (design D6/D5)."""
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Plain Job",
            "agent": "kimi",
            "message": "Just a job",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["loop"] is None

    job_id = resp.json()["id"]
    get_resp = await app.get(f"/api/v1/projects/proj-test/jobs/{job_id}", headers=auth_headers)
    assert get_resp.json()["loop"] is None

    list_resp = await app.get("/api/v1/projects/proj-test/jobs", headers=auth_headers)
    listed = next(j for j in list_resp.json() if j["id"] == job_id)
    assert listed["loop"] is None


@pytest.mark.asyncio
async def test_creating_with_purpose_alone_opts_into_a_loop(app, auth_headers):
    """`purpose` alone is enough to opt a job in (design D6's "at least one field" rule)."""
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Loop Job",
            "agent": "kimi",
            "message": "Keep going",
            "cron": "0 9 * * *",
            "purpose": "Nightly dependency audit",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    loop = resp.json()["loop"]
    assert loop is not None
    assert loop["label"] == "Loop Job"
    assert loop["purpose"] == "Nightly dependency audit"
    assert loop["stop_when_queue_empties"] is False
    assert loop["queue"] == {}
    assert loop["current_tasks"] == []
    assert loop["open_questions"] == 0


@pytest.mark.asyncio
async def test_patch_loop_field_on_plain_job_is_400(app, auth_headers):
    """PATCHing a loop field onto a job with no `Loop` row is rejected, not a silent no-op."""
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Plain Job For Patch",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"stop_reason": "manually stopped"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_opts_a_plain_job_into_a_loop_for_the_first_time(app, auth_headers):
    """PATCH with a loop field on a plain job creates the Loop row (mirrors create_job)."""
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Opt-in Later",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]
    assert create_resp.json()["loop"] is None

    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"stop_when_queue_empties": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    loop = resp.json()["loop"]
    assert loop is not None
    assert loop["stop_when_queue_empties"] is True
    assert loop["purpose"] == ""


@pytest.mark.asyncio
async def test_patch_stages_an_edit_to_an_existing_loop_rather_than_applying_it(app, auth_headers):
    """Design D11 (task A2.1/A2.4): PATCHing purpose/stop_at/stop_when_queue_empties onto a job
    with an existing loop is always accepted, but never applied on the spot — it lands in
    `pending_edit`, distinct from the still-unchanged live `purpose`, and is applied only at the
    loop's next firing (`test_scheduler.py`'s own firing-boundary tests exercise that half)."""
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Existing Loop",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
            "purpose": "Initial purpose",
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"purpose": "Revised purpose"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    loop = resp.json()["loop"]
    # The live field is untouched — a firing in flight (or the next one to fire, before it starts)
    # must keep reading the definition it already has.
    assert loop["purpose"] == "Initial purpose"
    assert loop["pending_edit"]["purpose"] == "Revised purpose"
    assert loop["pending_edit"]["staged_by"] == "operator"
    assert loop["pending_edit"]["staged_at"] is not None


@pytest.mark.asyncio
async def test_patch_staging_an_edit_records_actor_and_time(app, auth_headers):
    """Design D11 (task A2.5): each staged edit is recorded against the loop with actor and time —
    mirrors `loop_control_changed`'s own persist_event/broadcast pair (A1)."""
    from sqlalchemy import select

    from hub.db.engine import async_session_factory
    from hub.db.models import EventLog

    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Loop For Edit Event",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
            "purpose": "Original",
        },
        headers=auth_headers,
    )
    loop_id = create_resp.json()["loop"]["id"]
    job_id = create_resp.json()["id"]

    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"purpose": "Edited by operator"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    async with async_session_factory() as session:
        events = (
            (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == "loop_edit_staged")
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        event = events[0]
        assert event.data["id"] == loop_id
        assert event.data["actor"] == "operator"
        assert event.agent is None
        assert event.data["changes"] == {"purpose": "Edited by operator"}


@pytest.mark.asyncio
async def test_resume_on_a_plain_job_is_unchanged_by_patch(app, auth_headers):
    """PATCHing `session_mode=resume` onto a job with no `Loop` row still succeeds, unchanged
    (and still broken per `known_debts` — `AIJob.last_session_id`'s write path is out of scope
    for design D4, which only refuses `resume` for a loop's job)."""
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Plain Job For Resume Patch",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"session_mode": "resume"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["session_mode"] == "resume"
    assert resp.json()["loop"] is None


@pytest.mark.asyncio
async def test_create_job_with_resume_and_loop_opt_in_is_refused(app, auth_headers):
    """Design D4: `session_mode=resume` combined with a loop-opting field in the same POST is
    refused, naming why, rather than silently creating a resumable loop."""
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Resume Loop At Creation",
            "agent": "kimi",
            "message": "Keep going",
            "cron": "0 9 * * *",
            "session_mode": "resume",
            "purpose": "Nightly dependency audit",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"].lower()
    assert "loop" in detail
    assert "checkpoint" in detail

    list_resp = await app.get("/api/v1/projects/proj-test/jobs", headers=auth_headers)
    assert all(j["name"] != "Resume Loop At Creation" for j in list_resp.json())


@pytest.mark.asyncio
async def test_patch_resume_onto_an_existing_loop_job_is_refused(app, auth_headers):
    """Design D4: PATCHing `session_mode=resume` onto a job that already has a `Loop` row is
    refused — the loop was created in an earlier request, so no loop fields need to accompany
    this one for the refusal to fire."""
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Already A Loop",
            "agent": "kimi",
            "message": "Keep going",
            "cron": "0 9 * * *",
            "purpose": "Nightly dependency audit",
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"session_mode": "resume"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"].lower()
    assert "loop" in detail
    assert "checkpoint" in detail

    get_resp = await app.get(f"/api/v1/projects/proj-test/jobs/{job_id}", headers=auth_headers)
    assert get_resp.json()["session_mode"] == "new"


@pytest.mark.asyncio
async def test_patch_resume_and_loop_opt_in_together_is_refused(app, auth_headers):
    """Design D4's "given, in the same request" case: a plain job PATCHed with `session_mode`
    resume AND a loop-opting field together is refused — the request would opt it into a loop
    and set resume in one step, and neither must land."""
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Opts Into A Loop And Resume",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]
    assert create_resp.json()["loop"] is None

    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"session_mode": "resume", "purpose": "Nightly dependency audit"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"].lower()
    assert "loop" in detail
    assert "checkpoint" in detail

    get_resp = await app.get(f"/api/v1/projects/proj-test/jobs/{job_id}", headers=auth_headers)
    assert get_resp.json()["loop"] is None
    assert get_resp.json()["session_mode"] == "new"


@pytest.mark.asyncio
async def test_declaring_a_source_document_on_loop_creation_round_trips(app, auth_headers):
    """Task 4.2(a): a loop created with `spec_document_id` persists it on the `Loop` row."""
    from sqlalchemy import select

    from hub.db.engine import async_session_factory
    from hub.db.models import Loop

    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Declares A Document",
            "agent": "kimi",
            "message": "Work the queue",
            "cron": "0 9 * * *",
            "purpose": "Drive doc-declare-1's tasks",
            "spec_document_id": "doc-declare-1",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201

    async with async_session_factory() as session:
        result = await session.execute(
            select(Loop).where(Loop.project_id == "proj-test", Loop.job_id == resp.json()["id"])
        )
        loop = result.scalar_one()
        assert loop.spec_document_id == "doc-declare-1"


@pytest.mark.asyncio
async def test_a_second_loop_declaring_the_same_document_is_refused(app, auth_headers):
    """Task 4.2(b): a document already claimed by one loop 409s for a second, naming the first."""
    first_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "First Claimant",
            "agent": "kimi",
            "message": "Work the queue",
            "cron": "0 9 * * *",
            "purpose": "Drive doc-declare-2's tasks",
            "spec_document_id": "doc-declare-2",
        },
        headers=auth_headers,
    )
    assert first_resp.status_code == 201
    first_loop_id = first_resp.json()["loop"]["id"]

    second_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Second Claimant",
            "agent": "kimi",
            "message": "Work the queue",
            "cron": "0 9 * * *",
            "purpose": "Also wants doc-declare-2",
            "spec_document_id": "doc-declare-2",
        },
        headers=auth_headers,
    )
    assert second_resp.status_code == 409
    assert first_loop_id in second_resp.json()["detail"]


@pytest.mark.asyncio
async def test_a_loop_can_still_be_created_with_no_source_document(app, auth_headers):
    """Task 4.2(c): `spec_document_id` stays optional, unchanged from `many-named-loops`."""
    from sqlalchemy import select

    from hub.db.engine import async_session_factory
    from hub.db.models import Loop

    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "No Document",
            "agent": "kimi",
            "message": "Work the queue",
            "cron": "0 9 * * *",
            "purpose": "No document declared",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201

    async with async_session_factory() as session:
        result = await session.execute(
            select(Loop).where(Loop.project_id == "proj-test", Loop.job_id == resp.json()["id"])
        )
        loop = result.scalar_one()
        assert loop.spec_document_id is None


@pytest.mark.asyncio
async def test_patch_declares_a_source_document_on_an_existing_loop(app, auth_headers):
    """`JobUpdate.spec_document_id` (task 4.1) lets an existing loop declare one after creation."""
    from sqlalchemy import select

    from hub.db.engine import async_session_factory
    from hub.db.models import Loop

    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Declares Later",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
            "purpose": "Undeclared for now",
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"spec_document_id": "doc-declare-later"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    async with async_session_factory() as session:
        result = await session.execute(
            select(Loop).where(Loop.project_id == "proj-test", Loop.job_id == job_id)
        )
        loop = result.scalar_one()
        assert loop.spec_document_id == "doc-declare-later"


@pytest.mark.asyncio
async def test_patch_declaring_a_claimed_document_is_refused(app, auth_headers):
    """PATCH mirrors create_job's 409 (task 4.1): the update path checks conflicts too."""
    holder_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Holder",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
            "purpose": "Holds doc-declare-3",
            "spec_document_id": "doc-declare-3",
        },
        headers=auth_headers,
    )
    holder_loop_id = holder_resp.json()["loop"]["id"]

    challenger_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Challenger",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
            "purpose": "Wants doc-declare-3 too",
        },
        headers=auth_headers,
    )
    challenger_id = challenger_resp.json()["id"]

    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{challenger_id}",
        json={"spec_document_id": "doc-declare-3"},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert holder_loop_id in resp.json()["detail"]


@pytest.mark.asyncio
async def test_patch_re_declaring_your_own_document_is_not_a_conflict(app, auth_headers):
    """A no-op re-declare of a loop's own document must not 409 against itself."""
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Re-declares Its Own",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
            "purpose": "Holds doc-declare-4",
            "spec_document_id": "doc-declare-4",
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"spec_document_id": "doc-declare-4"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Finding F1 — a cron restricting both day fields is refused at every write site
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("cron", ["0 0 15 * 5", "0 0 1 * 1", "0 0 */2 * MON"])
async def test_create_job_refuses_a_cron_restricting_both_day_fields(app, auth_headers, cron):
    """F1: `0 0 15 * 5` was accepted, stored with `next_run` 2026-08-28, and fired 2027-05-15.

    APScheduler ANDs day-of-month with day-of-week; croniter — which computes the `next_run` the
    card shows, and which matches every other crontab on the operator's machine — ORs them. The
    expression is valid to both libraries and means two different things, so it is refused rather
    than silently assigned one of the two readings.
    """
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={"name": "Ambiguous", "agent": "kimi", "message": "x", "cron": cron},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    # The refusal has to be actionable: it names both offending fields and the way out, because
    # "invalid cron" alone reads as a typo in a string that works everywhere else.
    assert "day-of-month" in detail and "day-of-week" in detail
    assert "two jobs" in detail

    listed = await app.get("/api/v1/projects/proj-test/jobs", headers=auth_headers)
    assert [j for j in listed.json() if j["cron"] == cron] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cron",
    [
        "0 9 * * *",  # neither day field restricted
        "0 9 * * 1-5",  # weekdays only — day-of-month is `*`
        "0 9 15 * *",  # the 15th — day-of-week is `*`
        "0 9 15 * 0-6",  # every weekday listed out is not a restriction
        "0 9 15 * 1-7",  # ...nor is 1-7, where 7 is Sunday again
    ],
)
async def test_create_job_still_accepts_every_unambiguous_cron(app, auth_headers, cron):
    """The refusal must be narrow. A validator that guessed would reject working schedules."""
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={"name": f"Fine {cron}", "agent": "kimi", "message": "x", "cron": cron},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["cron"] == cron


@pytest.mark.asyncio
async def test_update_job_refuses_a_cron_restricting_both_day_fields(app, auth_headers):
    """The same rule on the update path, or the expression walks in through the back door."""
    create_resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={"name": "Retimed", "agent": "kimi", "message": "x", "cron": "0 9 * * *"},
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"cron": "0 0 15 * 5"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "day-of-week" in resp.json()["detail"]

    # Refused before anything was written: the job keeps the schedule it had.
    after = await app.get(f"/api/v1/projects/proj-test/jobs/{job_id}", headers=auth_headers)
    assert after.json()["cron"] == "0 9 * * *"


# ---------------------------------------------------------------------------
# Finding F13 — re-enabling a loop that has already ended is refused, not undone
# ---------------------------------------------------------------------------


async def _ended_loop_job(app, auth_headers, *, name, ending_state, stop_reason):
    """A job whose loop has ended, in the state `_do_fire_job`'s stop branch leaves behind."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from hub.db.engine import async_session_factory
    from hub.db.models import AIJob, Loop

    create = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": name,
            "agent": "kimi",
            "message": "loop work",
            "cron": "0 9 * * *",
            "purpose": "a loop that finished",
            "stop_when_queue_empties": True,
        },
        headers=auth_headers,
    )
    assert create.status_code == 201, create.json()
    job_id = create.json()["id"]

    async with async_session_factory() as db:
        job = await db.get(AIJob, job_id)
        job.enabled = False
        loop = (await db.execute(select(Loop).where(Loop.job_id == job_id))).scalar_one()
        loop.ending_state = ending_state
        loop.stop_reason = stop_reason
        loop.stopped_at = datetime.now(timezone.utc)
        await db.commit()
    return job_id


@pytest.mark.asyncio
async def test_reenabling_a_finished_loop_is_refused(app, auth_headers):
    """F13: PATCH {"enabled": true} returned 200 on a loop carrying `ending_state: completed`.

    Measured 2026-08-23: the loop then read `enabled: true` alongside `stopped_at` and
    `stop_reason` for one minute, fired once more, re-stopped itself, and set `enabled` back to
    false — the operator's action silently undone, with only a history row to say why.
    """
    job_id = await _ended_loop_job(
        app,
        auth_headers,
        name="Finished Loop",
        ending_state="completed",
        stop_reason="loop queue is empty",
    )

    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "loop_ended"
    assert detail["ending_state"] == "completed"
    assert detail["stop_reason"] == "loop queue is empty"
    assert detail["stopped_at"] is not None
    # Says what to do instead. A new loop, not "give this one work": D12 closes an ended loop's
    # queue to every caller including the operator, so there is no way to feed this one.
    assert "Create a new loop" in detail["message"]

    after = await app.get(f"/api/v1/projects/proj-test/jobs/{job_id}", headers=auth_headers)
    assert after.json()["enabled"] is False


@pytest.mark.asyncio
async def test_a_loop_stopped_by_its_stop_at_also_refuses_re_enabling(app, auth_headers):
    """`completed` is not the only ending — a `stopped` loop is just as closed."""
    job_id = await _ended_loop_job(
        app,
        auth_headers,
        name="Timed Out Loop",
        ending_state="stopped",
        stop_reason="loop reached its stop time",
    )

    resp = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["ending_state"] == "stopped"


@pytest.mark.asyncio
async def test_a_merely_paused_loop_can_still_be_re_enabled(app, auth_headers):
    """The refusal turns on `ending_state`, not on `enabled`.

    D6 rejected a third "paused" state: a loop an operator disabled by hand leaves `ending_state`,
    `stop_reason` and `stopped_at` all NULL, and resuming it is ordinary. If this ever 409s, the
    fix for F13 has taken the pause button with it.
    """
    create = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Paused Loop",
            "agent": "kimi",
            "message": "loop work",
            "cron": "0 9 * * *",
            "purpose": "still going",
            "stop_when_queue_empties": True,
        },
        headers=auth_headers,
    )
    job_id = create.json()["id"]

    pause = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"enabled": False},
        headers=auth_headers,
    )
    assert pause.status_code == 200
    assert pause.json()["enabled"] is False

    resume = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert resume.status_code == 200
    assert resume.json()["enabled"] is True


@pytest.mark.asyncio
async def test_re_enabling_an_ordinary_job_is_untouched_by_the_loop_refusal(app, auth_headers):
    """A job with no `Loop` row at all never reaches the F13 check."""
    create = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Plain Job",
            "agent": "kimi",
            "message": "x",
            "cron": "0 9 * * *",
            "enabled": False,
        },
        headers=auth_headers,
    )
    job_id = create.json()["id"]

    resume = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert resume.status_code == 200
    assert resume.json()["enabled"] is True


# ---------------------------------------------------------------------------
# F28: a flow adopts the tasks already materialised from the document it claims
# ---------------------------------------------------------------------------


async def _task_rows(task_ids):
    from sqlalchemy import select

    from hub.db.engine import async_session_factory
    from hub.db.models import Task

    async with async_session_factory() as session:
        result = await session.execute(select(Task).where(Task.id.in_(task_ids)))
        return {row.id: row for row in result.scalars().all()}


async def _materialised_task(task_id: str, document_id: str, loop_id=None):
    """A task as `spec_tasks.materialise()` leaves it: carrying its document, and a loop only if
    one already claimed that document at the time."""
    from hub.db.engine import async_session_factory
    from hub.db.models import Task

    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                project_id="proj-test",
                title=f"Work {task_id}",
                status="pending",
                spec_document_id=document_id,
                loop_id=loop_id,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_a_flow_created_after_approval_adopts_the_documents_tasks(app, auth_headers):
    """The F28 reproduction. Approve first, build the flow second: the tasks exist with a null
    `loop_id`, and every queue query reads `Task.loop_id`, so the queue was empty forever."""
    await _materialised_task("task-f28-a", "doc-f28-after")
    await _materialised_task("task-f28-b", "doc-f28-after")

    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Built after approval",
            "agent": "kimi",
            "message": "Work the queue",
            "cron": "0 9 * * *",
            "purpose": "Drive doc-f28-after",
            "spec_document_id": "doc-f28-after",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    loop_id = resp.json()["loop"]["id"]

    rows = await _task_rows(["task-f28-a", "task-f28-b"])
    assert rows["task-f28-a"].loop_id == loop_id
    assert rows["task-f28-b"].loop_id == loop_id


@pytest.mark.asyncio
async def test_adoption_does_not_take_a_task_another_loop_already_owns(app, auth_headers):
    """Restricted to `loop_id IS NULL`. A task another flow is already driving keeps its owner."""
    await _materialised_task("task-f28-owned", "doc-f28-owned", loop_id="loop-someone-else")

    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Late claimer",
            "agent": "kimi",
            "message": "Work the queue",
            "cron": "0 9 * * *",
            "purpose": "Drive doc-f28-owned",
            "spec_document_id": "doc-f28-owned",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text

    rows = await _task_rows(["task-f28-owned"])
    assert rows["task-f28-owned"].loop_id == "loop-someone-else"


@pytest.mark.asyncio
async def test_a_flow_does_not_adopt_another_documents_tasks(app, auth_headers):
    """The claim is on one document, so adoption is too."""
    await _materialised_task("task-f28-other", "doc-f28-unrelated")

    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Claims its own document",
            "agent": "kimi",
            "message": "Work the queue",
            "cron": "0 9 * * *",
            "purpose": "Drive doc-f28-mine",
            "spec_document_id": "doc-f28-mine",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text

    rows = await _task_rows(["task-f28-other"])
    assert rows["task-f28-other"].loop_id is None


@pytest.mark.asyncio
async def test_claiming_a_document_by_patch_also_adopts_its_tasks(app, auth_headers):
    """A claim made by editing an existing loop reaches the same state as one made at creation."""
    await _materialised_task("task-f28-patch", "doc-f28-patched")

    created = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Claims later",
            "agent": "kimi",
            "message": "Work the queue",
            "cron": "0 9 * * *",
            "purpose": "Will name its document in a moment",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text

    patched = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{created.json()['id']}",
        json={"spec_document_id": "doc-f28-patched"},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text

    rows = await _task_rows(["task-f28-patch"])
    assert rows["task-f28-patch"].loop_id == created.json()["loop"]["id"]


# ---------------------------------------------------------------------------
# F33: a job that could only ever fail is not scheduled
# ---------------------------------------------------------------------------


async def _roster(*names):
    from hub.db.engine import async_session_factory
    from hub.db.models import Agent

    async with async_session_factory() as session:
        for name in names:
            session.add(Agent(id=f"agt-{name}", project_id="proj-test", name=name))
        await session.commit()


@pytest.mark.asyncio
async def test_a_job_naming_an_agent_not_on_the_roster_is_refused(app, auth_headers):
    """The F33 reproduction: `nobody` was accepted, enabled and scheduled, then failed every five
    minutes forever. The cron on this same route is refused at creation."""
    await _roster("realagent")

    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Ghost",
            "agent": "nobody",
            "message": "work",
            "cron": "*/5 * * * *",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "nobody" in detail
    assert "realagent" in detail


@pytest.mark.asyncio
async def test_a_job_naming_a_real_agent_is_created(app, auth_headers):
    await _roster("presentagent")

    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Real",
            "agent": "presentagent",
            "message": "work",
            "cron": "*/5 * * * *",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_a_project_with_no_known_agents_is_left_alone(app, auth_headers):
    """Deliberately not unconditional. Creating a job before the watchdog first syncs is the
    ordinary bootstrap order, and there is no roster to contradict."""
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Before any sync",
            "agent": "not-yet-registered",
            "message": "work",
            "cron": "*/5 * * * *",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_a_job_for_an_archived_agent_says_it_is_archived(app, auth_headers):
    """It exists, so "does not exist" would send the operator looking for the wrong thing."""
    from hub.db.engine import async_session_factory
    from hub.db.models import Agent

    async with async_session_factory() as session:
        session.add(
            Agent(
                id="agt-gone",
                project_id="proj-test",
                name="goneagent",
                lifecycle="archived",
            )
        )
        session.add(Agent(id="agt-here", project_id="proj-test", name="hereagent"))
        await session.commit()

    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "For an archived agent",
            "agent": "goneagent",
            "message": "work",
            "cron": "*/5 * * * *",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text
    assert "archived" in resp.json()["detail"]
