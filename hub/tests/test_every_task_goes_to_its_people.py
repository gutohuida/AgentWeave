"""Every driver gives each task to its people (`the-build-plan-lives-in-the-spec-and-every-task-
goes-to-its-people`, task `people-get-their-tasks`).

A flow gives a task to its own builder, even one outside the build-wide builders or named to check
other work, and holds a task whose builder is not an open agent (FR-8). A check goes to the task's
checker as the build records it, else the build's default checker, and is held for a checker who is
not an open agent; at Fast none is handed out (FR-9). A hand build only places tasks on the board
with their builder and checker named (FR-10). The lead's brief names each task's people, and a task
it hands to someone other than its builder is recorded with who it went to (FR-11).

Named by acceptance criterion: `-k outside_the_list`, `-k not_open`, `-k checker`, `-k fast`,
`-k hand`, `-k lead`.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    InboundQueueEntry,
    Loop,
    Message,
    Run,
    SpecDocument,
    Task,
)
from hub.scheduler import JobScheduler, decide_firing
from hub.spec_payload import SCHEMA_VERSION
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

from .test_review_turn import _roster

P = "proj-test"
BASE = f"/api/v1/projects/{P}/project"
TASKS = f"/api/v1/projects/{P}/tasks"
AGENT_DOCS = "/api/v1/agent-actions/spec/documents"
HAND_OUT = "/api/v1/agent-actions/tasks/{}/hand-out"
PATH = "spec/changes/every-task-goes-to-its-people/spec.json"


def _scheduling():
    """`schedule_agent` answers "started" without spawning anything; queued input stays queued."""
    return patch(
        "hub.turn_scheduler.schedule_agent",
        AsyncMock(return_value=MagicMock(waiting_reason=None, terminal_failure=False)),
    )


async def _run_headers(run_id, agent, status="running"):
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as db:
        db.add(
            Run(
                id=run_id,
                project_id=P,
                agent=agent,
                status=status,
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await db.commit()
    return {"Authorization": f"Bearer {token}"}


def _document(tasks, **delivery):
    keys = [task["key"] for task in tasks]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Every task goes to its people",
        "problem": "A task named for somebody goes to somebody else.",
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
        "requirements": [
            {"key": f"r-{key}", "statement": f"It does {key}", "modal": "MUST"} for key in keys
        ],
        "acceptance_criteria": [
            {
                "key": f"c-{key}",
                "requirement": f"r-{key}",
                "given": "g",
                "when": "w",
                "then": "t",
                "how_to_check": "pytest",
                "checked_by": "agent",
            }
            for key in keys
        ],
        "tasks": [
            {"description": f"Build {task['key']}", "requirements": [f"r-{task['key']}"], **task}
            for task in tasks
        ],
        "delivery": {
            "mode": "flow",
            "agent": "dev",
            "stop_when_queue_empties": True,
            "cron": "*/10 * * * *",
            **delivery,
        },
    }


async def _approved(app, auth_headers, document):
    author = await _run_headers("run-people-author", "author")
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "People"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(AGENT_DOCS, json={"path": PATH, "document": document}, headers=author)
    assert saved.status_code == 200, saved.text
    async with async_session_factory() as db:  # the author's turn is over
        (await db.get(Run, "run-people-author")).status = "completed"
        await db.commit()
    read = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    approved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={
            "reason": "",
            "approve_anyway": True,
            "content_version": read.json()["content_version"],
        },
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text


async def _build(app, auth_headers, **settings):
    with _scheduling():
        built = await app.post(
            f"{BASE}/documents/build", params={"path": PATH}, json=settings, headers=auth_headers
        )
    assert built.status_code == 200, built.text
    return built.json()["build_outcome"]


async def _rows(model, *where):
    async with async_session_factory() as db:
        return list((await db.execute(select(model).where(*where))).scalars())


async def _tasks():
    (document,) = await _rows(SpecDocument, SpecDocument.path == PATH)
    return {t.spec_task_key: t for t in await _rows(Task, Task.spec_document_id == document.id)}


async def _decide():
    (loop,) = await _rows(Loop)
    (job,) = await _rows(AIJob, AIJob.id == loop.job_id)
    async with async_session_factory() as db:
        return await decide_firing(db, await db.get(Loop, loop.id), default_agent=job.agent)


async def _fire():
    (loop,) = await _rows(Loop)
    with _scheduling():
        async with async_session_factory() as db:
            job = await db.get(AIJob, loop.job_id)
            await JobScheduler()._do_fire_job(job, "scheduled", db)


async def _work(task_id, agent):
    """*agent* takes *task_id* and completes it, as its own bound run."""
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        actor = run_actor(f"run-{agent}-{task_id}", agent)
        await apply_transition(db, task, "in_progress", actor)
        await apply_transition(db, task, "completed", actor)
        await db.commit()


async def _clear_assignee(task_id):
    async with async_session_factory() as db:
        (await db.get(Task, task_id)).assignee = None
        await db.commit()


def _picks(decision):
    return [(s.task.id, s.agent, s.is_review) for s in decision.selections]


@pytest.fixture
def reviewable(monkeypatch):
    """Every finished task has a commit to review, so the ladder is what decides."""
    from hub import task_integration
    from hub.requirement_evidence import ReviewTarget

    async def _reviewable(session, task, root=None):
        return ReviewTarget(commit_sha="a" * 40, branch=f"agentweave/task/{task.id}")

    monkeypatch.setattr(task_integration, "review_target", _reviewable)


# ---------------------------------------------------------------------------------------------
# ac-flow-builder-outside-list (flow-gives-task-to-its-builder)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_flow_gives_a_task_to_its_builder_outside_the_list(app, auth_headers, bind_runner):
    """Builders [dev]; t1's builder is opus, who is also t2's checker (F767 withholds checkers from
    fresh work). With opus busy t1 goes to nobody, dev included; with opus free it goes to opus. The
    same holds once t1's holder is cleared: the task's builder, not the pool, decides."""
    await _roster(app, auth_headers, bind_runner, "dev", "opus", "qa")
    await _approved(
        app,
        auth_headers,
        _document(
            [
                {"key": "t1", "builder": "opus"},
                {"key": "t2", "builder": "dev", "checker": "opus"},
            ]
        ),
    )
    await _build(app, auth_headers, driver="flow", level="reviewed", builders=["dev"])
    t1 = (await _tasks())["t1"]
    assert (t1.builder, t1.assignee) == ("opus", "opus")
    await _run_headers("run-opus-busy", "opus")

    for cleared in (False, True):
        if cleared:
            await _clear_assignee(t1.id)
        async with async_session_factory() as db:
            (await db.get(Run, "run-opus-busy")).status = "running"
            await db.commit()

        busy = await _decide()

        assert t1.id not in {s.task.id for s in busy.selections}, (cleared, busy)

        async with async_session_factory() as db:
            (await db.get(Run, "run-opus-busy")).status = "completed"
            await db.commit()

        free = await _decide()

        assert (t1.id, "opus", False) in _picks(free), (cleared, free)
        assert all(s.agent != "opus" or s.task.id == t1.id for s in free.selections)


# ---------------------------------------------------------------------------------------------
# F1092: the build's default builder, stored apart from `builders`
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_flow_gives_an_unnamed_task_only_to_the_default_builder(
    app, auth_headers, bind_runner
):
    """As build-7450d5263aed was built: default builder, empty `builders`, nobody on the tasks. The
    job's own agent dev and the idle other are free and neither takes anything; opus takes one task
    at a time, and while opus is busy the work waits."""
    await _roster(app, auth_headers, bind_runner, "dev", "opus", "other", "qa")
    await _approved(app, auth_headers, _document([{"key": "t1"}, {"key": "t2"}]))
    await _build(app, auth_headers, driver="flow", level="reviewed", builder="opus")
    tasks = await _tasks()
    assert (tasks["t1"].builder, tasks["t1"].assignee) == (None, None)

    free = await _decide()

    assert [(agent, review) for _, agent, review in _picks(free)] == [("opus", False)]
    assert _picks(free)[0][0] in {tasks["t1"].id, tasks["t2"].id}

    await _run_headers("run-opus-busy", "opus")

    busy = await _decide()

    assert _picks(busy) == [], busy


@pytest.mark.asyncio
async def test_a_default_builder_who_is_not_open_holds_the_work(app, auth_headers, bind_runner):
    """Nobody is quietly substituted for a default that was archived since: the task says who."""
    await _roster(app, auth_headers, bind_runner, "dev", "opus", "other", "qa")
    await _approved(app, auth_headers, _document([{"key": "t1"}]))
    await _build(app, auth_headers, driver="flow", level="reviewed", builder="opus")
    archived = await app.post(f"/api/v1/projects/{P}/agents/opus/archive", headers=auth_headers)
    assert archived.status_code in (200, 204), archived.text

    decision = await _decide()

    assert _picks(decision) == []
    assert "opus is not an open agent" in str(decision.unstaffed), decision


@pytest.mark.asyncio
async def test_a_task_naming_its_builder_still_goes_to_it_over_the_default(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, "dev", "opus", "other", "qa")
    await _approved(app, auth_headers, _document([{"key": "t1", "builder": "other"}]))
    await _build(app, auth_headers, driver="flow", level="reviewed", builder="opus")
    t1 = (await _tasks())["t1"]
    await _clear_assignee(t1.id)

    assert _picks(await _decide()) == [(t1.id, "other", False)]


@pytest.mark.asyncio
async def test_a_filled_builders_list_still_narrows_the_pool_beside_a_default(
    app, auth_headers, bind_runner
):
    """The list is the wider choice and stands as it did: both of its people may build, and the
    default outside it gets nothing it was not named for."""
    await _roster(app, auth_headers, bind_runner, "dev", "opus", "other", "qa")
    await _approved(app, auth_headers, _document([{"key": "t1"}, {"key": "t2"}]))
    await _build(
        app,
        auth_headers,
        driver="flow",
        level="reviewed",
        builder="opus",
        builders=["dev", "other"],
    )

    assert sorted(agent for _, agent, _ in _picks(await _decide())) == ["dev", "other"]


@pytest.mark.asyncio
async def test_a_build_with_no_default_and_no_list_leaves_any_free_agent(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, "dev", "other", "qa")
    await _approved(app, auth_headers, _document([{"key": "t1"}, {"key": "t2"}]))
    await _build(app, auth_headers, driver="flow", level="reviewed", builder="")

    assert len({agent for _, agent, _ in _picks(await _decide())}) == 2


# ---------------------------------------------------------------------------------------------
# ac-builder-not-open (flow-gives-task-to-its-builder)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_task_whose_builder_is_not_open_is_held_and_says_so(app, auth_headers, bind_runner):
    """t4 names ghost, who is not an agent; dev is a free builder. The flow gives t4 to nobody and
    the task's story says its builder ghost is not an open agent. On master the free dev took it."""
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    await _approved(app, auth_headers, _document([{"key": "t4", "builder": "ghost"}]))
    await _build(app, auth_headers, driver="flow", level="reviewed", builders=["dev"])
    t4 = (await _tasks())["t4"]
    assert (t4.builder, t4.assignee) == ("ghost", None)

    decision = await _decide()

    assert decision.selections == (), decision
    (reason,) = [why for task_id, why in decision.unstaffed if task_id == t4.id]
    assert "builder ghost is not an open agent" in reason

    await _fire()

    (task,) = await _rows(Task, Task.id == t4.id)
    assert (task.assignee, task.status) == (None, "pending")
    assert await _rows(InboundQueueEntry, InboundQueueEntry.agent == "dev") == []
    story = await app.get(f"{TASKS}/{t4.id}/story", headers=auth_headers)
    assert story.status_code == 200, story.text
    assert "builder ghost is not an open agent" in story.text


