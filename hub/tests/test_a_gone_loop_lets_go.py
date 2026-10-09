"""A loop that is gone lets go of its document (F53, F157).

A replacement loop on a document adopts the unfinished tasks an archived loop left, and records the
move; materialise stamps only a live loop; and a create that names a document on a job that is not a
loop is refused rather than dropped.
"""

import pytest
from sqlalchemy import select

from hub import spec_tasks
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AIJob, Loop, SpecDocument, SpecRequirement, Task
from hub.spec_lifecycle import Actor
from hub.spec_payload import SCHEMA_VERSION

PROJECT = "proj-test"
JOBS = f"/api/v1/projects/{PROJECT}/jobs"
LOOPS = f"/api/v1/projects/{PROJECT}/loops"
TASKS = f"/api/v1/projects/{PROJECT}/tasks"
DOC = "doc-gone-loop"
ACTOR = Actor(kind="operator", name="operator")


async def _flow(app, auth_headers, name, document=DOC, agent="kimi"):
    created = await app.post(
        JOBS,
        json={
            "name": name,
            "agent": agent,
            "message": "Work the queue",
            "cron": "0 9 * * *",
            "purpose": f"Drive {document}",
            "spec_document_id": document,
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"], created.json()["loop"]["id"]


async def _archive(app, auth_headers, job_id):
    archived = await app.post(f"{JOBS}/{job_id}/archive", headers=auth_headers)
    assert archived.status_code == 200, archived.text


async def _seed(task_id, status, loop_id, assignee=None, document=DOC):
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                project_id=PROJECT,
                title=f"Work {task_id}",
                status=status,
                assignee=assignee,
                spec_document_id=document,
                loop_id=loop_id,
            )
        )
        await session.commit()


async def _loop_of(task_id):
    async with async_session_factory() as session:
        return (await session.get(Task, task_id)).loop_id


async def _adopted_events(app, auth_headers, loop_id):
    detail = await app.get(f"{LOOPS}/{loop_id}", headers=auth_headers)
    assert detail.status_code == 200, detail.text
    return [e for e in detail.json()["events"] if e["event_type"] == "loop_tasks_adopted"]


async def _handed_over(app, auth_headers):
    """Loop 1 claims DOC and adopts three tasks; it is archived; loop 2 claims DOC."""
    job_one, loop_one = await _flow(app, auth_headers, "First")
    await _seed("t-pending", "pending", loop_one)
    await _seed("t-working", "in_progress", loop_one, assignee="kimi")
    await _seed("t-done", "approved", loop_one)
    await _archive(app, auth_headers, job_one)
    _, loop_two = await _flow(app, auth_headers, "Second")
    return loop_one, loop_two


@pytest.mark.asyncio
async def test_1_1_a_successor_adopts_the_unfinished_tasks_only(app, auth_headers):
    loop_one, loop_two = await _handed_over(app, auth_headers)

    assert await _loop_of("t-pending") == loop_two
    assert await _loop_of("t-working") == loop_two
    assert await _loop_of("t-done") == loop_one
    async with async_session_factory() as session:
        assert (await session.get(Task, "t-working")).assignee == "kimi"


