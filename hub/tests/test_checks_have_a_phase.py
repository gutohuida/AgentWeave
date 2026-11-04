"""Checks have a phase (`checks-know-their-phase-and-give-way-to-the-user`, task `phases`).

Each check runs before review, at landing, or both. Before this change every check ran in a task's
pre-review run and again in its landing batch, so a slow suite ran about 4.7 times per task.

Real git repositories and real check processes throughout: each check is a script outside the
checkout that appends the tree it ran on to its own marker file, so "it ran" and "on which tree"
are read from what the process did, not from what the Hub recorded.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hub import landing_queue, project_checks
from hub.db import models
from hub.db.engine import async_session_factory
from hub.db.models import Project, TaskCheckRun

from .test_approved_work_merges_in_batches import (
    PY,
    approve,
    landings_of,
    merged_rows,
    tasks_under_review,
)

SETTINGS = "/api/v1/projects/proj-test/settings"
TASKS = "/api/v1/projects/proj-test/tasks"


@pytest.fixture(autouse=True)
def _a_long_gather_window(monkeypatch):
    """Approvals wait in the queue; each test drains it itself."""
    monkeypatch.setattr(landing_queue, "BATCH_GATHER_SECONDS", 3600.0)
    yield
    landing_queue.cancel_timers()


def marker_check(tmp_path_factory, name, *, phase=None, fails=False):
    """A check named *name* that appends the tree it ran on to its marker file, and passes (or
    fails, printing a pytest failure line, where *fails*)."""
    outside = tmp_path_factory.mktemp(f"check-{name}")
    marker = outside / "ran.txt"
    script = outside / "check.py"
    script.write_text(
        "import subprocess, sys\n"
        "tree = subprocess.run(['git', 'rev-parse', 'HEAD^{tree}'], capture_output=True,"
        " text=True).stdout.strip()\n"
        f"with open(r'{marker}', 'a', encoding='utf-8') as out:\n"
        "    out.write(tree + '\\n')\n"
        + (
            "print('FAILED tests/test_suite.py::test_balance - assert 2 == 3')\nsys.exit(1)\n"
            if fails
            else ""
        ),
        encoding="utf-8",
    )
    check = {"name": name, "command": f'{PY} "{script}"', "timeout_seconds": 120}
    if phase is not None:
        check["phase"] = phase
    return check, marker


def ran(marker):
    return marker.read_text(encoding="utf-8").split() if marker.exists() else []


async def store_checks(checks):
    """Store *checks* as they are, as a project saved before this change stored them."""
    async with async_session_factory() as session:
        (await session.get(Project, "proj-test")).checks = checks
        await session.commit()


async def runs_of(task_id):
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(TaskCheckRun)
                    .where(TaskCheckRun.task_id == task_id)
                    .order_by(TaskCheckRun.started_at)
                )
            ).scalars()
        )


async def batch_runs():
    async with async_session_factory() as session:
        batches = list(
            (
                await session.execute(
                    select(models.LandingBatch).order_by(models.LandingBatch.created_at)
                )
            ).scalars()
        )
        return [
            (batch, await session.get(TaskCheckRun, batch.check_run_id))
            for batch in batches
            if batch.check_run_id
        ]


async def check_before_review(task_id):
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()


async def land_everything():
    await landing_queue.drain()
    await project_checks.drain()


# --- FR-1 phase-setting ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_check_saved_before_phases_reads_and_runs_as_both(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """ac-phase-default: no phase key stored; the route reads both, and both runs run it."""
    lint, lint_ran = marker_check(tmp_path_factory, "lint")
    suite, suite_ran = marker_check(tmp_path_factory, "suite")
    [task_id], _ = await tasks_under_review(tmp_path, 1, status="completed")
    await store_checks([lint, suite])

    read = await app.get(SETTINGS, headers=auth_headers)
    assert read.status_code == 200, read.text
    assert [check["phase"] for check in read.json()["checks"]] == ["both", "both"]

    await check_before_review(task_id)
    [run] = await runs_of(task_id)
    assert run.state == "passed", (run.state, run.error, run.results)
    assert [result["name"] for result in run.results] == ["lint", "suite"]
    assert len(ran(lint_ran)) == 1 and len(ran(suite_ran)) == 1

    # The landing batch runs every check too. The tree is the one already passed before review,
    # so its passes are reused rather than run again (`checks-wait-less`), exactly as before.
    moved = await app.patch(
        f"{TASKS}/{task_id}", json={"status": "under_review"}, headers=auth_headers
    )
    assert moved.status_code == 200, moved.text
    assert (await approve(app, auth_headers, task_id)).status_code == 200
    await land_everything()
    [(batch, batch_run)] = await batch_runs()
    assert batch.state == "landed"
    assert [result["name"] for result in batch_run.results] == ["lint", "suite"]


@pytest.mark.asyncio
async def test_the_operator_sets_one_check_to_landing(app, auth_headers):
    """ac-phase-set."""
    saved = await app.put(
        SETTINGS,
        json={
            "checks": [
                {"name": "lint", "command": "ruff check ."},
                {"name": "suite", "command": "pytest", "phase": "landing"},
            ]
        },
        headers=auth_headers,
    )
    assert saved.status_code == 200, saved.text
    read = await app.get(SETTINGS, headers=auth_headers)
    assert {check["name"]: check["phase"] for check in read.json()["checks"]} == {
        "lint": "both",
        "suite": "landing",
    }
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        assert [c["name"] for c in project_checks.configured_checks(project, "review")] == ["lint"]
        assert [c["name"] for c in project_checks.configured_checks(project, "landing")] == [
            "lint",
            "suite",
        ]


# --- FR-2 landing-only-skipped-before-review -------------------------------------------------


@pytest.mark.asyncio
async def test_a_landing_only_check_waits_for_landing_and_holds_nothing_before(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """ac-landing-only, then ac-landing-runs-it."""
    a, a_ran = marker_check(tmp_path_factory, "A", phase="review")
    b, b_ran = marker_check(tmp_path_factory, "B", phase="landing")
    [task_id], _ = await tasks_under_review(tmp_path, 1, status="completed")
    await store_checks([a, b])

    await check_before_review(task_id)
    [run] = await runs_of(task_id)
    assert run.state == "passed", (run.state, run.error, run.results)
    assert [result["name"] for result in run.results] == ["A"]
    assert len(ran(a_ran)) == 1
    assert ran(b_ran) == [], "the landing-only check ran before review"

    checks = await app.get(f"{TASKS}/{task_id}/checks", headers=auth_headers)
    assert checks.status_code == 200, checks.text
    body = checks.json()
    assert body["at_landing"] == ["B"]
    assert body["before_review"] is True
    assert all(result["name"] != "B" for result in body["runs"][0]["results"])

    moved = await app.patch(
        f"{TASKS}/{task_id}", json={"status": "under_review"}, headers=auth_headers
    )
    assert moved.status_code == 200, moved.text
    approved = await approve(app, auth_headers, task_id)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert ran(b_ran) == [], "approval waited for the landing-only check"

    # ac-landing-runs-it: B runs on the merged tree, and the work lands.
    await land_everything()
    [(batch, batch_run)] = await batch_runs()
    assert batch.state == "landed", batch.state
    assert ran(b_ran) == [batch_run.merged_sha and _tree(tmp_path, batch_run.merged_sha)]
    assert "B" in [result["name"] for result in batch_run.results]
    assert [landing.state for landing in await landings_of(task_id)] == ["landed"]


@pytest.mark.asyncio
async def test_a_landing_only_check_that_fails_holds_the_landing(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """ac-landing-runs-it, its failure half: B fails on the merged tree, so nothing lands."""
    a, _ = marker_check(tmp_path_factory, "A", phase="review")
    b, b_ran = marker_check(tmp_path_factory, "B", phase="landing", fails=True)
    [task_id], _ = await tasks_under_review(tmp_path, 1, status="completed")
    await store_checks([a, b])
    main_before = _tip(tmp_path)

    await check_before_review(task_id)
    [run] = await runs_of(task_id)
    assert run.state == "passed", "B's failure is not seen before review"
    await app.patch(f"{TASKS}/{task_id}", json={"status": "under_review"}, headers=auth_headers)
    assert (await approve(app, auth_headers, task_id)).status_code == 200

    await land_everything()
    assert len(ran(b_ran)) >= 1, "the landing-only check did not run at landing"
    assert await merged_rows(task_id) == []
    assert _tip(tmp_path) == main_before, "main moved over a failing landing check"
    assert all(landing.state != "landed" for landing in await landings_of(task_id))


# --- FR-3 review-only-skipped-at-landing -----------------------------------------------------


@pytest.mark.asyncio
async def test_a_review_only_check_does_not_run_at_landing(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """ac-review-only: approved straight from review, the batch runs C and not A, and lands."""
    a, a_ran = marker_check(tmp_path_factory, "A", phase="review")
    c, c_ran = marker_check(tmp_path_factory, "C", phase="both")
    [task_id], [work] = await tasks_under_review(tmp_path, 1)
    await store_checks([a, c])
    await project_checks.drain()
    a_before = len(ran(a_ran))

    assert (await approve(app, auth_headers, task_id)).status_code == 200
    await land_everything()

    [(batch, batch_run)] = await batch_runs()
    assert batch.state == "landed", batch.state
    assert [result["name"] for result in batch_run.results] == ["C"]
    assert len(ran(a_ran)) == a_before, "the review-only check ran in the landing batch"
    assert _tree(tmp_path, batch_run.merged_sha) in ran(c_ran)
    assert [row.commit_sha for row in await merged_rows(task_id)] == [work]


# --- FR-4 fast-not-landing-only --------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_fast_landing_only_check_is_refused_and_nothing_changes(app, auth_headers):
    """ac-fast-refused."""
    first = [{"name": "lint", "command": "ruff check .", "timeout_seconds": 60, "fast": True}]
    assert (
        await app.put(SETTINGS, json={"checks": first}, headers=auth_headers)
    ).status_code == 200
    before = (await app.get(SETTINGS, headers=auth_headers)).json()["checks"]

    refused = await app.put(
        SETTINGS,
        json={"checks": [{**first[0], "phase": "landing"}]},
        headers=auth_headers,
    )
    assert refused.status_code == 422, refused.text
    assert "a fast check gates an agent's completion before review" in refused.text
    assert "cannot be landing-only" in refused.text
    assert (await app.get(SETTINGS, headers=auth_headers)).json()["checks"] == before

    # Fast and before-review-only, or fast and both, are fine.
    for phase in ("review", "both"):
        ok = await app.put(
            SETTINGS, json={"checks": [{**first[0], "phase": phase}]}, headers=auth_headers
        )
        assert ok.status_code == 200, ok.text


def _tip(root):
    from .test_task_integration import git

    return git(root, "rev-parse", "main").stdout.strip()


def _tree(root, commit):
    from .test_task_integration import git

    return git(root, "rev-parse", f"{commit}^{{tree}}").stdout.strip()
