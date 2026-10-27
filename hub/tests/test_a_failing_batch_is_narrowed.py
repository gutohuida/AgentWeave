"""A failing batch sends back only the task that broke it (`approved-work-merges-in-batches`, task
narrow-and-hold).

The roadmap's done criterion: a deliberately broken task among four is the only one sent back. Real
git, and the project's check a plain pytest run over the checked tree, with a `conftest.py` on main
that records every run's selected test ids in a file outside the repository -- so "the check ran on
the whole tree twice and the narrowed runs ran one test" is counted, not inferred.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest
from sqlalchemy import select

from hub import landing_queue
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    EventLog,
    LandingBatch,
    Loop,
    Project,
    Task,
    TaskIntegration,
    TaskTransition,
)
from hub.worktrees import task_branch_name

from .test_task_integration import commits_on, files_on, git, make_repo, set_main_branch

pytestmark = pytest.mark.asyncio

PY = f'"{sys.executable}"'
PYTEST = {
    "name": "pytest",
    "command": f"{PY} -m pytest -q -p no:cacheprovider -p no:randomly",
    "timeout_seconds": 120,
}
TASKS = "/api/v1/projects/proj-test/tasks"
#: Fails once `broken.txt` exists: the file a broken task adds.
SUITE = (
    "import os\n\n\n"
    "def test_ok():\n    assert True\n\n\n"
    "def test_no_marker():\n    assert not os.path.exists('broken.txt'), 'broken'\n"
)
NO_MARKER = "test_suite.py::test_no_marker"
#: Main is red here: `test_red` fails on main and on every task's tree.
RED = "def test_red():\n    assert 1 == 2, 'main is red'\n"
RED_ID = "test_red.py::test_red"


@pytest.fixture(autouse=True)
def _a_long_gather_window(monkeypatch):
    monkeypatch.setattr(landing_queue, "BATCH_GATHER_SECONDS", 3600.0)
    yield
    landing_queue.cancel_timers()


def _repo(root: Path, ledger: Path, extra: Optional[Dict[str, str]] = None) -> None:
    """Main with the suite and a conftest recording each run's selected ids in *ledger*."""
    make_repo(root)
    files = {
        "test_suite.py": SUITE,
        "conftest.py": (
            "def pytest_collection_modifyitems(session, config, items):\n"
            f"    with open(r'{ledger}', 'a', encoding='utf-8') as out:\n"
            "        out.write(' '.join(item.nodeid for item in items) + '\\n')\n"
        ),
        **(extra or {}),
    }
    for name, content in files.items():
        (root / name).write_text(content, encoding="utf-8")
        git(root, "add", name)
    git(root, "commit", "-q", "-m", "the suite")


async def _project(auto_override: Optional[bool] = None) -> None:
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.checks = [PYTEST]
        if auto_override is not None:
            project.checks_auto_override = auto_override
        session.add(
            AIJob(
                id="job-narrow",
                project_id="proj-test",
                name="narrow",
                agent="builder",
                message="work",
                cron="*/5 * * * *",
                session_mode="new",
                enabled=False,
            )
        )
        await session.flush()
        session.add(
            Loop(
                id="loop-narrow",
                project_id="proj-test",
                job_id="job-narrow",
                purpose="work",
                work_needs_evidence=False,
            )
        )
        await session.commit()
    await set_main_branch("main")


async def _tasks(
    root: Path, work: List[Tuple[Dict[str, str], Optional[int]]]
) -> Tuple[List[str], List[str]]:
    """One task under review per entry: its files, committed on a branch cut from main, or from the
    branch of the task numbered by the entry's second element (a dependent)."""
    ids = [f"task-a7a40000{n:04d}" for n in range(1, len(work) + 1)]
    async with async_session_factory() as session:
        for n, task_id in enumerate(ids, start=1):
            session.add(
                Task(
                    id=task_id,
                    loop_id="loop-narrow",
                    project_id="proj-test",
                    title=f"Work {n}",
                    description="",
                    status="under_review",
                    assignee="builder",
                )
            )
        await session.commit()
    tips: List[str] = []
    for task_id, (files, parent) in zip(ids, work, strict=True):
        base = "main" if parent is None else task_branch_name(ids[parent - 1])
        git(root, "checkout", "-q", "-b", task_branch_name(task_id), base)
        for name, content in files.items():
            (root / name).write_text(content, encoding="utf-8")
            git(root, "add", name)
        git(root, "commit", "-q", "-m", f"work of {task_id}")
        tips.append(git(root, "rev-parse", "HEAD").stdout.strip())
    git(root, "checkout", "-q", "main")
    return ids, tips