# ---------------------------------------------------------------------------------------------
# ac-check-to-checker (check-goes-to-its-checker)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_check_goes_to_its_checker(app, auth_headers, bind_runner, reviewable):
    """Reviewed flow; default checker qa. t1 names qa2, t2 names nobody, t3 names ghost. Once dev
    completes each: t1's check goes to qa2, t2's to qa, and t3's to nobody, its story saying its
    checker ghost is not an open agent."""
    await _roster(app, auth_headers, bind_runner, "dev", "qa", "qa2")
    await _approved(
        app,
        auth_headers,
        _document(
            [
                {"key": "t1", "builder": "dev", "checker": "qa2"},
                {"key": "t2", "builder": "dev"},
                {"key": "t3", "builder": "dev", "checker": "ghost"},
            ],
            checker="qa",
        ),
    )
    await _build(app, auth_headers, driver="flow", level="reviewed", builders=["dev"])
    tasks = await _tasks()
    for key in ("t1", "t2", "t3"):
        await _work(tasks[key].id, "dev")

    decision = await _decide()

    picks = _picks(decision)
    assert (tasks["t1"].id, "qa2", True) in picks, decision
    assert (tasks["t2"].id, "qa", True) in picks, decision
    assert tasks["t3"].id not in {task_id for task_id, _, _ in picks}
    (reason,) = [why for task_id, why in decision.unstaffed if task_id == tasks["t3"].id]
    assert "checker ghost is not an open agent" in reason

    await _fire()

    story = await app.get(f"{TASKS}/{tasks['t3'].id}/story", headers=auth_headers)
    assert "checker ghost is not an open agent" in story.text
    assert await _rows(InboundQueueEntry, InboundQueueEntry.review_task_id == tasks["t3"].id) == []


