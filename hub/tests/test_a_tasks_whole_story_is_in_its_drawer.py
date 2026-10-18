"""A task's whole story (`a-tasks-whole-story-is-in-its-drawer`, slice task-story).

`GET /tasks/{id}/story` joins what the Hub records about one task into one list, oldest first, with
a summary. The UI renders it in the order the route returns, so these tests pin that order: a route
that reversed it, or dropped a kind, fails here (CLAUDE.md: a consumer's test uses the route's
real order).
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    Run,
    RunDivergence,
    Task,
    TaskTransition,
    TurnUsage,
)

from .test_task_integration import (
    AGENT_BRANCH,
    AGENT_EVIDENCE,
    BASE,
    TASKS,
    commit_on_branch,
    drive_to,
    git,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-story-b", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-story-b",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_storyb-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_storyb-secret"}


async def a_worked_task(app, auth_headers, builder, tmp_path):
    """A task with a run that cost something, evidence, an approval that merged, and a divergence."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    task = await linked_task(app, auth_headers)
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    recorded = await app.post(
        AGENT_EVIDENCE,
        json={
            "identifier": "FR-1",
            "summary": "ran it",
            "task_id": task,
            "command": "python feature.py",
            "output": "hi\n",
            "covers": "full",
        },
        headers=builder,
    )
    assert recorded.status_code == 201, recorded.text
    git(tmp_path, "checkout", "-q", "main")
    # After the task was created, as every real run is.
    start = datetime.now(timezone.utc) + timedelta(seconds=1)
    async with async_session_factory() as session:
        run = await session.get(Run, "run-story-b")
        run.task_id = task
        run.status = "completed"
        run.started_at = start
        run.ended_at = start + timedelta(minutes=11)
        session.add(
            TurnUsage(
                id="tu-story-1",
                run_id="run-story-b",
                project_id="proj-test",
                agent="builder",
                status="measured",
                runner="claude",
                model="claude-sonnet-5-5",
                total_tokens=12000,
                api_equivalent_usd_micros=1_840_000,
            )
        )
        session.add(
            RunDivergence(
                id="rdv-story-1",
                project_id="proj-test",
                run_id="run-story-b",
                agent="builder",
                task_id=task,
                task_status_at_end="in_progress",
                run_exit_status="completed",
                policy_applied="surface",
                outcome="surfaced",
            )
        )
        await session.commit()
    walked = await drive_to(
        app, auth_headers, task, "assigned", "in_progress", "completed", "under_review", "approved"
    )
    assert walked.status_code == 200, walked.text
    return task, recorded.json()["id"]


