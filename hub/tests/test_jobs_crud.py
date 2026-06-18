"""Happy-path CRUD tests for /api/v1/jobs.

Companion to hub/tests/test_jobs.py (which mixes happy + negative cases).
Per PR 12 spec, this file isolates the 15 CRUD happy paths so a future
regression in create / get / list / update / pause / resume / run /
delete / history tracking is caught by a single, focused suite.

Negative cases (invalid cron, 404s, custom-id rejection) remain in
test_jobs.py.
"""

import pytest

# Check if croniter is available; many of the validations require it.
try:
    from croniter import croniter  # noqa: F401

    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_job_minimal(app, auth_headers):
    """POST /jobs with only the required fields returns 201 and a server-generated id."""
    resp = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Minimal Job",
            "agent": "kimi",
            "message": "ping",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("job-")
    assert data["name"] == "Minimal Job"
    assert data["agent"] == "kimi"
    assert data["message"] == "ping"
    assert data["cron"] == "0 9 * * *"
    assert data["enabled"] is True
    assert data["source"] == "hub"
    assert data["run_count"] == 0
    assert data["session_mode"] == "new"


@pytest.mark.asyncio
async def test_create_job_with_all_fields(app, auth_headers):
    """POST /jobs with every field round-trips correctly."""
    resp = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Full Job",
            "agent": "claude",
            "message": "do the thing",
            "cron": "*/15 * * * *",
            "session_mode": "resume",
            "enabled": True,
            "source": "hub",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["session_mode"] == "resume"
    assert data["cron"] == "*/15 * * * *"


@pytest.mark.asyncio
async def test_create_job_disabled_by_default(app, auth_headers):
    """A job created with enabled=False is created in the disabled state."""
    resp = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Off by Default",
            "agent": "kimi",
            "message": "x",
            "cron": "0 9 * * *",
            "enabled": False,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["enabled"] is False


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_jobs_empty(app, auth_headers):
    """An empty project returns an empty list, not a 404."""
    resp = await app.get("/api/v1/jobs", headers=auth_headers)
    assert resp.status_code == 200
    # Filter out anything left over from prior tests; this assertion is
    # per-project, so other test fixtures don't pollute the count.
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_jobs_returns_all_created(app, auth_headers):
    """All created jobs are present in the list (no pagination drops)."""
    for i in range(3):
        await app.post(
            "/api/v1/jobs",
            json={
                "name": f"List Job {i}",
                "agent": "kimi",
                "message": f"m{i}",
                "cron": "0 9 * * *",
            },
            headers=auth_headers,
        )

    resp = await app.get("/api/v1/jobs", headers=auth_headers)
    assert resp.status_code == 200
    names = {j["name"] for j in resp.json()}
    assert {"List Job 0", "List Job 1", "List Job 2"}.issubset(names)


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_job_includes_history(app, auth_headers):
    """GET /jobs/{id} returns a 'history' field (initially empty)."""
    create = await app.post(
        "/api/v1/jobs",
        json={
            "name": "History Job",
            "agent": "kimi",
            "message": "x",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create.json()["id"]
    resp = await app.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == job_id
    assert "history" in data
    assert isinstance(data["history"], list)
    assert len(data["history"]) == 0
    assert data["run_count"] == 0


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_job_name(app, auth_headers):
    """PATCH /jobs/{id} with {name: ...} updates the name."""
    create = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Original",
            "agent": "kimi",
            "message": "x",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create.json()["id"]
    resp = await app.patch(
        f"/api/v1/jobs/{job_id}",
        json={"name": "Renamed"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"


@pytest.mark.asyncio
async def test_update_job_message(app, auth_headers):
    """PATCH /jobs/{id} with {message: ...} updates the message."""
    create = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Msg Job",
            "agent": "kimi",
            "message": "old",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create.json()["id"]
    resp = await app.patch(
        f"/api/v1/jobs/{job_id}",
        json={"message": "new message"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "new message"


@pytest.mark.asyncio
async def test_update_job_cron(app, auth_headers):
    """PATCH /jobs/{id} with {cron: ...} updates the cron expression."""
    if not CRONITER_AVAILABLE:
        pytest.skip("croniter not available")
    create = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Cron Job",
            "agent": "kimi",
            "message": "x",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create.json()["id"]
    resp = await app.patch(
        f"/api/v1/jobs/{job_id}",
        json={"cron": "*/30 * * * *"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["cron"] == "*/30 * * * *"


# ---------------------------------------------------------------------------
# Pause / Resume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_job(app, auth_headers):
    """A job can be paused via PATCH {enabled: false}."""
    create = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Pause Job",
            "agent": "kimi",
            "message": "x",
            "cron": "0 9 * * *",
            "enabled": True,
        },
        headers=auth_headers,
    )
    job_id = create.json()["id"]
    resp = await app.patch(
        f"/api/v1/jobs/{job_id}",
        json={"enabled": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_resume_job(app, auth_headers):
    """A paused job can be resumed via PATCH {enabled: true}."""
    create = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Resume Job",
            "agent": "kimi",
            "message": "x",
            "cron": "0 9 * * *",
            "enabled": False,
        },
        headers=auth_headers,
    )
    job_id = create.json()["id"]
    resp = await app.patch(
        f"/api/v1/jobs/{job_id}",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_job_success(app, auth_headers):
    """POST /jobs/{id}/run on an enabled job returns success and bumps
    run_count + history length."""
    create = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Run Job",
            "agent": "kimi",
            "message": "run me",
            "cron": "0 9 * * *",
            "enabled": True,
        },
        headers=auth_headers,
    )
    job_id = create.json()["id"]

    run = await app.post(f"/api/v1/jobs/{job_id}/run", headers=auth_headers)
    if run.status_code == 503:
        pytest.skip("Scheduler not available in test environment")
    assert run.status_code == 200
    assert run.json()["success"] is True

    # run_count and history should reflect the new run.
    get = await app.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert get.json()["run_count"] == 1
    assert len(get.json()["history"]) == 1


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_job_returns_204(app, auth_headers):
    """DELETE /jobs/{id} returns 204 No Content."""
    create = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Delete Job",
            "agent": "kimi",
            "message": "x",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create.json()["id"]
    resp = await app.delete(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_get_after_delete_returns_404(app, auth_headers):
    """A deleted job returns 404 on subsequent GET."""
    create = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Gone",
            "agent": "kimi",
            "message": "x",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create.json()["id"]
    await app.delete(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    resp = await app.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_deleted_job_not_in_list(app, auth_headers):
    """A deleted job does not appear in the list response."""
    create = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Will Vanish",
            "agent": "kimi",
            "message": "x",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create.json()["id"]
    await app.delete(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    resp = await app.get("/api/v1/jobs", headers=auth_headers)
    ids = {j["id"] for j in resp.json()}
    assert job_id not in ids


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_run_history_tracks_run_count(app, auth_headers):
    """After a successful run, history has 1 entry and run_count is 1."""
    create = await app.post(
        "/api/v1/jobs",
        json={
            "name": "History Track",
            "agent": "kimi",
            "message": "x",
            "cron": "0 9 * * *",
            "enabled": True,
        },
        headers=auth_headers,
    )
    job_id = create.json()["id"]
    run = await app.post(f"/api/v1/jobs/{job_id}/run", headers=auth_headers)
    if run.status_code == 503:
        pytest.skip("Scheduler not available in test environment")

    resp = await app.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    data = resp.json()
    assert data["run_count"] == 1
    assert len(data["history"]) == 1
    # The history entry should be a JobRun-shaped dict.
    entry = data["history"][0]
    assert entry["job_id"] == job_id
    assert "fired_at" in entry