@pytest.mark.asyncio
async def test_the_checker_the_operator_chose_wins_over_the_documents(
    app, auth_headers, bind_runner, reviewable
):
    """The document names qa as t1's checker; the operator chose qa2 at Build. The check goes to
    qa2: the build is the decision, the document the recommendation. On master it went to qa."""
    await _roster(app, auth_headers, bind_runner, "dev", "qa", "qa2")
    await _approved(
        app, auth_headers, _document([{"key": "t1", "builder": "dev", "checker": "qa"}])
    )
    await _build(
        app,
        auth_headers,
        driver="flow",
        level="reviewed",
        builders=["dev"],
        task_checkers={"t1": "qa2"},
    )
    t1 = (await _tasks())["t1"]
    await _work(t1.id, "dev")

    assert _picks(await _decide()) == [(t1.id, "qa2", True)]


@pytest.mark.asyncio
async def test_a_check_never_goes_to_its_builder(app, auth_headers, bind_runner, reviewable):
    """t1's builder is also its checker: the check is held rather than self-reviewed or passed on."""
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    await _approved(
        app, auth_headers, _document([{"key": "t1", "builder": "dev", "checker": "dev"}])
    )
    await _build(app, auth_headers, driver="flow", level="reviewed", builders=["dev"])
    t1 = (await _tasks())["t1"]
    await _work(t1.id, "dev")

    decision = await _decide()

    assert decision.selections == (), decision
    assert [task_id for task_id, _ in decision.unstaffed] == [t1.id]


