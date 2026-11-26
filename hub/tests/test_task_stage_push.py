"""A task's stage is pushed to the open pages as a `task_stage` frame, derived as the routes derive
it (`task-stages-in-the-build-view-and-dependency-map` FR-6, FR-11; TSBVD-11).

Drive run 184251: the board and the map read the stage from the task list, the build view from the
build read, and on a busy Hub the two answer one event up to two seconds apart, so the pages showed
different stages for that long. The frame reaches every page at once; these tests hold that it
follows the commit that moved the stage, carries what the task list then reads, and costs nothing
while nobody listens.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

import pytest

from hub import project_checks, task_stage_push
from hub.sse import sse_manager

from .test_checks_run_before_review import TASK, _completed_outside_a_flow, _configure, _slow
from .test_task_stages_and_check_state import _in_a_build, _reads

pytestmark = pytest.mark.asyncio


async def _frames(queue, seconds: float = 10.0) -> List[Dict[str, Any]]:
    """Every `task_stage` frame the queue holds once the pushes in flight are done."""
    for _ in range(int(seconds / 0.05)):
        if not task_stage_push._running and not task_stage_push._pending:
            break
        await asyncio.sleep(0.05)
    frames = []
    while not queue.empty():
        event = queue.get_nowait()
        if event.event == task_stage_push.STAGE_EVENT:
            frames.append(json.loads(event.data) if isinstance(event.data, str) else event.data)
    return frames


def _of(frames: List[Dict[str, Any]], task_id: str) -> List[Dict[str, Any]]:
    return [row for frame in frames for row in frame["tasks"] if row["id"] == task_id]


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_check_start_pushes_the_stage_the_task_list_then_reads(app, auth_headers, tmp_path):
    await _completed_outside_a_flow(tmp_path)
    await _in_a_build(TASK)
    queue = sse_manager.subscribe("proj-test")
    try:
        await _configure([_slow(tmp_path)])
        await project_checks.request_run("proj-test", TASK)
        await project_checks.drain()
        pushed = _of(await _frames(queue), TASK)
        read = (await _reads(app, auth_headers, TASK))[TASK]
    finally:
        sse_manager.unsubscribe("proj-test", queue)

    assert pushed, "a check run starting pushes its task's stage"
    assert any(
        r["check_state"] and r["check_state"]["state"] == "running" for r in pushed
    ), f"a frame shows the check running: {pushed}"
    last = pushed[-1]
    assert (last["stage"], last["check_state"]) == (
        read["stage"],
        read["check"],
    ), "the last frame is what the task list and the build read answer afterwards"
    assert set(last) == {"id", *task_stage_push.STAGE_FIELDS}


async def test_an_operator_move_pushes_the_new_stage_after_its_commit(app, auth_headers, tmp_path):
    await _completed_outside_a_flow(tmp_path)
    queue = sse_manager.subscribe("proj-test")
    try:
        moved = await app.patch(
            f"/api/v1/projects/proj-test/tasks/{TASK}",
            json={
                "status": "revision_needed",
                "notes": "the ledger does not balance",
                "reason_class": "defect",
            },
            headers=auth_headers,
        )
        assert moved.status_code == 200, moved.text
        pushed = _of(await _frames(queue), TASK)
        listed = await app.get(f"/api/v1/projects/proj-test/tasks/{TASK}", headers=auth_headers)
    finally:
        sse_manager.unsubscribe("proj-test", queue)

    assert pushed, "the move pushes the task's stage"
    assert pushed[-1]["stage"] == listed.json()["stage"] == "sent_back"


async def test_nothing_is_derived_while_nobody_listens(app, auth_headers, tmp_path, monkeypatch):
    await _completed_outside_a_flow(tmp_path)
    derived: List[Any] = []

    async def frame(*args, **kwargs):
        derived.append(args)
        return {"tasks": []}

    monkeypatch.setattr(task_stage_push, "stage_frame", frame)
    # Nobody: not a stream another test left open in this worker either.
    monkeypatch.setattr(sse_manager, "_subscribers", {})
    monkeypatch.setattr(sse_manager, "_operator_subscribers", [])
    moved = await app.patch(
        f"/api/v1/projects/proj-test/tasks/{TASK}",
        json={
            "status": "revision_needed",
            "notes": "the ledger does not balance",
            "reason_class": "defect",
        },
        headers=auth_headers,
    )
    assert moved.status_code == 200, moved.text
    await asyncio.sleep(0.2)
    assert derived == [] and not task_stage_push._pending


async def test_a_run_event_pushes_the_stage_of_the_task_the_run_works_on(
    app, auth_headers, tmp_path
):
    from hub.db.engine import async_session_factory
    from hub.db.models import Run

    await _completed_outside_a_flow(tmp_path)
    async with async_session_factory() as db:
        db.add(
            Run(
                initiator="autonomous",
                id="run-push-dev",
                project_id="proj-test",
                agent="DeveloperA",
                status="completed",
                turn_depth=0,
                task_id=TASK,
            )
        )
        await db.commit()
    queue = sse_manager.subscribe("proj-test")
    try:
        # Only the run is named: its task is looked up.
        sse_manager.publish(
            "proj-test", "run_completed", {"run_id": "run-push-dev", "agent": "DeveloperA"}
        )
        pushed = _of(await _frames(queue), TASK)
        listed = await app.get(f"/api/v1/projects/proj-test/tasks/{TASK}", headers=auth_headers)
    finally:
        sse_manager.unsubscribe("proj-test", queue)
    assert pushed, "an event naming only a run pushes the stage of the run's task"
    assert pushed[-1]["stage"] == listed.json()["stage"]


async def test_a_passed_batch_reads_landing_and_its_frame_moves_every_task_of_the_batch(
    app, auth_headers, tmp_path, tmp_path_factory, monkeypatch
):
    """Drive run 203702: the batch's run passed and its landing row moved on 0.2 s later; pushed at
    once, that moment read Landing checks with no check on every page, and only the batch's first
    task moved while the other still showed the run running."""
    from hub import landing_queue
    from hub.db.engine import async_session_factory

    from .test_a_failing_batch_is_narrowed import _approve, _project, _repo, _tasks

    monkeypatch.setattr(landing_queue, "BATCH_GATHER_SECONDS", 3600.0)
    _repo(tmp_path, tmp_path_factory.mktemp("ledger") / "runs.txt")
    await _project()
    ids, _tips = await _tasks(
        tmp_path, [({"one.py": "x = 1\n"}, None), ({"two.py": "x = 2\n"}, None)]
    )
    await _in_a_build(*ids)
    for task_id in ids:
        await _approve(app, auth_headers, task_id)

    at_the_verdict: List[Any] = []
    decide = landing_queue._decide

    async def read_then_decide(*args, **kwargs):
        if not at_the_verdict:
            async with async_session_factory() as db:
                frame = await task_stage_push.stage_frame(db, "proj-test", {ids[0]}, set())
            at_the_verdict.append((await _reads(app, auth_headers, *ids), frame))
        return await decide(*args, **kwargs)

    monkeypatch.setattr(landing_queue, "_decide", read_then_decide)
    try:
        await landing_queue.drain()
    finally:
        landing_queue.cancel_timers()

    [(reads, frame)] = at_the_verdict
    for task_id in ids:
        assert (reads[task_id]["stage"], reads[task_id]["check"]) == (
            "landing",
            {"kind": "landing", "state": "passed"},
        ), reads
    assert {row["id"] for row in frame["tasks"]} == set(ids), "a batch's frame names all its tasks"
    assert {row["stage"] for row in frame["tasks"]} == {"landing"}


async def test_a_checkout_being_prepared_pushes_preparing_checkout_and_its_end(app, auth_headers):
    """Drive run 200412 (TSBVD-5): for ~1.5 s the build view showed Not started while the board and
    map showed Preparing checkout. The stage lives in memory, not in a commit, so the
    `workspace_preparing` event itself must push it -- and `workspace_prepared` the stage after."""
    from hub import workspace_preparation
    from hub.db.engine import async_session_factory
    from hub.db.models import Task

    async with async_session_factory() as db:
        db.add(Task(id="task-push-prep", project_id="proj-test", title="p", status="assigned"))
        await db.commit()
    queue = sse_manager.subscribe("proj-test")
    try:
        async with workspace_preparation.preparing(
            "proj-test", agent="D", task_id="task-push-prep", conversation_id="conv-push-prep"
        ):
            during = _of(await _frames(queue), "task-push-prep")
            listed = await app.get(
                "/api/v1/projects/proj-test/tasks/task-push-prep", headers=auth_headers
            )
        after = _of(await _frames(queue), "task-push-prep")
    finally:
        sse_manager.unsubscribe("proj-test", queue)

    assert during, "the preparation's start pushes the task's stage"
    assert during[-1]["stage"] == listed.json()["stage"] == "preparing_checkout"
    assert after and after[-1]["stage"] == "not_started", "its end pushes the stage after it"
