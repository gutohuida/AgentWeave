"""F1051: the newest integration row of a task is chosen by an order that cannot tie.

One approval of a task with several commits writes several `task_integrations` rows in a single
transaction, so they share a `created_at`. On the operator's Hub, task-8618731d065d has a `merged`
and a `skipped` ("already in master") row stamped identically; ordering by `created_at` alone left
the winner to SQLite, so a task that merged read "approved but not merged".
"""

from datetime import datetime, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Task, TaskIntegration

PROJECT = "proj-test"
TASKS = "/api/v1/projects/proj-test/tasks"
STAMP = datetime(2026, 10, 27, 3, 39, 29, 548442, tzinfo=timezone.utc)


async def _task_with(*rows):
    """Insert one approved task and `rows` (outcome, reason, id), in the order given."""
    async with async_session_factory() as session:
        session.add(Task(id="task-tie", project_id=PROJECT, title="Tied", status="approved"))
        await session.flush()
        for outcome, reason, row_id in rows:
            session.add(
                TaskIntegration(
                    id=row_id,
                    project_id=PROJECT,
                    task_id="task-tie",
                    outcome=outcome,
                    reason=reason,
                    commit_sha="09617d3b6920",
                    target_branch="master",
                    actor_kind="operator",
                    created_at=STAMP,
                )
            )
            await session.flush()
        await session.commit()


async def _latest(app, auth_headers):
    listed = await app.get(TASKS, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    row = next(t for t in listed.json()["tasks"] if t["id"] == "task-tie")
    single = await app.get(f"{TASKS}/task-tie", headers=auth_headers)
    assert single.json()["latest_integration"] == row["latest_integration"]
    return row["latest_integration"]


@pytest.mark.asyncio
@pytest.mark.parametrize("merged_first", [True, False])
async def test_a_merge_in_the_same_approval_beats_a_skip_whatever_was_inserted_first(
    app, auth_headers, merged_first
):
    merged = ("merged", "", "tint-zz-merged")
    skipped = (
        "skipped",
        "09617d3b6920 is already in master; there was nothing to merge",
        "tint-aa-skipped",
    )
    await _task_with(*((merged, skipped) if merged_first else (skipped, merged)))
    assert (await _latest(app, auth_headers))["outcome"] == "merged"


@pytest.mark.asyncio
async def test_a_failure_in_the_same_approval_is_not_hidden_by_a_merge(app, auth_headers):
    await _task_with(("failed", "CONFLICT (content)", "tint-1"), ("merged", "", "tint-2"))
    assert (await _latest(app, auth_headers))["outcome"] == "failed"


@pytest.mark.asyncio
async def test_rows_that_tie_in_time_and_outcome_resolve_to_the_last_inserted(app, auth_headers):
    # Ids sort the other way round, so only the insertion sequence can decide this.
    await _task_with(
        ("skipped", "first reason", "tint-zz"), ("skipped", "second reason", "tint-aa")
    )
    assert (await _latest(app, auth_headers))["reason"] == "second reason"
