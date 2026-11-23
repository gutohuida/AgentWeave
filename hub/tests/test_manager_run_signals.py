"""A manager run is announced when it starts and when it ends (`background-manager-work-you-can-see`).

BWYCS-2, the design's D1-D3: every job's background entry point runs inside `manager.manager_run`,
which publishes `manager_run_started`, holds the run in this process's registry of runs in progress
(`GET /manager/runs/running`), and on every exit records the end on `manager_job_fired` and
publishes `manager_run_ended` once. A failure stays listed by `GET /manager/runs/unseen-failures`
until `POST /manager/runs/seen` or a later run on the same item. The mender's runs publish the same
two events from their lifecycle. As in `test_vault_spec_check.py` the spec-vault-check worker is
faked; the real spawn is the acceptance drive's (`scripts/drive/background_work_drive.py`).
"""

import asyncio
import json
import threading

import pytest
from sqlalchemy import select

import hub.conversation_titles as conversation_titles
from hub import manager, stalls, vault_spec_check
from hub.api.v1 import agent_trigger
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Conversation, EventLog, Run, Stall
from hub.sse import sse_manager

from .test_manager_jobs import _conversation, _runner, _sync_agent
from .test_spec_documents_api import (  # noqa: F401  (run_headers is a fixture)
    PATH,
    _create,
    run_headers,
)
from .test_title_generation import _answered
from .test_vault_spec_check import (  # noqa: F401  (worker is a fixture)
    JANUARY,
    JOB,
    PROJECT,
    _check_now,
    _enable,
    _fact,
    _requirement,
    _saved,
    _source,
    worker,
)

PROJECT_ID = "proj-test"
RUNS = f"{PROJECT}/manager/runs"


def _events(queue) -> list:
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


def _drain(queue) -> list:
    """Every manager-run event the subscriber holds, as (event, data), in arrival order."""
    events = []
    while not queue.empty():
        event = queue.get_nowait()
        if event.event in (manager.RUN_STARTED_EVENT, manager.RUN_ENDED_EVENT):
            events.append((event.event, json.loads(event.data)))
    return events


async def _job_firings() -> list:
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(EventLog)
                    .where(EventLog.event_type == manager.FIRED_EVENT)
                    .order_by(EventLog.timestamp, EventLog.id)
                )
            )
            .scalars()
            .all()
        )
    return [row.data for row in rows if (row.data or {}).get("job") == JOB]


async def _ready_document(app, auth_headers, run_headers, tmp_path) -> None:  # noqa: F811
    january = await _source(app, auth_headers, JANUARY, "2026-01-10")
    await _fact(app, auth_headers, tmp_path, january, "Refunds up to 300 need none.")
    await _enable(app, auth_headers)
    await _create(app, auth_headers)
    await _saved(app, run_headers, _requirement("r1", "Refunds up to 3,000 need none."))