# ---------------------------------------------------------------------------------------------
# ac-fast-no-check (check-goes-to-its-checker)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_at_fast_no_check_is_handed_out(app, auth_headers, bind_runner, reviewable):
    """Fast flow, t1 names checker qa. Once t1 is completed the firing hands no check to anyone."""
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    await _approved(
        app, auth_headers, _document([{"key": "t1", "builder": "dev", "checker": "qa"}])
    )
    await _build(app, auth_headers, driver="flow", level="fast", builders=["dev"])
    t1 = (await _tasks())["t1"]
    await _work(t1.id, "dev")

    decision = await _decide()

    assert [s for s in decision.selections if s.is_review] == [], decision
    assert decision.approvals == (t1.id,)

    await _fire()

    assert await _rows(InboundQueueEntry, InboundQueueEntry.review_task_id == t1.id) == []
    assert await _rows(InboundQueueEntry, InboundQueueEntry.agent == "qa") == []


# ---------------------------------------------------------------------------------------------
# ac-hand-board (hand-only-places-on-the-board)
# ---------------------------------------------------------------------------------------------


async def _nothing_reached(agent):
    assert await _rows(Run, Run.agent == agent) == []
    assert await _rows(InboundQueueEntry, InboundQueueEntry.agent == agent) == []
    assert await _rows(Message, Message.recipient == agent) == []


