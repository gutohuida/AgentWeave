"""A job written as enabled must actually reach the scheduler.

APScheduler's job store is a *separate synchronous engine* pointed at the same SQLite file. While
the request that just wrote the job still holds a transaction open, that store cannot take the
write lock, and its insert fails with `database is locked` — caught inside `JobScheduler.add_job`,
logged, and returned as a `False` no caller read. The row stayed `enabled = 1` in `ai_jobs` with
nothing in `apscheduler_jobs`: a loop the operator had just armed, that would not fire until the
Hub restarted and `start()` loaded it from the database.

Measured live on the trial Hub. Creating an enabled loop *with* `initial_tasks` reproduced it every
time; the same loop without them registered fine, because seeding the queue is what leaves the
session mid-transaction. So the fact under test is not "the scheduler was called" — it always was —
but **the state the session was in when it was called**, which is the only thing that decides
whether the store can write.
"""

import pytest

pytestmark = pytest.mark.asyncio


class _RecordingScheduler:
    """Stands in for `JobScheduler` and records what the session looked like at handoff."""

    def __init__(self, session_holder):
        self._session_holder = session_holder
        self.added: list[str] = []
        self.removed: list[str] = []
        self.in_transaction_at_handoff: list[bool] = []

    def _snapshot(self):
        session = self._session_holder()
        self.in_transaction_at_handoff.append(session is not None and session.in_transaction())

    async def add_job(self, job):
        self._snapshot()
        self.added.append(job.id)
        return True

    async def remove_job(self, job_id):
        self._snapshot()
        self.removed.append(job_id)
        return True

    async def update_job(self, job):  # pragma: no cover - the route no longer calls this
        raise AssertionError("update_job is not the handoff path any more")


@pytest.fixture
def recording_scheduler(monkeypatch):
    import hub.api.v1.jobs as jobs_module
    import hub.scheduler as scheduler_module

    holder = {"session": None}
    instance = _RecordingScheduler(lambda: holder["session"])
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: instance)

    original = jobs_module._hand_job_to_scheduler

    async def _capture(session, job_id, job=None):
        holder["session"] = session
        return await original(session, job_id, job)

    monkeypatch.setattr(jobs_module, "_hand_job_to_scheduler", _capture)
    return instance


async def test_an_enabled_loop_seeded_with_tasks_is_handed_over_with_no_open_transaction(
    app, auth_headers, recording_scheduler
):
    """The reproduction. `initial_tasks` is what leaves the transaction open."""
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Armed Loop",
            "agent": "kimi",
            "message": "work the queue",
            "cron": "*/5 * * * *",
            "enabled": True,
            "purpose": "fire on a schedule",
            "stop_when_queue_empties": True,
            "initial_tasks": [{"title": "opening work"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    job_id = resp.json()["id"]

    assert recording_scheduler.added == [job_id]
    assert recording_scheduler.in_transaction_at_handoff == [False]


async def test_a_bare_enabled_job_is_handed_over_with_no_open_transaction(
    app, auth_headers, recording_scheduler
):
    """The case that always worked, kept so the fix cannot regress it into the broken one."""
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Plain Job",
            "agent": "kimi",
            "message": "ping",
            "cron": "0 9 * * *",
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text

    assert recording_scheduler.added == [resp.json()["id"]]
    assert recording_scheduler.in_transaction_at_handoff == [False]


async def test_a_job_created_disabled_is_not_registered(app, auth_headers, recording_scheduler):
    """Handing over is not the same as arming: a disabled job must not be added.

    It is still *handed over* — the helper reconciles the scheduler to the row rather than
    branching on how the row got there, so a disabled job produces an unregister that has nothing
    to unregister. That is idempotent and deliberate: one contract, no site deciding for itself
    which half of it applies.
    """
    resp = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Idle Job",
            "agent": "kimi",
            "message": "ping",
            "cron": "0 9 * * *",
            "enabled": False,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert recording_scheduler.added == []
    assert recording_scheduler.in_transaction_at_handoff == [False]


async def test_enabling_and_disabling_a_job_both_hand_over_cleanly(
    app, auth_headers, recording_scheduler
):
    """The update route registers on enable and unregisters on disable, both after committing."""
    created = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Toggled Job",
            "agent": "kimi",
            "message": "ping",
            "cron": "0 9 * * *",
            "enabled": False,
        },
        headers=auth_headers,
    )
    job_id = created.json()["id"]

    enabled = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert enabled.status_code == 200, enabled.text
    assert recording_scheduler.added == [job_id]
    # The create call reconciled first; only the enable added.
    assert recording_scheduler.removed == [job_id]

    disabled = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"enabled": False},
        headers=auth_headers,
    )
    assert disabled.status_code == 200, disabled.text
    assert recording_scheduler.removed == [job_id, job_id]
    assert recording_scheduler.in_transaction_at_handoff == [False, False, False]


async def test_archiving_a_job_unregisters_it_with_no_open_transaction(
    app, auth_headers, recording_scheduler
):
    """Archiving is the third handoff site and had the same swallow around it."""
    created = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Archivable Job",
            "agent": "kimi",
            "message": "ping",
            "cron": "0 9 * * *",
            "enabled": True,
        },
        headers=auth_headers,
    )
    job_id = created.json()["id"]

    archived = await app.post(
        f"/api/v1/projects/proj-test/jobs/{job_id}/archive", headers=auth_headers
    )
    assert archived.status_code == 200, archived.text
    assert recording_scheduler.removed == [job_id]
    assert recording_scheduler.in_transaction_at_handoff == [False, False]


async def test_stopping_a_loop_unregisters_its_job(app, auth_headers, recording_scheduler):
    """An ending clears `job.enabled`, and a job left registered keeps firing whatever the row says.

    This is the same defect as the create-time one wearing different clothes: the database says the
    loop is over and the scheduler has never been told. Nothing in `test_an_operator_stop_actually
    _stops.py` can see it — that file reads rows, and the row is already right.
    """
    created = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Stoppable Loop",
            "agent": "kimi",
            "message": "work the queue",
            "cron": "*/5 * * * *",
            "enabled": True,
            "purpose": "keep going",
            "stop_when_queue_empties": True,
        },
        headers=auth_headers,
    )
    job_id = created.json()["id"]
    assert recording_scheduler.added == [job_id]

    stopped = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"stop_reason": "that is enough for tonight"},
        headers=auth_headers,
    )
    assert stopped.status_code == 200, stopped.text
    assert recording_scheduler.removed == [job_id]
    assert recording_scheduler.in_transaction_at_handoff == [False, False]


async def test_editing_a_loop_that_is_still_running_does_not_unregister_it(
    app, auth_headers, recording_scheduler
):
    """The other direction: an edit is not an ending, and must not pull the job off the schedule."""
    created = await app.post(
        "/api/v1/projects/proj-test/jobs",
        json={
            "name": "Edited Loop",
            "agent": "kimi",
            "message": "work the queue",
            "cron": "*/5 * * * *",
            "enabled": True,
            "purpose": "keep going",
            "stop_when_queue_empties": True,
        },
        headers=auth_headers,
    )
    job_id = created.json()["id"]

    edited = await app.patch(
        f"/api/v1/projects/proj-test/jobs/{job_id}",
        json={"purpose": "keep going, more carefully"},
        headers=auth_headers,
    )
    assert edited.status_code == 200, edited.text
    assert recording_scheduler.removed == []
    assert recording_scheduler.added == [job_id]
