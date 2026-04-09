"""Tests for agentweave.jobs module."""

import pytest
from datetime import datetime, timedelta
from agentweave.jobs import Job, JobRun, CRONITER_AVAILABLE


class TestJobRun:
    """Tests for JobRun dataclass."""

    def test_job_run_creation(self):
        run = JobRun(
            id="run-abc123",
            job_id="job-xyz789",
            fired_at="2024-01-15T09:00:00",
            status="fired",
            trigger="scheduled",
            session_id="sess-001",
        )
        assert run.id == "run-abc123"
        assert run.job_id == "job-xyz789"
        assert run.status == "fired"
        assert run.trigger == "scheduled"
        assert run.session_id == "sess-001"

    def test_job_run_to_dict(self):
        run = JobRun(
            id="run-abc123",
            job_id="job-xyz789",
            fired_at="2024-01-15T09:00:00",
            status="fired",
            trigger="manual",
        )
        d = run.to_dict()
        assert d["id"] == "run-abc123"
        assert d["job_id"] == "job-xyz789"
        assert d["status"] == "fired"
        assert d["trigger"] == "manual"
        assert d["session_id"] is None

    def test_job_run_from_dict(self):
        data = {
            "id": "run-abc123",
            "job_id": "job-xyz789",
            "fired_at": "2024-01-15T09:00:00",
            "status": "failed",
            "trigger": "scheduled",
            "session_id": "sess-002",
        }
        run = JobRun.from_dict(data)
        assert run.id == "run-abc123"
        assert run.status == "failed"
        assert run.session_id == "sess-002"


class TestJob:
    """Tests for Job dataclass."""

    def test_job_creation_defaults(self):
        job = Job(
            id="job-test123",
            name="Test Job",
            agent="kimi",
            message="Test message",
            cron="0 9 * * *",
        )
        assert job.id == "job-test123"
        assert job.name == "Test Job"
        assert job.agent == "kimi"
        assert job.message == "Test message"
        assert job.cron == "0 9 * * *"
        assert job.session_mode == "new"
        assert job.enabled is True
        assert job.source == "local"
        assert job.synced is False
        assert job.run_count == 0

    def test_job_creation_custom(self):
        job = Job(
            id="job-test456",
            name="Custom Job",
            agent="claude",
            message="Custom message",
            cron="0 */6 * * *",
            session_mode="resume",
            enabled=False,
            source="hub",
            synced=True,
            last_session_id="sess-prev",
        )
        assert job.session_mode == "resume"
        assert job.enabled is False
        assert job.source == "hub"
        assert job.synced is True
        assert job.last_session_id == "sess-prev"

    def test_job_to_dict(self):
        job = Job(
            id="job-test789",
            name="Dict Test",
            agent="minimax",
            message="Test",
            cron="0 0 * * 0",
        )
        d = job.to_dict()
        assert d["id"] == "job-test789"
        assert d["name"] == "Dict Test"
        assert d["agent"] == "minimax"
        assert d["cron"] == "0 0 * * 0"
        assert d["session_mode"] == "new"
        assert d["enabled"] is True
        assert d["source"] == "local"

    def test_job_from_dict(self):
        data = {
            "id": "job-from-dict",
            "name": "From Dict",
            "agent": "kimi",
            "message": "Loaded from dict",
            "cron": "0 12 * * 1-5",
            "session_mode": "resume",
            "enabled": False,
            "created_at": "2024-01-01T00:00:00",
            "last_run": "2024-01-10T12:00:00",
            "next_run": "2024-01-11T12:00:00",
            "run_count": 5,
            "source": "hub",
            "synced": True,
            "last_session_id": "sess-123",
        }
        job = Job.from_dict(data)
        assert job.id == "job-from-dict"
        assert job.session_mode == "resume"
        assert job.enabled is False
        assert job.run_count == 5
        assert job.source == "hub"
        assert job.synced is True
        assert job.last_session_id == "sess-123"

    def test_job_from_dict_defaults(self):
        """Test that missing fields get default values."""
        data = {
            "id": "job-minimal",
            "name": "Minimal",
            "agent": "claude",
            "message": "Minimal job",
            "cron": "0 9 * * *",
        }
        job = Job.from_dict(data)
        assert job.session_mode == "new"  # default
        assert job.enabled is True  # default
        assert job.source == "local"  # default
        assert job.synced is False  # default
        assert job.run_count == 0  # default


