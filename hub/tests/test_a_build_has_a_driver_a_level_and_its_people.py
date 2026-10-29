"""`a-build-has-a-driver-a-level-and-its-people`: a build records how a spec is built, and by whom.

The acceptance drive of slice D of the roadmap "Flows that do not stall". Every test drives the real
routes and the real firing decision. On master 5e8d23c each fails for the reason the slice exists:
the Build action takes no driver, level, people, cap, window or landing and records no build; a
spec task cannot name its builder; a flow hands fresh work and reviews to whichever agent is free
(the night of 2026-10-26/27, when T3 went to the free Architect); and approved work always lands.

Named by acceptance criterion: `-k recorded`, `-k level`, `-k builder`, `-k staffs`, `-k hand`,
`-k lands`.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    EvidenceFootprint,
    InboundQueueEntry,
    Loop,
    RequirementEvidence,
    Run,
    SpecDocument,
    SpecRequirement,
    Task,
    TaskIntegration,
    TaskRequirementLink,
)
from hub.scheduler import decide_firing
from hub.spec_payload import SCHEMA_VERSION
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

from .test_review_turn import _roster

P = "proj-test"
BASE = f"/api/v1/projects/{P}/project"
TASKS = f"/api/v1/projects/{P}/tasks"
AGENT_DOCS = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/a-build-of-its-own/spec.json"

FLOW = {"mode": "flow", "agent": "dev", "stop_when_queue_empties": True, "cron": "*/10 * * * *"}

#: What the operator chooses when they press Build, for the staffing drive (T3, 2026-10-27).
STAFFED = {"driver": "flow", "level": "gated", "builders": ["dev"], "reviewers": ["qa"]}


@pytest.fixture
async def author_headers():
    token = "aw_run_build-author-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-build-author",
                project_id=P,
                agent="author",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


def _document(tasks=None, **overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "A build of its own",
        "problem": "Nobody chooses how a spec is built.",
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
        "requirements": [
            {"key": "alpha", "statement": "It does alpha", "modal": "MUST"},
            {"key": "beta", "statement": "It does beta", "modal": "MUST"},
        ],
        "acceptance_criteria": [
            {
                "key": f"c-{key}",
                "requirement": key,
                "given": "g",
                "when": "w",
                "then": "t",
                "how_to_check": "pytest",
                "checked_by": "agent",
            }
            for key in ("alpha", "beta")
        ],
        "tasks": tasks
        or [
            {"key": "t1", "description": "Build alpha", "requirements": ["alpha"]},
            {"key": "t2", "description": "Build beta", "requirements": ["beta"]},
        ],
        "delivery": FLOW,
    }
    payload.update(overrides)
    return payload


async def _approved(app, auth_headers, author_headers, document):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "A build"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        AGENT_DOCS, json={"path": PATH, "document": document}, headers=author_headers
    )
    assert saved.status_code == 200, saved.text
    version = (await _read(app, auth_headers))["content_version"]
    approved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={"reason": "", "approve_anyway": True, "content_version": version},
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text


async def _read(app, auth_headers):
    read = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    assert read.status_code == 200, read.text
    return read.json()


async def _build(app, auth_headers, **settings):
    return await app.post(
        f"{BASE}/documents/build", params={"path": PATH}, json=settings, headers=auth_headers
    )


async def _rows(model, *where):
    async with async_session_factory() as db:
        return (await db.execute(select(model).where(*where))).scalars().all()


async def _tasks_by_key():
    (document,) = await _rows(SpecDocument, SpecDocument.path == PATH)
    return {t.spec_task_key: t for t in await _rows(Task, Task.spec_document_id == document.id)}


async def _decide():
    (loop,) = await _rows(Loop)
    (job,) = await _rows(AIJob, AIJob.id == loop.job_id)
    async with async_session_factory() as db:
        fresh = await db.get(Loop, loop.id)
        return await decide_firing(db, fresh, default_agent=job.agent)


async def _move(task_id, status, agent, run_id=None):
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        await apply_transition(db, task, status, run_actor(run_id or f"run-{agent}-x", agent))
        await db.commit()
    # An approval lands through the queue once it commits (`approved-work-merges-in-batches`).
    from hub import landing_queue

    await landing_queue.settle("proj-test")


# ---------------------------------------------------------------------------------------------
# build-recorded (start-a-build)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_build_is_recorded_and_a_second_is_refused(app, auth_headers, author_headers):
    """The build reads back with exactly the settings chosen; a second start is refused 409, naming
    the running build. On master Build takes none of these settings (422) and records no build."""
    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
    settings = {
        "driver": "flow",
        "level": "gated",
        "builders": ["dev"],
        "reviewers": ["qa"],
        "budget_cap_usd": 5,
        "window_end": tomorrow.isoformat(),
        "landing": "main",
    }

    first = await _build(app, auth_headers, **settings)

    assert first.status_code == 200, first.text
    builds = (await _read(app, auth_headers))["builds"]
    assert len(builds) == 1, builds
    (build,) = builds
    assert build["state"] == "running"
    assert {k: build[k] for k in ("driver", "level", "builders", "reviewers", "landing")} == {
        "driver": "flow",
        "level": "gated",
        "builders": ["dev"],
        "reviewers": ["qa"],
        "landing": "main",
    }
    assert build["budget_cap_usd"] == 5
    assert datetime.fromisoformat(build["window_end"]) == tomorrow
    assert first.json()["build_outcome"]["build"]["id"] == build["id"]

    second = await _build(app, auth_headers, **settings)

    assert second.status_code == 409, second.text
    assert second.json()["detail"]["code"] == "build_running"
    assert build["id"] in second.json()["detail"]["message"]
    assert len((await _read(app, auth_headers))["builds"]) == 1


async def _roster_rows(*names):
    from hub.db.models import Agent

    async with async_session_factory() as db:
        for name in names:
            db.add(Agent(id=f"agt-{name}", project_id=P, name=name, lifecycle="open"))
        await db.commit()


# ---------------------------------------------------------------------------------------------
# level-on-task-and-transition (task-records-its-level)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_build_task_records_its_level_and_an_outside_task_none(
    app, auth_headers, author_headers
):
    """A Fast build's task reads its build and level, and each of its moves records fast; a task
    created outside any build reads neither and is approved as on master."""
    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    built = await _build(app, auth_headers, driver="hand", level="fast")
    assert built.status_code == 200, built.text
    build_id = built.json()["build_outcome"]["build"]["id"]
    t1 = (await _tasks_by_key())["t1"]
    outside = await app.post(
        TASKS, json={"title": "Outside any build", "description": "x"}, headers=auth_headers
    )
    assert outside.status_code in (200, 201), outside.text
    outside_id = outside.json()["id"]

    for task_id in (t1.id, outside_id):
        await _move(task_id, "in_progress", "dev", run_id=f"run-dev-{task_id}")
        await _move(task_id, "completed", "dev", run_id=f"run-dev-{task_id}")
        await _move(task_id, "under_review", "qa", run_id=f"run-qa-{task_id}")
        await _move(task_id, "approved", "qa", run_id=f"run-qa-{task_id}")

    read = (await app.get(f"{TASKS}/{t1.id}", headers=auth_headers)).json()
    assert (read["build_id"], read["level"], read["status"]) == (build_id, "fast", "approved")
    moves = (await app.get(f"{TASKS}/{t1.id}/transitions", headers=auth_headers)).json()
    assert moves["transitions"] and {m["level"] for m in moves["transitions"]} == {"fast"}

    other = (await app.get(f"{TASKS}/{outside_id}", headers=auth_headers)).json()
    assert (other["build_id"], other["level"], other["status"]) == (None, None, "approved")
    moves = (await app.get(f"{TASKS}/{outside_id}/transitions", headers=auth_headers)).json()
    assert {m["level"] for m in moves["transitions"]} == {None}


# ---------------------------------------------------------------------------------------------
# builder-assigned-at-start (a-task-names-its-builder)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_declared_builder_is_assigned_when_the_build_starts(
    app, auth_headers, author_headers
):
    """t1 declares dev (an open agent) and t2 ghost (no agent): at a hand-driven start t1 is dev's,
    t2 is nobody's and keeps ghost, and the response names ghost as unresolved; no run starts. On
    master a task cannot declare a builder: the document is refused when saved."""
    await _roster_rows("dev", "qa")
    tasks = [
        {"key": "t1", "description": "Build alpha", "requirements": ["alpha"], "builder": "dev"},
        {"key": "t2", "description": "Build beta", "requirements": ["beta"], "builder": "ghost"},
    ]
    await _approved(app, auth_headers, author_headers, _document(tasks=tasks))
    assert {t.assignee for t in (await _tasks_by_key()).values()} == {None}, "approval assigns"

    built = await _build(app, auth_headers, driver="hand")

    assert built.status_code == 200, built.text
    by_key = await _tasks_by_key()
    assert (by_key["t1"].assignee, by_key["t1"].builder) == ("dev", "dev")
    assert (by_key["t2"].assignee, by_key["t2"].builder) == (None, "ghost")
    unresolved = built.json()["build_outcome"]["build"]["unresolved_builders"]
    assert unresolved == [{"task": "t2", "builder": "ghost"}]
    assert await _rows(Run, Run.agent != "author") == []


# ---------------------------------------------------------------------------------------------
# flow-staffs-only-builders (the-flow-staffs-the-builds-people) -- the night's T3
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_flow_staffs_only_the_builds_people(
    app, auth_headers, author_headers, bind_runner, monkeypatch
):
    """A flow-driven Gated build with builders [dev] and reviewers [qa], and a free architect with a
    runner. With dev busy the task waits (architect is never selected); with dev free it goes to
    dev; once dev completes it, its review goes to qa. On master the same document's flow hands the
    task to the free architect (T3, 2026-10-27)."""
    from hub import task_integration
    from hub.requirement_evidence import ReviewTarget

    async def _reviewable(session, task, root=None):
        return ReviewTarget(commit_sha="a" * 40, branch=f"agentweave/task/{task.id}")

    monkeypatch.setattr(task_integration, "review_target", _reviewable)
    await _roster(app, auth_headers, bind_runner, "architect", "dev", "qa")
    await _approved(
        app,
        auth_headers,
        author_headers,
        _document(tasks=[{"key": "t1", "description": "Build alpha", "requirements": ["alpha"]}]),
    )
    built = await _build(app, auth_headers, **STAFFED)
    assert built.status_code == 200, built.text
    t1 = (await _tasks_by_key())["t1"]
    async with async_session_factory() as db:
        db.add(Run(id="run-dev-busy", project_id=P, agent="dev", status="running"))
        await db.commit()

    busy = await _decide()

    assert "architect" not in {s.agent for s in busy.selections}, busy
    assert busy.selections == ()

    async with async_session_factory() as db:
        (await db.get(Run, "run-dev-busy")).status = "completed"
        await db.commit()
    free = await _decide()

    assert [(s.task.id, s.agent, s.is_review) for s in free.selections] == [(t1.id, "dev", False)]

    await _move(t1.id, "in_progress", "dev", run_id="run-dev-t1")
    await _move(t1.id, "completed", "dev", run_id="run-dev-t1")
    review = await _decide()

    assert [(s.task.id, s.agent, s.is_review) for s in review.selections] == [(t1.id, "qa", True)]


# ---------------------------------------------------------------------------------------------
# hand-starts-nothing (a-lead-hands-out-the-work)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_hand_driven_build_starts_nothing(app, auth_headers, author_headers):
    """The delivery recommends a flow, the operator builds it by hand: no loop, no run and no
    queued entry, and the build is recorded as hand-driven. On master the build takes no driver."""
    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())

    built = await _build(app, auth_headers, driver="hand", builders=["dev"])

    assert built.status_code == 200, built.text
    assert await _rows(Loop) == [] and await _rows(AIJob) == []
    assert await _rows(Run, Run.agent != "author") == []
    assert await _rows(InboundQueueEntry) == []
    (build,) = (await _read(app, auth_headers))["builds"]
    assert (build["driver"], build["state"]) == ("hand", "running")


# ---------------------------------------------------------------------------------------------
# lands-nowhere (landing)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_build_that_lands_nowhere_merges_nothing(
    app, auth_headers, author_headers, bind_project_workspace, tmp_path
):
    """A task of a build landing nowhere, approvable in a git fixture with main set, is approved;
    main's tip does not move, and its integration record is skipped saying the build lands nowhere.
    On master the build takes no landing and approval merges the work into main."""
    from hub import worktrees

    from .test_task_integration import commit_on_branch, git, make_repo, set_main_branch

    make_repo(tmp_path)
    await set_main_branch("main")
    await bind_project_workspace(tmp_path)
    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    built = await _build(app, auth_headers, driver="hand", level="reviewed", landing="nowhere")
    assert built.status_code == 200, built.text
    t1 = (await _tasks_by_key())["t1"]
    tip = commit_on_branch(tmp_path, worktrees.task_branch_name(t1.id), "alpha.py", "a = 1\n")
    git(tmp_path, "checkout", "-q", "main")
    main_before = git(tmp_path, "rev-parse", "main").stdout.strip()
    await _evidence_naming(t1.id, tip)

    await _move(t1.id, "in_progress", "dev", run_id="run-dev-lands")
    await _move(t1.id, "completed", "dev", run_id="run-dev-lands")
    await _move(t1.id, "under_review", "qa", run_id="run-qa-lands")
    await _move(t1.id, "approved", "qa", run_id="run-qa-lands")

    (task,) = await _rows(Task, Task.id == t1.id)
    assert task.status == "approved"
    assert git(tmp_path, "rev-parse", "main").stdout.strip() == main_before
    (record,) = await _rows(TaskIntegration, TaskIntegration.task_id == t1.id)
    assert record.outcome == "skipped"
    assert "lands nowhere" in (record.reason or "")


# ---------------------------------------------------------------------------------------------
# A finished build ends its loop; deleting a document takes its builds; a racing Build is a 409
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("driver", ["flow", "lead"])
async def test_a_finished_build_ends_its_loop(app, auth_headers, author_headers, driver):
    """Every task of a Fast build approved, then two firings: the build reads finished and its loop
    has ended (completed, its job disabled), for a flow and for a lead. Before the review fix the
    build's firing returned before the loop's own stop check, and the loop ticked forever."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from hub.db.models import Build
    from hub.scheduler import JobScheduler
    from hub.task_transitions import operator

    await _roster_rows("dev", "qa", "lead")
    await _approved(app, auth_headers, author_headers, _document())
    settings = {"driver": driver, "level": "fast", "builders": ["dev"]}
    if driver == "lead":
        settings["lead"] = "lead"
    scheduling = patch(
        "hub.turn_scheduler.schedule_agent",
        AsyncMock(return_value=MagicMock(waiting_reason=None, terminal_failure=False)),
    )
    with scheduling:
        built = await _build(app, auth_headers, **settings)
    assert built.status_code == 200, built.text
    for task in (await _tasks_by_key()).values():
        async with async_session_factory() as db:
            row = await db.get(Task, task.id)
            for status in ("in_progress", "completed", "approved"):
                await apply_transition(db, row, status, operator())
            await db.commit()

    (loop,) = await _rows(Loop)
    for _ in range(2):
        with scheduling:
            async with async_session_factory() as db:
                job = await db.get(AIJob, loop.job_id)
                await JobScheduler()._do_fire_job(job, "scheduled", db)

    (build,) = await _rows(Build)
    (loop,) = await _rows(Loop)
    (job,) = await _rows(AIJob)
    assert build.state == "finished"
    assert (loop.ending_state, loop.stopped_at is not None, job.enabled) == (
        "completed",
        True,
        False,
    )