async def _running(app, auth_headers) -> list:
    listed = await app.get(f"{RUNS}/running", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    return listed.json()["runs"]


async def _unseen(app, auth_headers) -> list:
    listed = await app.get(f"{RUNS}/unseen-failures", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    return listed.json()["failures"]


# ---------------------------------------------------------------------------
# end-pushed-without-reload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_end_pushed_without_reload(
    app, auth_headers, run_headers, worker, tmp_path  # noqa: F811
) -> None:
    """Check now's run reaches a stream subscriber as started, then ended, with nothing asked of
    the Hub in between: the subscriber only reads its queue."""
    await _ready_document(app, auth_headers, run_headers, tmp_path)
    queue = sse_manager.subscribe(PROJECT_ID)
    during: list = []

    async def at_spawn() -> None:
        # Mid-run: the start is already on the stream, and the end is not.
        if not during:
            during.extend(_drain(queue))

    try:
        worker([], None, on_call=at_spawn)
        assert (await _check_now(app, auth_headers)).status_code == 202
        after = _drain(queue)

        assert [name for name, _ in during] == [manager.RUN_STARTED_EVENT]
        started = during[0][1]
        assert started["job"] == JOB
        assert started["subject"] == {"document": PATH}
        assert started["trigger"] == vault_spec_check.REQUESTED
        assert started["initiator"] == "operator"
        assert started["run_id"].startswith("mrun-") and len(started["run_id"]) == 17
        assert started["started_at"].endswith("+00:00")

        assert [name for name, _ in after] == [manager.RUN_ENDED_EVENT]
        ended = after[0][1]
        assert ended["run_id"] == started["run_id"]
        assert ended["started_at"] == started["started_at"]
        assert ended["outcome"] == "empty" and ended["ended_at"] >= started["started_at"]
        assert isinstance(ended["duration_ms"], int)

        # A failure: the ended event carries its reason.
        assert (await _check_now(app, auth_headers)).status_code == 202
        failed = _drain(queue)
        assert [name for name, _ in failed] == [manager.RUN_STARTED_EVENT, manager.RUN_ENDED_EVENT]
        assert failed[1][1]["outcome"] == "failed"
        assert "boom" in failed[1][1]["detail"]
    finally:
        sse_manager.unsubscribe(PROJECT_ID, queue)

    # The end is the run's `manager_job_fired`, carrying its id, initiator and start.
    firings = await _job_firings()
    assert [f["run_id"] for f in firings] == [started["run_id"], failed[0][1]["run_id"]]
    assert all(f["initiator"] == "operator" for f in firings)
    assert firings[0]["started_at"] == started["started_at"]
    assert await _running(app, auth_headers) == []


# ---------------------------------------------------------------------------
# silent-paths-end
# ---------------------------------------------------------------------------


async def _one_run(project_id: str, path: str, trigger: str = vault_spec_check.TRIGGER) -> tuple:
    """Run the background entry point once; answer its stream events and its recorded firing."""
    queue = sse_manager.subscribe(project_id)
    try:
        before = len(await _job_firings())
        await vault_spec_check.check_in_background(project_id, path, trigger=trigger)
        events = _drain(queue)
    finally:
        sse_manager.unsubscribe(project_id, queue)
    firings = (await _job_firings())[before:]
    return events, firings


def _ended_once(events: list, firings: list) -> dict:
    assert [name for name, _ in events] == [manager.RUN_STARTED_EVENT, manager.RUN_ENDED_EVENT]
    run_id = events[0][1]["run_id"]
    assert events[1][1]["run_id"] == run_id
    assert [f["run_id"] for f in firings] == [run_id]
    assert manager.running(PROJECT_ID) == []
    return {**events[1][1], "recorded": firings[0]}


@pytest.mark.asyncio
async def test_silent_paths_end(
    app, auth_headers, run_headers, worker, tmp_path, monkeypatch  # noqa: F811
) -> None:
    """(a) no requirements, (b) a refused check, (c) a worker that raises, (d) the job on with no
    runner: each run is announced as ended and recorded with a reason; none stays in progress."""
    await _enable(app, auth_headers)
    await _create(app, auth_headers)
    fake = worker()

    # (a) A document with no requirements: nothing to compare, said so.
    ended = _ended_once(*await _one_run(PROJECT_ID, PATH))
    assert ended["outcome"] == "empty"
    assert "no requirements" in ended["detail"]
    assert ended["recorded"]["outcome"] == "empty" and ended["recorded"]["detail"]

    # (b) A check refused: an unknown document.
    ended = _ended_once(*await _one_run(PROJECT_ID, "spec/changes/nothing/spec.json"))
    assert ended["outcome"] == "failed"
    assert "No document" in ended["detail"]

    # (c) The worker raises.
    january = await _source(app, auth_headers, JANUARY, "2026-01-10")
    await _fact(app, auth_headers, tmp_path, january, "Refunds up to 300 need none.")
    await _saved(app, run_headers, _requirement("r1", "Refunds up to 3,000 need none."))

    async def raising(**kwargs):
        raise RuntimeError("the worker fell over")

    monkeypatch.setattr(vault_spec_check, "run_worker", raising)
    ended = _ended_once(*await _one_run(PROJECT_ID, PATH))
    assert ended["outcome"] == "failed"
    assert "the worker fell over" in ended["detail"]
    assert ended["recorded"]["detail"] == ended["detail"]

    # (d) The job on, with no runner.
    async with async_session_factory() as db:
        await manager.set_job(db, PROJECT_ID, JOB, runner_id=None)
        await db.commit()
    ended = _ended_once(*await _one_run(PROJECT_ID, PATH))
    assert ended["outcome"] == "failed"
    assert "has no runner" in ended["detail"]
    assert fake.calls == []

    # Off: no run at all, so nothing is announced or recorded.
    async with async_session_factory() as db:
        await manager.set_job(db, PROJECT_ID, JOB, enabled=False)
        await db.commit()
    events, firings = await _one_run(PROJECT_ID, PATH)
    assert events == [] and firings == []


# ---------------------------------------------------------------------------
# reload-mid-run, restart-clears-running
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_running_now_is_read_mid_run_and_a_restart_clears_it(
    app, auth_headers, run_headers, worker, tmp_path  # noqa: F811
) -> None:
    """restart-clears-running: a run in progress is read with its start in Hub time; after a
    restart (this process's registry gone, as it goes with the process) none is shown, and nothing
    persisted could bring one back."""
    await _ready_document(app, auth_headers, run_headers, tmp_path)
    release = asyncio.Event()
    spawned = asyncio.Event()

    async def hold() -> None:
        spawned.set()
        await release.wait()

    worker([], on_call=hold)
    work = asyncio.create_task(
        vault_spec_check.check_in_background(PROJECT_ID, PATH, trigger=vault_spec_check.TRIGGER)
    )
    try:
        await asyncio.wait_for(spawned.wait(), 10)
        runs = await _running(app, auth_headers)
        assert len(runs) == 1
        run = runs[0]
        assert run["job"] == JOB and run["subject"] == {"document": PATH}
        assert run["initiator"] == "autonomous" and run["conversation_id"] is None
        assert run["started_at"].endswith("+00:00")
        # Nothing about the run in progress is in the database to outlive the process.
        async with async_session_factory() as db:
            stored = (await db.execute(select(EventLog.data))).scalars().all()
        assert not any((data or {}).get("run_id") == run["run_id"] for data in stored)

        # The restart: the process's memory goes, with the work it held.
        saved = dict(manager._running)
        manager._running.clear()
        assert await _running(app, auth_headers) == []
        manager._running.update(saved)
    finally:
        release.set()
        await asyncio.wait_for(work, 10)
    assert await _running(app, auth_headers) == []


# ---------------------------------------------------------------------------
# failure-persists (unseen)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unseen_failure_persists_until_seen_or_run_again(
    app, auth_headers, run_headers, worker, tmp_path  # noqa: F811
) -> None:
    """failure-persists: a failed check is listed as unseen across a restart, until it is marked
    seen; a later run on the same document clears it too, and is cleared while it runs."""
    await _ready_document(app, auth_headers, run_headers, tmp_path)
    release = asyncio.Event()
    holding = asyncio.Event()

    async def maybe_hold() -> None:
        if not release.is_set():
            holding.set()
            await release.wait()

    release.set()
    worker(None, None, [], on_call=maybe_hold)

    assert (await _check_now(app, auth_headers)).status_code == 202
    failures = await _unseen(app, auth_headers)
    assert len(failures) == 1
    failure = failures[0]
    assert failure["job"] == JOB and failure["subject"] == {"document": PATH}
    assert "boom" in failure["detail"] and failure["ended_at"].endswith("+00:00")

    # Read from the record, so a restart (the registry gone) leaves it listed.
    manager._running.clear()
    assert [f["run_id"] for f in await _unseen(app, auth_headers)] == [failure["run_id"]]

    # Seen: gone, and stays gone; an unknown id is ignored; open views are told after the commit.
    queue = sse_manager.subscribe(PROJECT_ID)
    try:
        seen = await app.post(
            f"{RUNS}/seen",
            json={"run_ids": [failure["run_id"], "mrun-000000000000"]},
            headers=auth_headers,
        )
        assert seen.status_code == 204, seen.text
        told = [json.loads(e.data) for e in _events(queue) if e.event == manager.SEEN_EVENT]
    finally:
        sse_manager.unsubscribe(PROJECT_ID, queue)
    assert told == [{"run_ids": [failure["run_id"]]}]
    assert await _unseen(app, auth_headers) == []
    again = await app.post(
        f"{RUNS}/seen", json={"run_ids": [failure["run_id"]]}, headers=auth_headers
    )
    assert again.status_code == 204
    async with async_session_factory() as db:
        marks = (
            (
                await db.execute(
                    select(EventLog.data).where(EventLog.event_type == manager.SEEN_EVENT)
                )
            )
            .scalars()
            .all()
        )
    assert marks == [{"run_id": failure["run_id"]}]

    # A second failure, then the same check run again: cleared while it runs, and after it.
    assert (await _check_now(app, auth_headers)).status_code == 202
    second = await _unseen(app, auth_headers)
    assert len(second) == 1 and second[0]["run_id"] != failure["run_id"]
    release.clear()
    work = asyncio.create_task(
        vault_spec_check.check_in_background(PROJECT_ID, PATH, trigger=vault_spec_check.TRIGGER)
    )
    try:
        await asyncio.wait_for(holding.wait(), 10)
        assert await _unseen(app, auth_headers) == []
    finally:
        release.set()
        await asyncio.wait_for(work, 10)
    assert await _unseen(app, auth_headers) == []