@pytest.mark.asyncio
async def test_1_2_the_successors_queue_lists_the_moved_tasks(app, auth_headers):
    _, loop_two = await _handed_over(app, auth_headers)

    listed = await app.get(TASKS, params={"loop_id": loop_two}, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert sorted(t["id"] for t in listed.json()["tasks"]) == ["t-pending", "t-working"]


@pytest.mark.asyncio
async def test_1_3_control_a_live_loops_document_cannot_be_claimed(app, auth_headers):
    _, loop_one = await _flow(app, auth_headers, "Live")
    await _seed("t-live", "pending", loop_one)

    refused = await app.post(
        JOBS,
        json={
            "name": "Rival",
            "agent": "kimi",
            "message": "Work",
            "cron": "0 9 * * *",
            "purpose": "Take it",
            "spec_document_id": DOC,
        },
        headers=auth_headers,
    )
    assert refused.status_code == 409, refused.text
    assert await _loop_of("t-live") == loop_one


async def _seed_loops_naming(document, order):
    """Loops written directly, in *order* (`"archived"` / `"live"`), so row order is controlled."""
    from datetime import datetime, timezone

    ids = {}
    async with async_session_factory() as session:
        for kind in order:
            job_id = f"job-{kind}-mat"
            loop_id = f"loop-{kind}-mat"
            session.add(
                AIJob(
                    id=job_id,
                    project_id=PROJECT,
                    name=f"{kind} mat",
                    agent="kimi",
                    message="m",
                    cron="0 9 * * *",
                )
            )
            await session.flush()
            session.add(
                Loop(
                    id=loop_id,
                    project_id=PROJECT,
                    job_id=job_id,
                    purpose="p",
                    spec_document_id=document,
                    archived_at=datetime.now(timezone.utc) if kind == "archived" else None,
                )
            )
            ids[kind] = loop_id
        await session.commit()
    return ids


async def _materialise_into(document_id, key):
    async with async_session_factory() as db:
        document = SpecDocument(
            id=document_id,
            project_id=PROJECT,
            path=f"spec/changes/{document_id}/spec.json",
            title=document_id,
            phase="approved",
            kind="change-spec",
        )
        db.add(document)
        db.add(
            SpecRequirement(
                id=f"req-{document_id}",
                project_id=PROJECT,
                document_id=document_id,
                identifier="FR-1",
                key="alpha",
                digest="d" * 64,
            )
        )
        await db.commit()
        payload = {
            "schema_version": SCHEMA_VERSION,
            "tasks": [{"key": key, "description": f"Build {key}.", "requirements": ["alpha"]}],
        }
        created = await spec_tasks.materialise(db, document, payload, actor=ACTOR)
        await db.commit()
    return created


@pytest.mark.asyncio
@pytest.mark.parametrize("order", [("archived", "live"), ("live", "archived")])
async def test_1_4_materialise_stamps_the_live_loop_whatever_the_row_order(app, order):
    ids = await _seed_loops_naming("doc-mat-both", order)
    created = await _materialise_into("doc-mat-both", "build")
    assert [t.loop_id for t in created] == [ids["live"]]


@pytest.mark.asyncio
async def test_1_5_materialise_leaves_a_task_unowned_when_only_an_archived_loop_names_it(app):
    await _seed_loops_naming("doc-mat-gone", ("archived",))
    created = await _materialise_into("doc-mat-gone", "build")
    assert [t.loop_id for t in created] == [None]


@pytest.mark.asyncio
async def test_1_6_a_document_on_a_job_that_is_not_a_loop_is_refused(app, auth_headers):
    refused = await app.post(
        JOBS,
        json={
            "name": "Not a loop",
            "agent": "kimi",
            "message": "ping",
            "cron": "0 9 * * *",
            "spec_document_id": DOC,
        },
        headers=auth_headers,
    )
    assert refused.status_code == 400, refused.text
    assert "spec_document_id describes a loop" in refused.text
    listed = await app.get(JOBS, headers=auth_headers)
    assert "Not a loop" not in [j["name"] for j in listed.json()]


@pytest.mark.asyncio
async def test_1_7_control_a_document_with_a_purpose_still_creates_a_loop(app, auth_headers):
    _, loop_id = await _flow(app, auth_headers, "With purpose")
    async with async_session_factory() as session:
        assert (await session.get(Loop, loop_id)).spec_document_id == DOC


@pytest.mark.asyncio
async def test_1_9_the_move_is_recorded_against_both_loops(app, auth_headers):
    loop_one, loop_two = await _handed_over(app, auth_headers)

    for loop_id in (loop_one, loop_two):
        events = await _adopted_events(app, auth_headers, loop_id)
        assert len(events) == 1, loop_id
        data = events[0]["data"]
        assert data["from_loop"] == loop_one
        assert data["to_loop"] == loop_two
        assert sorted(data["task_ids"]) == ["t-pending", "t-working"]


@pytest.mark.asyncio
async def test_1_9_adopting_only_unowned_tasks_writes_no_event(app, auth_headers):
    await _seed("t-unowned", "pending", None)
    _, loop_id = await _flow(app, auth_headers, "Unowned")

    assert await _loop_of("t-unowned") == loop_id
    assert await _adopted_events(app, auth_headers, loop_id) == []


@pytest.mark.asyncio
async def test_1_9_a_claim_that_rolls_back_leaves_no_event_and_no_move(
    app, auth_headers, monkeypatch
):
    from hub.api.v1 import jobs as jobs_api

    job_one, loop_one = await _flow(app, auth_headers, "Gone")
    await _seed("t-stays", "pending", loop_one)
    await _archive(app, auth_headers, job_one)
    await _seed_loops_naming(DOC, ("live",))

    async def _no_conflict_check(*args, **kwargs):
        return None

    # A concurrent live claim is the only way past the check; the partial index is what stops it.
    monkeypatch.setattr(jobs_api, "_check_spec_document_conflict", _no_conflict_check)
    refused = await app.post(
        JOBS,
        json={
            "name": "Racer",
            "agent": "kimi",
            "message": "Work",
            "cron": "0 9 * * *",
            "purpose": "Lose the race",
            "spec_document_id": DOC,
        },
        headers=auth_headers,
    )
    assert refused.status_code == 409, refused.text
    assert await _loop_of("t-stays") == loop_one
    assert await _adopted_events(app, auth_headers, loop_one) == []


@pytest.mark.asyncio
async def test_1_11_control_an_ended_loop_still_holds_its_document_until_archived(
    app, auth_headers
):
    job_one, loop_one = await _flow(app, auth_headers, "Ends")
    async with async_session_factory() as session:
        loop = await session.get(Loop, loop_one)
        loop.ending_state = "finished"
        await session.commit()

    blocked = await app.post(
        JOBS,
        json={
            "name": "Successor",
            "agent": "kimi",
            "message": "Work",
            "cron": "0 9 * * *",
            "purpose": "Take over",
            "spec_document_id": DOC,
        },
        headers=auth_headers,
    )
    assert blocked.status_code == 409, blocked.text
    assert loop_one in blocked.text

    await _archive(app, auth_headers, job_one)
    _, loop_two = await _flow(app, auth_headers, "Successor after archive")
    assert loop_two != loop_one


@pytest.mark.asyncio
async def test_1_10_an_adopted_task_held_by_an_archived_agent_is_a_stall_not_a_briefing(
    app, auth_headers, bind_runner
):
    """Design D7: the walk names the archived assignee instead of selecting the task for them."""
    from hub.scheduler import decide_firing

    await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {"kimi": {"runner": "claude"}, "ada": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    for name in ("kimi", "ada"):
        await bind_runner(name, cli="claude")
    job_one, loop_one = await _flow(app, auth_headers, "First", agent="kimi")
    await _seed("t-working", "in_progress", loop_one, assignee="ada")
    await _archive(app, auth_headers, job_one)
    _, loop_two = await _flow(app, auth_headers, "Second", agent="kimi")
    assert await _loop_of("t-working") == loop_two
    async with async_session_factory() as session:
        agent = (await session.execute(select(Agent).where(Agent.name == "ada"))).scalar_one()
        agent.lifecycle = "archived"
        await session.commit()

    async with async_session_factory() as session:
        decision = await decide_firing(
            session, await session.get(Loop, loop_two), default_agent="kimi"
        )

    assert decision.selections == ()
    assert decision.stall_reason is not None
    assert "t-working" in decision.stall_reason
    assert "ada" in decision.stall_reason
    assert "archived" in decision.stall_reason
    async with async_session_factory() as session:
        task = await session.get(Task, "t-working")
        assert (task.status, task.assignee) == ("in_progress", "ada")