@pytest.mark.asyncio
async def test_deleting_a_document_deletes_its_builds(app, auth_headers, author_headers):
    from hub.db.models import Build

    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    assert (await _build(app, auth_headers, driver="hand")).status_code == 200
    assert len(await _rows(Build)) == 1

    deleted = await app.delete(f"{BASE}/documents/{PATH}", headers=auth_headers)

    assert deleted.status_code == 200, deleted.text
    assert await _rows(Build) == []


@pytest.mark.asyncio
async def test_two_racing_builds_answer_409_not_500(app, auth_headers, author_headers, monkeypatch):
    """Two Build requests that both pass the running-build check: the second meets the partial
    unique index and is answered 409 build_running, as the check would have answered it."""
    from hub.api.v1 import spec as spec_api

    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    assert (await _build(app, auth_headers, driver="hand")).status_code == 200

    async def missed(*args, **kwargs):
        return None

    monkeypatch.setattr(spec_api, "_refuse_a_second_build", missed)
    second = await _build(app, auth_headers, driver="hand")

    assert second.status_code == 409, second.text
    assert second.json()["detail"]["code"] == "build_running"


async def _evidence_naming(task_id, commit):
    """Evidence for the task's requirement naming *commit*: what approval would merge."""
    async with async_session_factory() as db:
        (link,) = (
            (
                await db.execute(
                    select(TaskRequirementLink).where(TaskRequirementLink.task_id == task_id)
                )
            )
            .scalars()
            .all()
        )
        requirement = await db.get(SpecRequirement, link.requirement_id)
        db.add(
            RequirementEvidence(
                id=f"ev-lands-{task_id}",
                project_id=P,
                requirement_id=requirement.id,
                task_id=task_id,
                digest=requirement.digest,
                kind="artifact_diff",
                actor_kind="agent",
                actor="dev",
                summary="alpha is built",
                review_state="awaiting",
            )
        )
        db.add(
            EvidenceFootprint(
                id=f"fp-lands-{task_id}",
                project_id=P,
                evidence_id=f"ev-lands-{task_id}",
                kind="git",
                commit_sha=commit,
                branch=f"agentweave/task/{task_id}",
            )
        )
        await db.commit()