class TestJobValidation:
    """Tests for job validation."""

    def test_validate_cron_valid(self):
        if not CRONITER_AVAILABLE:
            pytest.skip("croniter not available")
        
        # Should not raise
        Job.validate_cron("0 9 * * *")
        Job.validate_cron("*/5 * * * *")
        Job.validate_cron("0 0 * * 0")

    def test_validate_cron_invalid(self):
        if not CRONITER_AVAILABLE:
            pytest.skip("croniter not available")
        
        with pytest.raises(ValueError, match="Invalid cron"):
            Job.validate_cron("invalid")
        with pytest.raises(ValueError, match="Invalid cron"):
            Job.validate_cron("* * * *")
        with pytest.raises(ValueError, match="Invalid cron"):
            Job.validate_cron("abc")

    def test_validate_cron_without_croniter(self, monkeypatch):
        """Test that validation fails gracefully without croniter."""
        monkeypatch.setattr("agentweave.jobs.CRONITER_AVAILABLE", False)
        with pytest.raises(ValueError, match="croniter is required"):
            Job.validate_cron("0 9 * * *")


class TestJobPersistence:
    """Tests for job save/load/delete."""

    def test_job_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        job = Job(
            id="job-persist",
            name="Persist Test",
            agent="kimi",
            message="Test persistence",
            cron="0 9 * * *",
        )
        assert job.save() is True

        loaded = Job.load("job-persist")
        assert loaded is not None
        assert loaded.id == "job-persist"
        assert loaded.name == "Persist Test"
        assert loaded.agent == "kimi"

    def test_job_load_not_found(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        loaded = Job.load("job-nonexistent")
        assert loaded is None

    def test_job_load_invalid_id(self, tmp_path, monkeypatch):
        """Test that path traversal attempts are blocked."""
        monkeypatch.chdir(tmp_path)
        loaded = Job.load("../../../etc/passwd")
        assert loaded is None
        loaded = Job.load("job-with/../traversal")
        assert loaded is None

    def test_job_list_all(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        
        # Create some jobs
        job1 = Job(id="job-1", name="Job 1", agent="kimi", message="M1", cron="0 9 * * *")
        job2 = Job(id="job-2", name="Job 2", agent="claude", message="M2", cron="0 10 * * *")
        job3 = Job(id="job-3", name="Job 3", agent="kimi", message="M3", cron="0 11 * * *")
        job1.save()
        job2.save()
        job3.save()

        # List all
        all_jobs = Job.list_all()
        assert len(all_jobs) == 3

        # Filter by agent
        kimi_jobs = Job.list_all(agent="kimi")
        assert len(kimi_jobs) == 2
        assert all(j.agent == "kimi" for j in kimi_jobs)

        claude_jobs = Job.list_all(agent="claude")
        assert len(claude_jobs) == 1
        assert claude_jobs[0].agent == "claude"

    def test_job_delete(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        job = Job(id="job-delete", name="Delete Me", agent="kimi", message="Delete", cron="0 9 * * *")
        job.save()
        
        # Verify it exists
        assert Job.load("job-delete") is not None
        
        # Delete it
        assert job.delete() is True
        
        # Verify it's gone
        assert Job.load("job-delete") is None


class TestJobShouldFire:
    """Tests for the should_fire logic."""

    def test_should_fire_disabled_job(self):
        job = Job(
            id="job-disabled",
            name="Disabled",
            agent="kimi",
            message="Test",
            cron="* * * * *",
            enabled=False,
        )
        assert job.should_fire() is False

    def test_should_fire_no_croniter(self, monkeypatch):
        monkeypatch.setattr("agentweave.jobs.CRONITER_AVAILABLE", False)
        job = Job(
            id="job-nocron",
            name="No Croniter",
            agent="kimi",
            message="Test",
            cron="* * * * *",
            enabled=True,
        )
        assert job.should_fire() is False

    @pytest.mark.skipif(not CRONITER_AVAILABLE, reason="croniter not available")
    def test_should_fire_with_recent_last_run(self):
        """Test fire guard prevents double-firing."""
        # Create a job that just ran
        recent_run = (datetime.now() - timedelta(seconds=30)).isoformat()
        job = Job(
            id="job-recent",
            name="Recent Run",
            agent="kimi",
            message="Test",
            cron="* * * * *",  # Every minute
            enabled=True,
            last_run=recent_run,
        )
        # Should NOT fire because last_run was < 50 seconds ago
        assert job.should_fire() is False

    @pytest.mark.skipif(not CRONITER_AVAILABLE, reason="croniter not available")
    def test_should_fire_old_last_run(self, monkeypatch):
        """Test job fires when last run was long ago."""
        from datetime import datetime as dt
        
        # Mock datetime.now() to a known minute boundary (10:00:00)
        mock_now = dt(2024, 1, 15, 10, 0, 0)
        
        class MockDateTime:
            @classmethod
            def now(cls, tz=None):
                return mock_now
            
            @classmethod
            def fromisoformat(cls, s):
                return dt.fromisoformat(s)
        
        monkeypatch.setattr("agentweave.jobs.datetime", MockDateTime)
        
        # Create a job that ran 5 minutes ago (at 9:55:00)
        old_run = (mock_now - timedelta(minutes=5)).isoformat()
        job = Job(
            id="job-old",
            name="Old Run",
            agent="kimi",
            message="Test",
            cron="* * * * *",  # Every minute
            enabled=True,
            last_run=old_run,
        )
        # Should fire because last_run was > 50 seconds ago and we're at minute boundary
        assert job.should_fire() is True


class TestJobRecordRun:
    """Tests for recording job runs."""

    def test_record_run_updates_stats(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        job = Job(
            id="job-record",
            name="Record Test",
            agent="kimi",
            message="Test",
            cron="0 9 * * *",
            run_count=0,
        )
        job.save()

        run = job.record_run(status="fired", trigger="manual", session_id="sess-test")
        
        assert run.job_id == job.id
        assert run.status == "fired"
        assert run.trigger == "manual"
        assert run.session_id == "sess-test"
        
        # Job stats should be updated
        assert job.run_count == 1
        assert job.last_session_id == "sess-test"
        assert job.last_run is not None


class TestJobCreate:
    """Tests for Job.create factory method."""

    @pytest.mark.skipif(not CRONITER_AVAILABLE, reason="croniter not available")
    def test_create_valid_job(self):
        job = Job.create(
            name="Factory Job",
            agent="kimi",
            message="Created via factory",
            cron="0 9 * * *",
        )
        assert job.name == "Factory Job"
        assert job.agent == "kimi"
        assert job.cron == "0 9 * * *"
        assert job.id.startswith("job-")
        assert job.enabled is True
        assert job.next_run is not None  # Should be computed

    @pytest.mark.skipif(not CRONITER_AVAILABLE, reason="croniter not available")
    def test_create_with_session_mode(self):
        job = Job.create(
            name="Resume Job",
            agent="claude",
            message="Resume mode test",
            cron="0 10 * * *",
            session_mode="resume",
        )
        assert job.session_mode == "resume"

    def test_create_invalid_cron(self):
        if not CRONITER_AVAILABLE:
            pytest.skip("croniter not available")
        with pytest.raises(ValueError, match="Invalid cron"):
            Job.create(
                name="Bad Cron",
                agent="kimi",
                message="Test",
                cron="invalid cron",
            )

    @pytest.mark.skipif(not CRONITER_AVAILABLE, reason="croniter not available")
    def test_create_invalid_session_mode_defaults_to_new(self):
        """Invalid session_mode should default to 'new'."""
        job = Job.create(
            name="Invalid Mode",
            agent="kimi",
            message="Test",
            cron="0 9 * * *",
            session_mode="invalid_mode",
        )
        assert job.session_mode == "new"


class TestJobComputeNextRun:
    """Tests for compute_next_run."""

    @pytest.mark.skipif(not CRONITER_AVAILABLE, reason="croniter not available")
    def test_compute_next_run_daily(self):
        job = Job(
            id="job-next",
            name="Next Run",
            agent="kimi",
            message="Test",
            cron="0 9 * * *",  # Daily at 9am
        )
        next_run = job.compute_next_run()
        assert next_run is not None
        # Should be a valid ISO timestamp
        dt = datetime.fromisoformat(next_run)
        assert dt.hour == 9
        assert dt.minute == 0

    def test_compute_next_run_no_croniter(self, monkeypatch):
        monkeypatch.setattr("agentweave.jobs.CRONITER_AVAILABLE", False)
        job = Job(
            id="job-no-croniter",
            name="No Croniter",
            agent="kimi",
            message="Test",
            cron="0 9 * * *",
        )
        assert job.compute_next_run() is None

    def test_compute_next_run_invalid_cron(self):
        if not CRONITER_AVAILABLE:
            pytest.skip("croniter not available")
        job = Job(
            id="job-invalid-cron",
            name="Invalid Cron",
            agent="kimi",
            message="Test",
            cron="not a cron expression",
        )
        assert job.compute_next_run() is None