# ---------------------------------------------------------------------------
# titles_and_mender (top-bar-count)
# ---------------------------------------------------------------------------


async def _mender_with_running_run() -> str:
    """The Hub's mender agent, one stall it was woken on, and its run in progress in the stall's
    thread. Answers the run's id."""
    async with async_session_factory() as db:
        db.add(
            Agent(
                id="ag-mender",
                project_id=PROJECT_ID,
                name=stalls.MENDER,
                config={"hub_role": stalls.HUB_ROLE},
            )
        )
        db.add(
            Conversation(
                id="conv-mending", project_id=PROJECT_ID, agent=stalls.MENDER, origin="mender"
            )
        )
        db.add(
            Stall(
                id="stall-1",
                project_id=PROJECT_ID,
                key="integration_failed:task-x",
                cause="integration_failed",
                reason="The merge of task-x failed.",
                conversation_id="conv-mending",
            )
        )
        db.add(
            Run(
                id="run-mending",
                project_id=PROJECT_ID,
                agent=stalls.MENDER,
                conversation_id="conv-mending",
                status="running",
                turn_depth=0,
            )
        )
        await db.commit()
    return "run-mending"


@pytest.mark.asyncio
async def test_titles_and_mender_count_as_runs_in_progress(
    app, auth_headers, bind_runner, monkeypatch
) -> None:
    """top-bar-count: two conversation-title runs and one mender run in progress read as three
    runs; the mender's carries its stall and conversation, and its start and end are published
    as a manager run's."""
    await _sync_agent(app, auth_headers)
    first = await _conversation(app, auth_headers, "Investigate the flaky checkout test")
    second = await _conversation(app, auth_headers, "Plan the release notes")
    await bind_runner("offline", cli="claude", model="claude-opus-5")
    titles_runner = await _runner(app, auth_headers, model="claude-haiku-4-5-20251001")
    await app.patch(
        f"{PROJECT}/manager/jobs/conversation-titles",
        json={"enabled": True, "runner_id": titles_runner},
        headers=auth_headers,
    )
    gate = threading.Event()
    entered = threading.Semaphore(0)

    def held_titler(cmd, cwd, env=None):
        entered.release()
        gate.wait(10)
        return _answered("A title")

    monkeypatch.setattr(conversation_titles, "_run_titler", held_titler)
    monkeypatch.setattr(conversation_titles, "_gate", asyncio.Semaphore(2))
    mender_run = await _mender_with_running_run()

    queue = sse_manager.subscribe(PROJECT_ID)
    titling = [
        asyncio.create_task(
            conversation_titles.generate_conversation_title(
                project_id=PROJECT_ID, conversation_id=conversation_id
            )
        )
        for conversation_id in (first, second)
    ]
    try:
        for _ in range(2):
            assert await asyncio.to_thread(entered.acquire, True, 10)
        runs = await _running(app, auth_headers)
        assert len(runs) == 3
        assert sorted(run["job"] for run in runs) == ["conversation-titles"] * 2 + ["mender"]
        titled = {run["subject"]["conversation_id"] for run in runs if run["job"] != "mender"}
        assert titled == {first, second}
        mender = next(run for run in runs if run["job"] == "mender")
        assert mender["run_id"] == mender_run
        assert mender["conversation_id"] == "conv-mending"
        assert mender["subject"] == {"stall": "stall-1", "reason": "The merge of task-x failed."}
    finally:
        gate.set()
        await asyncio.gather(*titling)

    # The mender's lifecycle publishes the same two events as a job's run.
    async with async_session_factory() as db:
        await agent_trigger._broadcast_run_lifecycle(
            db, PROJECT_ID, "run_started", agent=stalls.MENDER, run_id=mender_run
        )
        run = await db.get(Run, mender_run)
        run.status = "failed"
        run.error = "The mender's CLI exited 1."
        await db.commit()
        await agent_trigger._broadcast_run_lifecycle(
            db, PROJECT_ID, "run_failed", agent=stalls.MENDER, run_id=mender_run
        )
    events = _drain(queue)
    sse_manager.unsubscribe(PROJECT_ID, queue)
    mender_events = [(name, data) for name, data in events if data["job"] == "mender"]
    assert [name for name, _ in mender_events] == [
        manager.RUN_STARTED_EVENT,
        manager.RUN_ENDED_EVENT,
    ]
    ended = mender_events[1][1]
    assert ended["run_id"] == mender_run and ended["conversation_id"] == "conv-mending"
    assert ended["outcome"] == "failed" and "exited 1" in ended["detail"]
    title_events = [name for name, data in events if data["job"] == "conversation-titles"]
    assert title_events.count(manager.RUN_STARTED_EVENT) == 2
    assert title_events.count(manager.RUN_ENDED_EVENT) == 2
    assert await _running(app, auth_headers) == []