# ---------------------------------------------------------------------------------------------
# Fast: an allowed approval accepts the builder's awaiting evidence (slice D drive, B1)
# ---------------------------------------------------------------------------------------------


async def _evidence_row(task_id):
    (row,) = await _rows(RequirementEvidence, RequirementEvidence.task_id == task_id)
    return row


async def _complete_with_evidence(task_id):
    await _evidence_naming(task_id, "4b5ac3a5b3db" + "0" * 28)
    await _move(task_id, "in_progress", "dev", run_id="run-dev-b1")
    await _move(task_id, "completed", "dev", run_id="run-dev-b1")


@pytest.mark.asyncio
async def test_at_fast_the_builders_own_approval_accepts_its_evidence(
    app, auth_headers, author_headers
):
    """B1(a): the builder completes (evidence awaiting) and approves its own task at Fast. On the
    unfixed code the gate refused 409 "nobody has judged it", because a builder never accepts its
    own evidence and Fast has no reviewer."""
    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    built = await _build(app, auth_headers, driver="hand", level="fast", builders=["dev"])
    assert built.status_code == 200, built.text
    t1 = (await _tasks_by_key())["t1"]
    await _complete_with_evidence(t1.id)
    assert (await _evidence_row(t1.id)).review_state == "awaiting"

    await _move(t1.id, "approved", "dev", run_id="run-dev-b1")

    (task,) = await _rows(Task, Task.id == t1.id)
    assert task.status == "approved"
    assert (await _evidence_row(t1.id)).review_state == "accepted"


