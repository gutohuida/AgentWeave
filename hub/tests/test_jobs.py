"""Tests for job endpoints."""

import pytest

# Check if croniter is available
try:
    from croniter import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False


@pytest.mark.asyncio
async def test_create_job(app, auth_headers):
    """Test creating a new job."""
    resp = await app.post(
        "/api/v1/jobs",
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
        "/api/v1/jobs",
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
        "/api/v1/jobs",
        json={
            "name": "Job 1",
            "agent": "kimi",
            "message": "Message 1",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    await app.post(
        "/api/v1/jobs",
        json={
            "name": "Job 2",
            "agent": "claude",
            "message": "Message 2",
            "cron": "0 10 * * *",
        },
        headers=auth_headers,
    )

    resp = await app.get("/api/v1/jobs", headers=auth_headers)
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
        "/api/v1/jobs",
        json={
            "name": "Get Job",
            "agent": "kimi",
            "message": "Get me",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    resp = await app.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == job_id
    assert data["name"] == "Get Job"
    assert data["history"] is not None  # Should include history


@pytest.mark.asyncio
async def test_get_job_not_found(app, auth_headers):
    """Test getting a non-existent job."""
    resp = await app.get("/api/v1/jobs/job-nonexistent123", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_job(app, auth_headers):
    """Test updating a job."""
    create_resp = await app.post(
        "/api/v1/jobs",
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
        f"/api/v1/jobs/{job_id}",
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
        "/api/v1/jobs",
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
        f"/api/v1/jobs/{job_id}",
        json={"cron": "bad cron"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_pause_and_resume_job(app, auth_headers):
    """Test pausing and resuming a job."""
    create_resp = await app.post(
        "/api/v1/jobs",
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
        f"/api/v1/jobs/{job_id}",
        json={"enabled": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    # Resume the job
    resp = await app.patch(
        f"/api/v1/jobs/{job_id}",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


@pytest.mark.asyncio
async def test_delete_job(app, auth_headers):
    """Test deleting a job."""
    create_resp = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Delete Job",
            "agent": "kimi",
            "message": "Delete me",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    # Delete the job
    resp = await app.delete(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Verify it's gone
    get_resp = await app.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_run_job_disabled(app, auth_headers):
    """Test running a disabled job fails."""
    create_resp = await app.post(
        "/api/v1/jobs",
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
    resp = await app.post(f"/api/v1/jobs/{job_id}/run", headers=auth_headers)
    assert resp.status_code == 400
    assert "disabled" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_run_job_not_found(app, auth_headers):
    """Test running a non-existent job."""
    resp = await app.post("/api/v1/jobs/job-nonexistent/run", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_job_with_custom_id(app, auth_headers):
    """Test creating a job with a custom ID."""
    resp = await app.post(
        "/api/v1/jobs",
        json={
            "id": "my-custom-job-id",
            "name": "Custom ID Job",
            "agent": "kimi",
            "message": "Test",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == "my-custom-job-id"


@pytest.mark.asyncio
async def test_duplicate_job_id(app, auth_headers):
    """Test creating a job with duplicate ID fails."""
    # Create first job
    resp1 = await app.post(
        "/api/v1/jobs",
        json={
            "id": "duplicate-job-id",
            "name": "First",
            "agent": "kimi",
            "message": "First",
            "cron": "0 9 * * *",
        },
        headers=auth_headers,
    )
    assert resp1.status_code == 201

    # Try to create another with same ID
    resp2 = await app.post(
        "/api/v1/jobs",
        json={
            "id": "duplicate-job-id",
            "name": "Second",
            "agent": "claude",
            "message": "Second",
            "cron": "0 10 * * *",
        },
        headers=auth_headers,
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_job_source_field(app, auth_headers):
    """Test that source field is set correctly."""
    # Default should be "hub"
    resp = await app.post(
        "/api/v1/jobs",
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
        "/api/v1/jobs",
        json={
            "id": "local-job-test",
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
        "/api/v1/jobs",
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
        "/api/v1/jobs",
        json={
            "id": "resume-job-test",
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
        "/api/v1/jobs",
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
    run_resp = await app.post(f"/api/v1/jobs/{job_id}/run", headers=auth_headers)
    
    # If scheduler not available, skip this test
    if run_resp.status_code == 503:
        pytest.skip("Scheduler not available in test environment")
    
    # Should succeed
    assert run_resp.status_code == 200
    assert run_resp.json()["success"] is True

    # Check that run_count increased
    get_resp = await app.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert get_resp.json()["run_count"] == 1
    assert len(get_resp.json()["history"]) == 1


@pytest.mark.asyncio
async def test_update_job_not_found(app, auth_headers):
    """Test updating a non-existent job."""
    resp = await app.patch(
        "/api/v1/jobs/job-nonexistent",
        json={"name": "New Name"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_job_not_found(app, auth_headers):
    """Test deleting a non-existent job."""
    resp = await app.delete("/api/v1/jobs/job-nonexistent", headers=auth_headers)
    assert resp.status_code == 404