@pytest.mark.asyncio
async def test_another_agents_run_is_not_a_manager_run(app, auth_headers) -> None:
    """An agent of the project's own named like no Hub role publishes no manager run."""
    async with async_session_factory() as db:
        db.add(Agent(id="ag-dev", project_id=PROJECT_ID, name="dev"))
        db.add(Run(id="run-dev", project_id=PROJECT_ID, agent="dev", status="running"))
        await db.commit()
    queue = sse_manager.subscribe(PROJECT_ID)
    try:
        async with async_session_factory() as db:
            await agent_trigger._broadcast_run_lifecycle(
                db, PROJECT_ID, "run_started", agent="dev", run_id="run-dev"
            )
        assert _drain(queue) == []
    finally:
        sse_manager.unsubscribe(PROJECT_ID, queue)
    assert await _running(app, auth_headers) == []


# ---------------------------------------------------------------------------
# new-jobs-join-without-ui-change (FR-14)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_job_added_later_joins_through_the_wrapper_alone(app, auth_headers) -> None:
    """A job key this slice never names runs through `manager_run` and is listed running, ended
    and, failed, unseen, with no other change."""
    queue = sse_manager.subscribe(PROJECT_ID)
    try:
        async with manager.manager_run(
            PROJECT_ID,
            job="briefing-note",
            trigger="overview_opened",
            subject={"note": "note-1"},
            initiator=manager.AUTONOMOUS,
        ) as run:
            runs = await _running(app, auth_headers)
            assert [(r["job"], r["subject"]) for r in runs] == [
                ("briefing-note", {"note": "note-1"})
            ]
            run.ends("failed", "The note could not be written.")
        events = _drain(queue)
    finally:
        sse_manager.unsubscribe(PROJECT_ID, queue)
    assert [name for name, _ in events] == [manager.RUN_STARTED_EVENT, manager.RUN_ENDED_EVENT]
    assert events[1][1]["outcome"] == "failed"
    failures = await _unseen(app, auth_headers)
    assert [(f["job"], f["detail"]) for f in failures] == [
        ("briefing-note", "The note could not be written.")
    ]
