"""A project's could-not-run notices are read without decoding every run's results
(`screens-stop-repeating-work-on-every-read`, FR-3): only runs whose results name the word are
candidates, and the rest are read newest first until each candidate's newest result is found. The
notices stay what they were: one per check whose newest finished result could not run.
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub import project_checks
from hub.db.engine import async_session_factory
from hub.db.models import TaskCheckRun

pytestmark = pytest.mark.asyncio

TASKS = "/api/v1/projects/proj-test/tasks"
T0 = datetime(2026, 11, 28, 9, 0, tzinfo=timezone.utc)


def _result(name, **extra):
    return {"name": name, "exit_code": 0, "timed_out": False, **extra}


def _could_not(name):
    return _result(name, exit_code=1, outcome="could_not_run", missing_program="eslint")


async def _run(task_id, run_id, minutes, results, state="passed"):
    async with async_session_factory() as db:
        db.add(
            TaskCheckRun(
                id=run_id,
                project_id="proj-test",
                task_id=task_id,
                main_sha="a" * 40,
                target_shas=["b" * 40],
                state=state,
                results=results,
                started_at=T0 + timedelta(minutes=minutes),
                ended_at=T0 + timedelta(minutes=minutes + 1),
            )
        )
        await db.commit()


async def _notices():
    async with async_session_factory() as db:
        return await project_checks.could_not_run_notices(db, "proj-test")


async def test_notices_follow_each_checks_newest_result_past_one_batch(app, auth_headers):
    created = await app.post(TASKS, json={"title": "Checks"}, headers=auth_headers)
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    batch = project_checks._NOTICE_SCAN_BATCH

    # `ui` could not run long ago and passed later; `lint` could not run in the newest run.
    await _run(task_id, "chk-0", 0, [_could_not("ui"), _result("lint")], state="failed")
    await _run(task_id, "chk-1", 1, [_result("ui"), _result("lint")])
    # Many runs since that skip `ui` and mention the word only in output text.
    for i in range(2, batch * 2 + 2):
        await _run(
            task_id,
            f"chk-{i}",
            i,
            [
                _result("ui", skipped=True),
                _result("lint", output_tail="test_could_not_run_is_said ... ok"),
            ],
        )
    assert await _notices() == []

    last = batch * 2 + 3
    await _run(task_id, "chk-last", last, [_result("ui", skipped=True), _could_not("lint")])
    [notice] = await _notices()
    assert notice["check"] == "lint" and notice["program"] == "eslint"
    assert notice["source"] == "task"
    assert notice["at"] == (T0 + timedelta(minutes=last + 1)).isoformat()

    # `ui`'s only could-not-run is older than its pass, more than a batch back: still no notice.
    await _run(task_id, "chk-ui", last + 1, [_result("lint")])
    assert await _notices() == []
