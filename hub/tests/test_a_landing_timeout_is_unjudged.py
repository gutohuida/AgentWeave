"""A landing batch whose check ran out of time judged nothing, and a batch that ends closes its
check run (F1133, F1134).

The seams: `_decide` (the narrowing decision) over a `run_batch_checks` result, and `_record_landed`
(the batch-land path). Real git for the checked tree; the check itself is a stub result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest
from sqlalchemy import select

from hub import landing_queue, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import LandingBatch, Project, Task, TaskCheckRun, TaskLanding

from .test_task_integration import git, make_repo, set_main_branch

pytestmark = pytest.mark.asyncio

CHECK = {"name": "ruff", "command": "ruff check .", "timeout_seconds": 120}


def _result(**fields: Any) -> Dict[str, Any]:
    base = {
        "name": "ruff",
        "exit_code": None,
        "timed_out": True,
        "named_failures": [],
        "output": "All checks passed!",
        "skipped": False,
    }
    base.update(fields)
    return base


async def _rows(n: int = 1) -> List[TaskLanding]:
    ids = [f"task-f11310000{k:03d}" for k in range(1, n + 1)]
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.checks = [CHECK]
        for task_id in ids:
            session.add(
                Task(
                    id=task_id,
                    project_id="proj-test",
                    title=task_id,
                    description="",
                    status="approved",
                    assignee="builder",
                )
            )
        await session.flush()
        for k, task_id in enumerate(ids, start=1):
            session.add(
                TaskLanding(
                    id=f"land-f1131{k:03d}",
                    project_id="proj-test",
                    task_id=task_id,
                    state="checking",
                    order_key=float(k),
                    targets=[],
                )
            )
        await session.commit()
        return [await session.get(TaskLanding, f"land-f1131{k:03d}") for k in range(1, n + 1)]


async def _batch(batch_id: str, base: str, landings, **fields: Any) -> None:
    async with async_session_factory() as session:
        session.add(
            LandingBatch(
                id=batch_id,
                project_id="proj-test",
                base_sha=base,
                state="checking",
                task_ids=[landing.task_id for landing in landings],
                prefixes=[base for _ in landings],
                merged_sha=base,
                results=[],
                narrowing=[],
                **fields,
            )
        )
        await session.commit()
        for landing in landings:
            row = await session.get(TaskLanding, landing.id)
            row.batch_id = batch_id
        await session.commit()


@pytest.fixture
def forbid_blame(monkeypatch):
    async def boom(*args, **kwargs):
        raise AssertionError("an unjudged timeout was narrowed or blamed on a task")

    monkeypatch.setattr(landing_queue, "_narrow", boom)
    monkeypatch.setattr(landing_queue, "_send_back", boom)


async def _run_and_decide(tmp_path: Path, monkeypatch, batch_id: str, landings, result):
    base = make_repo(tmp_path)
    await set_main_branch("main")
    await _batch(batch_id, base, landings)
    monkeypatch.setattr(project_checks, "run_one", lambda *a, **k: dict(result))
    outcome = await landing_queue.run_batch_checks(
        tmp_path, "proj-test", batch_id, base, base, [CHECK], landings
    )
    decided = await landing_queue._decide(
        tmp_path,
        "main",
        "proj-test",
        batch_id,
        base,
        [landing.task_id for landing in landings],
        [base for _ in landings],
        landings,
        [CHECK],
        outcome,
        landing_queue.Chain(),
    )
    return outcome, decided


async def test_a_timeout_naming_no_failure_blames_nobody(app, tmp_path, monkeypatch, forbid_blame):
    landings = await _rows(2)
    outcome, decided = await _run_and_decide(
        tmp_path, monkeypatch, "lbat-f11310001", landings, _result()
    )

    assert outcome.unjudged and decided is False
    async with async_session_factory() as session:
        batch = await session.get(LandingBatch, "lbat-f11310001")
        states = [(await session.get(TaskLanding, row.id)).state for row in landings]
        run = await session.get(TaskCheckRun, batch.check_run_id)
    assert batch.state == "failed" and batch.error.startswith(landing_queue.UNJUDGED_TIMEOUT)
    assert states == ["queued", "queued"]  # retried, nobody sent back
    assert run.state == "error" and run.ended_by == project_checks.ENDED_BY_TIMEOUT


async def test_a_second_unjudged_timeout_is_the_operators(app, tmp_path, monkeypatch, forbid_blame):
    landings = await _rows(1)
    await _run_and_decide(tmp_path, monkeypatch, "lbat-f11310002", landings, _result())
    async with async_session_factory() as session:
        row = await session.get(TaskLanding, landings[0].id)
        row.state, row.batch_id = "checking", None
        await session.commit()
    outcome, decided = await _run_and_decide_again(
        tmp_path, monkeypatch, "lbat-f11310003", landings
    )

    assert decided is True
    async with async_session_factory() as session:
        batch = await session.get(LandingBatch, "lbat-f11310003")
        row = await session.get(TaskLanding, landings[0].id)
    assert batch.state == "held" and "twice in a row" in batch.error
    assert row.state == "held" and "twice in a row" in row.reason


async def _run_and_decide_again(tmp_path: Path, monkeypatch, batch_id: str, landings):
    base = git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    await _batch(batch_id, base, landings)
    monkeypatch.setattr(project_checks, "run_one", lambda *a, **k: _result())
    outcome = await landing_queue.run_batch_checks(
        tmp_path, "proj-test", batch_id, base, base, [CHECK], landings
    )
    decided = await landing_queue._decide(
        tmp_path,
        "main",
        "proj-test",
        batch_id,
        base,
        [landing.task_id for landing in landings],
        [base],
        landings,
        [CHECK],
        outcome,
        landing_queue.Chain(),
    )
    return outcome, decided


async def test_a_timeout_that_named_a_failure_still_narrows(app, tmp_path, monkeypatch):
    landings = await _rows(1)
    narrowed: List[bool] = []

    async def narrow(*args, **kwargs):
        narrowed.append(True)
        return True

    monkeypatch.setattr(landing_queue, "_narrow", narrow)
    monkeypatch.setattr(project_checks, "confirm_failure", lambda *a, **k: None)

    async def no_baseline(self, *a, **k):
        return None

    monkeypatch.setattr(project_checks._MainBaseline, "record", no_baseline)
    named = _result(named_failures=["test_x.py::test_y"])
    outcome, _ = await _run_and_decide(tmp_path, monkeypatch, "lbat-f11310004", landings, named)
    assert not outcome.unjudged and narrowed == [True]


async def test_a_landed_batch_ends_its_check_run(app, tmp_path):
    landings = await _rows(1)
    base = make_repo(tmp_path)
    await set_main_branch("main")
    await _batch("lbat-f11310005", base, landings)
    async with async_session_factory() as session:
        session.add(
            TaskCheckRun(
                id="chk-f11310005",
                project_id="proj-test",
                task_id=landings[0].task_id,
                main_sha=base,
                target_shas=[],
                merged_sha=base,
                state="running",
                results=[],
                error="",
            )
        )
        (await session.get(LandingBatch, "lbat-f11310005")).check_run_id = "chk-f11310005"
        await session.commit()

    await landing_queue._record_landed(tmp_path, "main", "lbat-f11310005", base, [base], landings)

    async with async_session_factory() as session:
        run = await session.get(TaskCheckRun, "chk-f11310005")
    assert run.state == "passed" and run.ended_at is not None


async def test_a_start_closes_a_run_left_running_by_an_ended_batch(app, tmp_path):
    landings = await _rows(1)
    base = make_repo(tmp_path)
    async with async_session_factory() as session:
        for n, state in enumerate(("landed", "checking"), start=6):
            session.add(
                TaskCheckRun(
                    id=f"chk-f1131000{n}",
                    project_id="proj-test",
                    task_id=landings[0].task_id,
                    main_sha=base,
                    target_shas=[],
                    merged_sha=base,
                    state="running",
                    results=[],
                    error="",
                )
            )
            session.add(
                LandingBatch(
                    id=f"lbat-f1131000{n}",
                    project_id="proj-test",
                    base_sha=base,
                    state=state,
                    task_ids=[],
                    prefixes=[],
                    results=[],
                    narrowing=[],
                    check_run_id=f"chk-f1131000{n}",
                )
            )
        await session.commit()

    assert await landing_queue.close_orphaned_check_runs() == 1

    async with async_session_factory() as session:
        runs = {r.id: r for r in (await session.execute(select(TaskCheckRun))).scalars()}
    assert runs["chk-f11310006"].state == "passed" and runs["chk-f11310006"].ended_at
    assert runs["chk-f11310007"].state == "running"
