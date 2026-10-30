"""Every send-back says why (`a-task-s-checks-and-merges-use-its-own-work-and-a-live-run-is-never-
reset`, FR-8 and FR-9; trial Hub document `spdoc-ed50fbb03efe`, task `send-back-reason`).

Two send-backs on 2026-10-29, one a regression and one a merge only, both read just "held (not
named as failing)" in the history. A move to `revision_needed` now records a reason class and a
sentence on its history row: a reviewer must give the class (refused naming the six), and the Hub
sets it on the send-backs it makes itself.
"""

from __future__ import annotations

import json
import typing
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hub import mcp_server, project_checks
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, Task, TaskCheckRun
from hub.task_transitions import SEND_BACK_CLASSES

from .test_checks_run_before_review import (
    TASK,
    _completed_outside_a_flow,
    _configure,
    _latest_transition,
    _slow,
)
from .test_task_integration import TASKS, drive_to

pytestmark = pytest.mark.asyncio

AGENT_TASKS = "/api/v1/agent-actions/tasks"
REVIEWER_TOKEN = "aw_run_sendback-reviewer"
#: The history row the app's vitest renders (`hub/ui/src/__tests__/taskTransitionHistory.test.tsx`).
#: Checked against what the route returns below, so the UI test is fed the route's real shape.
UI_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "ui"
    / "src"
    / "__tests__"
    / "fixtures"
    / "taskTransitionSendBack.json"
)
SENTENCE = (
    "The work is right; main moved under it, so merge main into the branch and complete again."
)


