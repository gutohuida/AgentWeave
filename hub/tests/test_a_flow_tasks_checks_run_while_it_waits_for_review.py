"""F773 -- a flow task's checks run at the end of its turn, on the commit its review will be given.

Where evidence governs, `task_integration.merge_targets` names accepted evidence only, and a task
just completed has awaiting evidence, so `request_run` found no target and started nothing: the
reviewer judged without a result, and its approval was first refused "checks are still running".
Real git and real check subprocesses, as in `test_project_checks_run.py`.
"""

import pytest

from hub import project_checks
from hub.db.engine import async_session_factory
from hub.db.models import Loop, Run

from .review_evidence import record_review_evidence
from .test_project_checks_run import PASS, _project, _runs, _task_with_work

pytestmark = pytest.mark.asyncio


async def _flow_task(tmp_path):
    """A completed task whose loop's work needs evidence, with one awaiting piece naming its tip."""
    task_id, work = await _task_with_work(tmp_path)
    async with async_session_factory() as session:
        (await session.get(Loop, "loop-checks")).work_needs_evidence = True
        await record_review_evidence(session, task_id, suffix="f773", commit_sha=work)
        session.add(
            Run(
                id="run-f773000001",
                project_id="proj-test",
                agent="builder",
                status="completed",
                turn_depth=0,
                task_id=task_id,
            )
        )
        await session.commit()
    return task_id, work


async def test_a_completed_flow_tasks_checks_run_at_its_turns_end(app, tmp_path):
    task_id, work = await _flow_task(tmp_path)
    await _project([PASS])

    project_checks.after_run("proj-test", "run-f773000001")
    await project_checks.drain()

    [run] = await _runs(task_id)
    assert run.state == "passed"
    assert run.target_shas == [work], "the commit the review is given"


async def test_a_flow_task_with_no_evidence_naming_a_commit_is_still_not_checked(app, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    async with async_session_factory() as session:
        (await session.get(Loop, "loop-checks")).work_needs_evidence = True
        session.add(
            Run(
                id="run-f773000002",
                project_id="proj-test",
                agent="builder",
                status="completed",
                turn_depth=0,
                task_id=task_id,
            )
        )
        await session.commit()
    await _project([PASS])

    project_checks.after_run("proj-test", "run-f773000002")
    await project_checks.drain()

    assert await _runs(task_id) == []