async def _approve(app, auth_headers, task_id: str) -> None:
    approved = await app.patch(
        f"{TASKS}/{task_id}", json={"status": "approved"}, headers=auth_headers
    )
    assert approved.status_code == 200, approved.text


async def _status(task_id: str) -> str:
    async with async_session_factory() as session:
        return (await session.get(Task, task_id)).status


async def _merged(task_id: str) -> List[TaskIntegration]:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(TaskIntegration).where(
                        TaskIntegration.task_id == task_id, TaskIntegration.outcome == "merged"
                    )
                )
            ).scalars()
        )


async def _batches() -> List[LandingBatch]:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(select(LandingBatch).order_by(LandingBatch.created_at))
            ).scalars()
        )


async def _landing(task_id: str):
    async with async_session_factory() as session:
        return await landing_queue.latest_landing(session, task_id)


def _runs(ledger: Path) -> List[List[str]]:
    lines = ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else []
    return [line.split() for line in lines]


async def test_a_broken_task_among_four_is_the_only_one_sent_back(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """broken-one-sent-back, the roadmap's done criterion."""
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    _repo(tmp_path, ledger)
    await _project()
    ids, tips = await _tasks(
        tmp_path,
        [
            ({"one.py": "x = 1\n"}, None),
            ({"two.py": "x = 2\n"}, None),
            ({"broken.txt": "this breaks the suite\n"}, None),
            ({"four.py": "x = 4\n"}, None),
        ],
    )
    for task_id in ids:
        await _approve(app, auth_headers, task_id)

    await landing_queue.drain()

    assert [await _status(task_id) for task_id in ids] == [
        "approved",
        "approved",
        "revision_needed",
        "approved",
    ]
    for task_id, tip in ((ids[0], tips[0]), (ids[1], tips[1]), (ids[3], tips[3])):
        assert [row.commit_sha for row in await _merged(task_id)] == [tip]
    assert await _merged(ids[2]) == []
    assert "broken.txt" not in files_on(tmp_path, "main")
    assert tips[2] not in commits_on(tmp_path, "main")

    async with async_session_factory() as session:
        back = (
            await session.execute(
                select(TaskTransition).where(
                    TaskTransition.task_id == ids[2], TaskTransition.to_status == "revision_needed"
                )
            )
        ).scalar_one()
        task = await session.get(Task, ids[2])
    first = (await _batches())[0]
    assert first.id in (back.note or ""), back.note
    report = (await _landing(ids[2])).reason
    assert first.id in report and NO_MARKER in report, report
    assert ids[0] in report and ids[1] in report and ids[3] not in report.split("\n\n")[0]
    assert NO_MARKER in str(task.notes)

    # Two runs on the whole tree (the batch, then the rest of it), and the narrowing ran only the
    # failing test, at most ceil(log2(4)) = 2 times.
    runs = _runs(ledger)
    whole = [run for run in runs if len(run) >= 2]
    assert len(whole) == 2, runs
    assert all(run == [NO_MARKER] for run in runs if len(run) < 2), runs
    narrowing = first.narrowing
    assert 1 <= len(narrowing) <= 2, narrowing
    assert all(step["tests"] == [NO_MARKER] for step in narrowing), narrowing
    landed = (await _batches())[-1]
    assert landed.state == "landed" and landed.task_ids == [ids[0], ids[1], ids[3]]
    assert git(tmp_path, "rev-parse", "main").stdout.strip() == landed.merged_sha


async def test_a_conflict_in_a_batch_goes_to_its_author(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """conflict-taken-out: the second is sent back before any check runs, naming the path and the
    first task; the first lands after the batch's run."""
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    _repo(tmp_path, ledger)
    await _project()
    ids, tips = await _tasks(
        tmp_path,
        [({"README.md": "first wording\n"}, None), ({"README.md": "second wording\n"}, None)],
    )
    for task_id in ids:
        await _approve(app, auth_headers, task_id)

    await landing_queue.drain()

    assert await _status(ids[0]) == "approved"
    assert [row.commit_sha for row in await _merged(ids[0])] == [tips[0]]
    assert await _status(ids[1]) == "revision_needed"
    landing = await _landing(ids[1])
    assert landing.state == "sent_back"
    assert "README.md" in landing.reason and ids[0] in landing.reason, landing.reason
    [batch] = await _batches()
    assert batch.task_ids == [ids[0]], "the conflicting task was taken out before the check"
    assert len([run for run in _runs(ledger) if len(run) >= 2]) == 1


async def test_a_dependent_lands_after_its_prerequisite(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """dependent-waits: B's branch contains A's commit. Queued A after B, A lands first (or with
    it); sent back by its batch, A holds B, which is not sent back and names A."""
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    _repo(tmp_path, ledger)
    await _project()
    ids, tips = await _tasks(tmp_path, [({"a.py": "a = 1\n"}, None), ({"b.py": "b = 1\n"}, 1)])
    a, b = ids
    await _approve(app, auth_headers, b)
    await _approve(app, auth_headers, a)

    await landing_queue.drain()

    [batch] = await _batches()
    assert batch.task_ids == [a, b], "the prerequisite is landed first"
    assert [row.commit_sha for row in await _merged(a)] == [tips[0]]
    assert [row.commit_sha for row in await _merged(b)] == [tips[1]]


async def test_a_sent_back_prerequisite_holds_its_dependent(
    app, auth_headers, tmp_path, tmp_path_factory
):
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    _repo(tmp_path, ledger)
    await _project()
    ids, tips = await _tasks(
        tmp_path, [({"broken.txt": "breaks\n"}, None), ({"b.py": "b = 1\n"}, 1)]
    )
    a, b = ids
    await _approve(app, auth_headers, b)
    await _approve(app, auth_headers, a)

    await landing_queue.drain()

    assert await _status(a) == "revision_needed"
    assert await _status(b) == "approved", "the dependent is not sent back"
    landing = await _landing(b)
    assert landing.state == "held" and landing.waits_on == a, (landing.state, landing.waits_on)
    assert a in landing.reason
    assert tips[1] not in commits_on(tmp_path, "main")


async def _fix_tasks() -> List[str]:
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(EventLog.data).where(EventLog.event_type == "checks_fix_task_filed")
                )
            )
            .scalars()
            .all()
        )
    return [row["task_id"] for row in rows]