@pytest.fixture
async def reviewer():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-sendback-r", project_id="proj-test", name="reviewer"))
        session.add(
            Run(
                id="run-sendback-r",
                project_id="proj-test",
                agent="reviewer",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(REVIEWER_TOKEN),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {REVIEWER_TOKEN}"}


async def _under_review(app, auth_headers) -> str:
    created = await app.post(TASKS, json={"title": "Send me back"}, headers=auth_headers)
    assert created.status_code == 201, created.text
    task = created.json()["id"]
    walked = await drive_to(
        app, auth_headers, task, "assigned", "in_progress", "completed", "under_review"
    )
    assert walked.status_code == 200, walked.text
    return task


async def _status(task_id: str) -> str:
    async with async_session_factory() as session:
        return (await session.get(Task, task_id)).status


async def test_a_send_back_records_its_class_and_sentence(app, auth_headers, reviewer):
    """ac-reason-recorded: class merge-needed, a sentence, no failing pieces."""
    task = await _under_review(app, auth_headers)

    sent = await app.patch(
        f"{AGENT_TASKS}/{task}",
        json={"status": "revision_needed", "reason_class": "merge-needed", "notes": SENTENCE},
        headers=reviewer,
    )
    assert sent.status_code == 200, sent.text

    history = await app.get(f"{AGENT_TASKS}/{task}/transitions", headers=reviewer)
    assert history.status_code == 200, history.text
    [row] = [r for r in history.json()["transitions"] if r["to_status"] == "revision_needed"]
    assert (row["reason_class"], row["reason"]) == ("merge-needed", SENTENCE)
    assert row["actor_agent"] == "reviewer"

    # The operator's route answers the same, and the app's fixture is that answer's shape.
    operator_view = await app.get(f"{TASKS}/{task}/transitions", headers=auth_headers)
    [same] = [r for r in operator_view.json()["transitions"] if r["to_status"] == "revision_needed"]
    assert same == row
    fixture = json.loads(UI_FIXTURE.read_text(encoding="utf-8"))
    assert set(fixture) == set(row), "the UI fixture must carry exactly the route's fields"
    for key in ("from_status", "to_status", "actor_kind", "actor_agent", "origin"):
        assert fixture[key] == row[key], key
    assert (fixture["reason_class"], fixture["reason"]) == ("merge-needed", SENTENCE)


async def test_a_send_back_without_a_class_is_refused_naming_them(app, auth_headers, reviewer):
    """ac-reason-required: refused naming the six classes; the task stays under_review."""
    task = await _under_review(app, auth_headers)

    sent = await app.patch(
        f"{AGENT_TASKS}/{task}",
        json={"status": "revision_needed", "notes": "It prints the wrong word."},
        headers=reviewer,
    )

    assert sent.status_code == 422, sent.text
    detail = sent.json()["detail"]
    assert detail["code"] == "send_back_needs_a_class"
    for name in SEND_BACK_CLASSES:
        assert name in detail["message"], name
    assert len(SEND_BACK_CLASSES) == 6
    assert await _status(task) == "under_review"


async def test_an_unknown_class_or_a_missing_sentence_is_refused(app, auth_headers, reviewer):
    task = await _under_review(app, auth_headers)

    unknown = await app.patch(
        f"{AGENT_TASKS}/{task}",
        json={"status": "revision_needed", "reason_class": "vibes", "notes": "No."},
        headers=reviewer,
    )
    silent = await app.patch(
        f"{AGENT_TASKS}/{task}",
        json={"status": "revision_needed", "reason_class": "defect"},
        headers=reviewer,
    )

    assert unknown.status_code == 422 and unknown.json()["detail"]["code"] == (
        "send_back_class_unknown"
    )
    assert silent.status_code == 422 and silent.json()["detail"]["code"] == (
        "send_back_needs_a_reason"
    )
    assert await _status(task) == "under_review"


async def test_the_operator_may_send_back_with_a_status_alone(app, auth_headers):
    """The app's status menu sends a status alone: not refused, and the row records no reason."""
    task = await _under_review(app, auth_headers)

    sent = await app.patch(
        f"{TASKS}/{task}", json={"status": "revision_needed"}, headers=auth_headers
    )

    assert sent.status_code == 200, sent.text
    row = await _latest_transition(task)
    assert (row.to_status, row.reason_class, row.reason) == ("revision_needed", None, None)


async def test_the_tool_offers_exactly_the_hubs_classes():
    """`mcp_server` restates the classes (it may not import the Hub); the two must agree."""
    assert typing.get_args(mcp_server.SendBackClass) == SEND_BACK_CLASSES


async def _a_failed_run_with_confirmation(tmp_path, confirmed_exit_code: int) -> str:
    """A completed task, its real check run failed; its results then stubbed to a failure whose
    confirming re-run exited *confirmed_exit_code* (`project_checks.confirm_failure`'s shape: a
    re-run that passed still counts as the task's failure when the flaky test is in a file the task
    changed, FR-4)."""
    await _completed_outside_a_flow(tmp_path)
    await _configure([_slow(tmp_path, fails_on="ledger.py")])
    async with async_session_factory() as db:
        (await db.get(Task, TASK)).status = "under_review"  # so the run's own return does not act
        await db.commit()
    run_id = await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()
    async with async_session_factory() as db:
        run = await db.get(TaskCheckRun, run_id)
        assert run.state == "failed"
        test_id = "tests/test_ledger.py::test_balance"
        run.results = [
            {
                "name": "hub-tests",
                "exit_code": 1,
                "timed_out": False,
                "failed_tests": [test_id],
                "confirmed": {
                    "how": "tests",
                    "tests": [test_id],
                    "exit_code": confirmed_exit_code,
                    "timed_out": False,
                    "duration_seconds": 0.5,
                },
                "compared_tests": [test_id],
            }
        ]
        run.ended_at = datetime.now(timezone.utc)
        (await db.get(Task, TASK)).status = "completed"
        await db.commit()
    return run_id


@pytest.mark.parametrize(("confirmed_exit_code", "expected"), [(1, "broken-check"), (0, "flaky")])
async def test_the_hubs_own_send_back_records_broken_check_or_flaky(
    app, tmp_path, confirmed_exit_code, expected
):
    """ac-hub-sendback-class: failing on confirmation records broken-check; passing on the
    confirming re-run records flaky."""
    run_id = await _a_failed_run_with_confirmation(tmp_path, confirmed_exit_code)

    assert await project_checks.return_failed_work(run_id) is True

    row = await _latest_transition(TASK)
    assert (row.to_status, row.origin) == ("revision_needed", "checks")
    assert row.reason_class == expected
    assert run_id in (row.reason or "")


def test_send_back_class_reads_only_the_tasks_own_failures():
    passed = {"name": "lint", "exit_code": 0, "timed_out": False}
    on_main = {"name": "suite", "exit_code": 1, "timed_out": False, "preexisting": True}
    flaked = {**on_main, "preexisting": False, "confirmed": {"exit_code": 0, "timed_out": False}}
    stands = {**flaked, "confirmed": {"exit_code": 1, "timed_out": False}}

    assert project_checks.send_back_class([passed, on_main, flaked]) == "flaky"
    assert project_checks.send_back_class([flaked, stands]) == "broken-check"
    assert project_checks.send_back_class([{**on_main, "preexisting": False}]) == "broken-check"