async def story(app, auth_headers, task):
    response = await app.get(f"{TASKS}/{task}/story", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_the_story_is_oldest_first_and_carries_every_kind(
    app, auth_headers, builder, tmp_path
):
    task, _evidence = await a_worked_task(app, auth_headers, builder, tmp_path)

    body = await story(app, auth_headers, task)

    kinds = [event["kind"] for event in body["events"]]
    assert kinds[0] == "created"
    assert {"transition", "run", "evidence", "integration", "divergence"} <= set(kinds)
    stamps = [event["at"] for event in body["events"]]
    assert stamps == sorted(stamps), stamps
    transitions = [e for e in body["events"] if e["kind"] == "transition"]
    assert [(e["from"], e["to"]) for e in transitions][-1] == ("under_review", "approved")


@pytest.mark.asyncio
async def test_a_run_carries_its_model_duration_and_cost(app, auth_headers, builder, tmp_path):
    task, _evidence = await a_worked_task(app, auth_headers, builder, tmp_path)

    body = await story(app, auth_headers, task)

    [run] = [e for e in body["events"] if e["kind"] == "run"]
    assert run["agent"] == "builder"
    assert run["model"] == "claude-sonnet-5-5"
    assert run["duration_seconds"] == 660
    assert run["cost_usd"] == 1.84
    assert body["summary"]["runs"] == 1
    assert body["summary"]["cost_usd"] == 1.84


@pytest.mark.asyncio
async def test_evidence_carries_its_proof_and_its_reviews(app, auth_headers, builder, tmp_path):
    task, evidence = await a_worked_task(app, auth_headers, builder, tmp_path)

    body = await story(app, auth_headers, task)

    [piece] = [e for e in body["events"] if e["kind"] == "evidence"]
    assert piece["id"] == evidence
    assert piece["evidence"]["command"] == "python feature.py"
    assert piece["evidence"]["requirement"]["statement"] == "It lists what is due today"
    # The operator's approval decided it (vis-D4): one review, recorded on the piece.
    assert [(r["decision"], r["actor_kind"]) for r in piece["reviews"]] == [
        ("accepted", "operator")
    ]
    assert body["summary"]["evidence"] == {"accepted": 1, "rejected": 0, "awaiting": 0}


@pytest.mark.asyncio
async def test_a_merge_and_an_override_reach_the_summary(app, auth_headers, builder, tmp_path):
    task, _evidence = await a_worked_task(app, auth_headers, builder, tmp_path)
    from sqlalchemy import select

    async with async_session_factory() as session:
        transition = (
            await session.execute(
                select(TaskTransition).where(
                    TaskTransition.task_id == task, TaskTransition.to_status == "approved"
                )
            )
        ).scalar_one()
        transition.override_reason = "the flaky suite fails on main too"
        await session.commit()

    body = await story(app, auth_headers, task)

    [integration] = [e for e in body["events"] if e["kind"] == "integration"]
    assert integration["outcome"] == "merged"
    assert body["summary"]["merged"] == [integration["commit_sha"]]
    approved = [e for e in body["events"] if e["kind"] == "transition" and e["to"] == "approved"]
    assert approved[0]["override_reason"] == "the flaky suite fails on main too"
    assert body["summary"]["overrides"] == 1


@pytest.mark.asyncio
async def test_an_unknown_task_has_no_story(app, auth_headers):
    response = await app.get(f"{TASKS}/task-nope/story", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_task_with_nothing_yet_has_a_one_line_story(app, auth_headers, builder, tmp_path):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    task = await linked_task(app, auth_headers)

    body = await story(app, auth_headers, task)

    assert [event["kind"] for event in body["events"]] == ["created"]
    assert body["summary"]["runs"] == 0 and body["summary"]["cost_usd"] is None
    async with async_session_factory() as session:
        assert (await session.get(Task, task)).status == body["task"]["status"]


@pytest.mark.asyncio
async def test_refused_turns_and_a_failed_checkout_release_are_in_the_story(
    app, auth_headers, builder, tmp_path
):
    """F711: two refused deliveries and `task_worktree_release_failed` left ~13 minutes of a jammed
    task out of its whole story. A turn that ran normally is its run, so it is not told twice."""
    from hub.db.models import InboundQueueEntry
    from hub.utils import persist_event

    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    task = await linked_task(app, auth_headers)
    start = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        session.add(
            InboundQueueEntry(
                id="entry-story-refused",
                project_id="proj-test",
                agent="beta",
                origin_type="operator",
                content="work",
                hop_depth=0,
                state="queued",
                task_id=task,
                arrived_at=start + timedelta(seconds=1),
                delivery_attempts=2,
                waiting_reason=f"Could not prepare the checkout for task {task}: refusing path",
            )
        )
        session.add(
            InboundQueueEntry(
                id="entry-story-ran",
                project_id="proj-test",
                agent="beta",
                origin_type="operator",
                content="work",
                hop_depth=0,
                state="delivered",
                task_id=task,
                arrived_at=start,
            )
        )
        await persist_event(
            session,
            "proj-test",
            "task_worktree_release_failed",
            {"task_id": task, "reason": "Permission denied"},
            severity="warn",
            commit=False,
        )
        await persist_event(
            session,
            "proj-test",
            "task_worktree_release_failed",
            {"task_id": "task-someone-else", "reason": "not this one"},
            severity="warn",
            commit=False,
        )
        await session.commit()

    body = await story(app, auth_headers, task)

    turns = [event for event in body["events"] if event["kind"] == "turn"]
    assert [t["id"] for t in turns] == ["entry-story-refused"]
    assert "Could not prepare the checkout" in turns[0]["refusal"]
    assert turns[0]["agent"] == "beta" and turns[0]["attempts"] == 2
    (workspace,) = [event for event in body["events"] if event["kind"] == "workspace"]
    assert workspace["outcome"] == "release_failed"
    assert workspace["reason"] == "Permission denied"
    stamps = [event["at"] for event in body["events"]]
    assert stamps == sorted(stamps), "still oldest first"


assert BASE
