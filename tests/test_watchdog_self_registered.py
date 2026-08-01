"""Tests for watchdog self-registration guard.

`_trigger_agent_from_message` (the HTTP-transport message-scanning auto-trigger) was
removed in task 3.10 — scheduled jobs now fire through the Hub's direct execution path
(`hub/hub/scheduler.py`'s `_job_agent_skip_reason`/`_do_fire_job`, tested in
`hub/tests/test_scheduler.py`) instead of writing a synthetic Hub message for the watchdog
to detect and re-trigger. The two tests that exercised that removed method directly
(pilot-mode and self-registered-poll skip guards for message-triggered execution) were
deleted along with it; their Hub-side equivalents live in `hub/tests/test_scheduler.py`.
This file's remaining test below covers a different, still-live code path: `_fire_job`,
the local/git-transport "timer duties" job-firing the watchdog keeps per task 3.10's own
wording, unaffected by this task.
"""

from unittest.mock import MagicMock


def test_watchdog_job_skips_self_registered_poll_agent(tmp_path, monkeypatch):
    """Scheduled jobs should skip self-registered poll agents."""
    from agentweave import watchdog as wd
    from agentweave.jobs import Job

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Job, "validate_cron", staticmethod(lambda cron: None))

    transport = MagicMock()
    transport.get_transport_type.return_value = "http"
    transport.get_agent_registration.return_value = {
        "self_registered": True,
        "contact_mode": "poll",
    }

    dog = wd.Watchdog(transport=transport)

    job = Job.create(name="Test Job", agent="hermes", message="Hello", cron="0 0 * * *")

    monkeypatch.setattr(wd, "_check_cli_available", lambda agent: True)

    result = dog._fire_job(job, trigger="manual")

    assert result is False, "Should skip firing job for self-registered poll agent"