@pytest.mark.asyncio
async def test_a_hand_build_places_tasks_on_the_board_and_starts_nothing(
    app, auth_headers, bind_runner
):
    """t1 names builder dev and checker qa; built by hand. The board shows t1 in Pending with dev
    as its builder and qa as its checker, and nothing reaches either agent -- not at the build, and
    not after dev completes t1."""
    await _roster(app, auth_headers, bind_runner, "dev", "qa")
    await _approved(
        app, auth_headers, _document([{"key": "t1", "builder": "dev", "checker": "qa"}])
    )
    await _build(app, auth_headers, driver="hand", level="reviewed")
    t1 = (await _tasks())["t1"]

    board = await app.get(TASKS, headers=auth_headers)
    assert board.status_code == 200, board.text
    (card,) = [task for task in board.json()["tasks"] if task["id"] == t1.id]
    assert (card["status"], card["builder"], card["checker"]) == ("pending", "dev", "qa")
    assert card["assignee"] == "dev"
    await _nothing_reached("dev")
    await _nothing_reached("qa")
    assert await _rows(Loop) == []

    await _work(t1.id, "dev")

    one = (await app.get(f"{TASKS}/{t1.id}", headers=auth_headers)).json()
    assert (one["status"], one["checker"]) == ("completed", "qa")
    await _nothing_reached("qa")


# ---------------------------------------------------------------------------------------------
# ac-lead-brief (lead-told-the-people)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_lead_is_told_each_tasks_people_and_a_hand_out_is_recorded(
    app, auth_headers, bind_runner
):
    """Lead build, lead architect; t1 names builder dev and checker qa. The brief names dev and qa
    for t1; the lead hands t1 to opus, and t1's history records that it went to opus, from the
    lead, with its named builder."""
    await _roster(app, auth_headers, bind_runner, "architect", "dev", "opus", "qa")
    await _approved(
        app, auth_headers, _document([{"key": "t1", "builder": "dev", "checker": "qa"}])
    )
    await _build(app, auth_headers, driver="lead", lead="architect", level="reviewed")
    t1 = (await _tasks())["t1"]

    (brief,) = await _rows(
        InboundQueueEntry,
        InboundQueueEntry.agent == "architect",
        InboundQueueEntry.task_id.is_(None),
    )
    assert f"{t1.id} [pending]" in brief.content
    assert "builder dev, checker qa" in brief.content

    lead = await _run_headers("run-architect-lead", "architect")
    with _scheduling():
        handed = await app.post(HAND_OUT.format(t1.id), json={"agent": "opus"}, headers=lead)
    assert handed.status_code == 200, handed.text

    history = await app.get(f"{TASKS}/{t1.id}/transitions", headers=auth_headers)
    (move,) = history.json()["transitions"]
    assert (move["from_status"], move["to_status"]) == ("pending", "assigned")
    assert move["actor_agent"] == "architect"
    assert "to opus" in move["note"] and "named builder is dev" in move["note"]
    (task,) = await _rows(Task, Task.id == t1.id)
    assert task.assignee == "opus"


@pytest.mark.asyncio
async def test_a_lead_hands_a_check_only_to_the_checker(app, auth_headers, bind_runner):
    """The lead may not hand t1's check to anyone but its checker qa; a task's own builder is
    taken even outside the build-wide builders."""
    await _roster(app, auth_headers, bind_runner, "architect", "dev", "opus", "qa")
    await _approved(
        app, auth_headers, _document([{"key": "t1", "builder": "opus", "checker": "qa"}])
    )
    await _build(
        app, auth_headers, driver="lead", lead="architect", level="reviewed", builders=["dev"]
    )
    t1 = (await _tasks())["t1"]
    lead = await _run_headers("run-architect-lead", "architect")

    with _scheduling():
        built = await app.post(HAND_OUT.format(t1.id), json={"agent": "opus"}, headers=lead)
    assert built.status_code == 200, built.text
    await _work(t1.id, "opus")

    wrong = await app.post(
        HAND_OUT.format(t1.id), json={"agent": "dev", "review": True}, headers=lead
    )
    assert wrong.status_code == 409, wrong.text
    assert "checker qa" in wrong.text
    assert await _rows(InboundQueueEntry, InboundQueueEntry.review_task_id == t1.id) == []