@pytest.mark.parametrize("override", [True, False])
async def test_a_failure_main_shares_follows_m(
    app, auth_headers, tmp_path, tmp_path_factory, override
):
    """main-shares-the-failure: a batch of three whose only failure fails on main too is never
    narrowed. With M's automatic override on all three land with it recorded on the batch and each
    integration, and one fix task is filed; off, the batch waits, and one reason lands all three."""
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    _repo(tmp_path, ledger, {"test_red.py": RED})
    await _project(auto_override=override)
    ids, tips = await _tasks(
        tmp_path,
        [({"one.py": "x = 1\n"}, None), ({"two.py": "x = 2\n"}, None), ({"three.py": "x\n"}, None)],
    )
    for task_id in ids:
        await _approve(app, auth_headers, task_id)

    await landing_queue.drain()

    [batch] = await _batches()
    assert batch.narrowing == [], "a failure main shares is not narrowed"
    if override:
        assert batch.state == "landed" and batch.override_by == "hub"
        assert RED_ID in (batch.override_reason or "")
        for task_id, tip in zip(ids, tips, strict=True):
            [row] = await _merged(task_id)
            assert row.commit_sha == tip and row.batch_id == batch.id
            assert row.override_reason == batch.override_reason
        assert len(await _fix_tasks()) == 1, "one fix task per failing check, not per task"
        return

    assert batch.state == "held"
    for task_id in ids:
        assert await _merged(task_id) == []
        assert (await _landing(task_id)).state == "held"
    read = await app.get(f"{TASKS}/{ids[1]}/checks", headers=auth_headers)
    assert read.json()["landing"]["state"] == "held"
    assert await _fix_tasks() == []

    landed = await app.post(
        f"{TASKS}/{ids[1]}/landing/land",
        json={"reason": "main is red on test_red; fixing it separately"},
        headers=auth_headers,
    )
    assert landed.status_code == 200, landed.text
    for task_id, tip in zip(ids, tips, strict=True):
        [row] = await _merged(task_id)
        assert row.commit_sha == tip
        assert row.override_reason == "main is red on test_red; fixing it separately"
    [batch] = await _batches()
    assert batch.state == "landed" and batch.override_by == "operator"