@pytest.mark.asyncio
async def test_at_reviewed_the_builders_own_approval_is_still_refused(
    app, auth_headers, author_headers
):
    """The level guard: a Reviewed build's builder approving completed work is refused, its
    evidence untouched."""
    from hub.task_transition_service import TransitionRefusedError

    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    built = await _build(app, auth_headers, driver="hand", level="reviewed", builders=["dev"])
    assert built.status_code == 200, built.text
    t1 = (await _tasks_by_key())["t1"]
    await _complete_with_evidence(t1.id)

    with pytest.raises(TransitionRefusedError):
        await _move(t1.id, "approved", "dev", run_id="run-dev-b1")

    (task,) = await _rows(Task, Task.id == t1.id)
    assert task.status == "completed"
    assert (await _evidence_row(t1.id)).review_state == "awaiting"


@pytest.mark.asyncio
async def test_a_flow_driven_fast_build_is_approved_by_the_flow_with_its_evidence_accepted(
    app, auth_headers, author_headers
):
    """B1(b): a flow-driven Fast build's completed task, with no checks to wait for, is approved by
    the flow's firing (origin job), and its awaiting evidence is accepted by that approval."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from hub.scheduler import JobScheduler

    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    scheduling = patch(
        "hub.turn_scheduler.schedule_agent",
        AsyncMock(return_value=MagicMock(waiting_reason=None, terminal_failure=False)),
    )
    with scheduling:
        built = await _build(app, auth_headers, driver="flow", level="fast", builders=["dev"])
    assert built.status_code == 200, built.text
    t1 = (await _tasks_by_key())["t1"]
    await _complete_with_evidence(t1.id)

    (loop,) = await _rows(Loop)
    with scheduling:
        async with async_session_factory() as db:
            job = await db.get(AIJob, loop.job_id)
            await JobScheduler()._do_fire_job(job, "scheduled", db)

    (task,) = await _rows(Task, Task.id == t1.id)
    assert task.status == "approved"
    assert (await _evidence_row(t1.id)).review_state == "accepted"
