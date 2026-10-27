"""Fast, Reviewed and Gated in the mover decision and the gate (`a-build-has-a-driver-a-level-and-its-
people`, task `levels`).

Red first, on the build record alone (task `build-record`): there a task records its level and
nothing reads it, so a Fast builder is refused from `completed` (no `completed -> approved` edge),
a flow stages a review of a Fast task, close-as-built leaves its tasks waiting on a review, and the
evidence gate reads only the document's rigor.

Named by acceptance criterion: `-k fast`, `-k flow_fast`, `-k already_built`, `-k reviewed`,
`-k gated`, `-k checks`.
"""

import itertools
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from hub import builds, project_checks
from hub.agent_auth import hash_run_token
from hub.api.v1.tasks import update_task_for_actor
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AIJob,
    Build,
    InboundQueueEntry,
    Loop,
    RequirementEvidence,
    Run,
    SpecDocument,
    Task,
    TaskTransition,
)
from hub.scheduler import JobScheduler
from hub.schemas.tasks import TaskUpdate
from hub.spec_payload import SCHEMA_VERSION
from hub.task_transition_service import TransitionRefusedError, apply_transition
from hub.task_transitions import run_actor

from .test_project_checks_run import FAIL, PASS, _project, _task_with_work
from .test_task_integration import commits_on

P = "proj-test"
BASE = f"/api/v1/projects/{P}/project"
TASKS = f"/api/v1/projects/{P}/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/levels-demo/spec.json"
_ids = itertools.count(1)


async def _build_row(level, *, driver="hand", lead=None, loop_id=None, document_id="doc-levels"):
    build_id = f"build-lv-{next(_ids)}"
    async with async_session_factory() as db:
        db.add(
            Build(
                id=build_id,
                project_id=P,
                document_id=document_id,
                state="running",
                driver=driver,
                level=level,
                builders=["dev"],
                reviewers=[],
                lead=lead,
                landing="main",
                loop_id=loop_id,
            )
        )
        await db.commit()
    return build_id


async def _in_build(task_id, build_id, level):
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        task.build_id, task.level = build_id, level
        await db.commit()


async def _completed_by(task_id, agent):
    """Worked and completed by *agent*'s run, so it is on the record as the builder."""
    run_id = f"run-{agent}-{next(_ids)}"
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        if task.status != "in_progress":
            await apply_transition(db, task, "in_progress", run_actor(run_id, agent))
        await apply_transition(db, task, "completed", run_actor(run_id, agent))
        await db.commit()


async def _plain_task(status="pending"):
    task_id = f"task-lv-{next(_ids)}"
    async with async_session_factory() as db:
        db.add(Task(id=task_id, project_id=P, title=task_id, status=status))
        await db.commit()
    return task_id


async def _update(task_id, status, agent):
    """The agent route's own entry point. Returns `(refusal, response)`."""
    async with async_session_factory() as db:
        try:
            response = await update_task_for_actor(
                task_id,
                TaskUpdate(status=status),
                project_id=P,
                actor=run_actor(f"run-act-{next(_ids)}", agent),
                session=db,
            )
        except (HTTPException, TransitionRefusedError) as refusal:
            return refusal, None
    return None, response


def _said(refusal) -> str:
    return str(refusal.detail if isinstance(refusal, HTTPException) else refusal)


async def _transitions(task_id):
    async with async_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(TaskTransition)
                    .where(TaskTransition.task_id == task_id)
                    .order_by(TaskTransition.sequence)
                )
            ).scalars()
        )


async def _review_entries(task_id):
    async with async_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.review_task_id == task_id)
                )
            ).scalars()
        )


# ---------------------------------------------------------------------------------------------
# fast-builder-approves (fast-approves-without-a-reviewer)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fast_builder_approves_from_completed_and_gated_refuses_naming_the_level(app):
    fast_build = await _build_row("fast")
    gated_build = await _build_row("gated", document_id="doc-levels-2")
    fast_task, gated_task = await _plain_task(), await _plain_task()
    await _in_build(fast_task, fast_build, "fast")
    await _in_build(gated_task, gated_build, "gated")
    await _completed_by(fast_task, "dev")
    await _completed_by(gated_task, "dev")

    refusal, response = await _update(fast_task, "approved", "dev")

    assert refusal is None, _said(refusal)
    assert response.status == "approved"
    last = (await _transitions(fast_task))[-1]
    assert (last.from_status, last.to_status, last.level) == ("completed", "approved", "fast")
    assert last.actor_agent == "dev"
    assert await _review_entries(fast_task) == []

    refusal, _ = await _update(gated_task, "approved", "dev")
    assert refusal is not None
    assert "gated" in _said(refusal)


@pytest.mark.asyncio
async def test_fast_lead_approves_and_another_agent_does_not(app):
    build_id = await _build_row("fast", lead="lead")
    led, other = await _plain_task(), await _plain_task()
    for task_id in (led, other):
        await _in_build(task_id, build_id, "fast")
        await _completed_by(task_id, "dev")

    refusal, _ = await _update(other, "approved", "qa")
    assert refusal is not None and "at Fast only" in _said(refusal)
    refusal, response = await _update(led, "approved", "lead")
    assert refusal is None, _said(refusal)
    assert response.status == "approved"


# ---------------------------------------------------------------------------------------------
# fast-flow-approves-after-checks
# ---------------------------------------------------------------------------------------------


def _scheduling():
    return patch(
        "hub.turn_scheduler.schedule_agent",
        AsyncMock(return_value=MagicMock(waiting_reason=None, terminal_failure=False)),
    )


async def _tick(job_id):
    async with async_session_factory() as db:
        job = await db.get(AIJob, job_id)
        return await JobScheduler()._do_fire_job(job, "scheduled", db)


async def _a_flow_fast_task(tmp_path, level="fast"):
    """`_task_with_work`'s task, made a flow's (its loop declares a document) in a build at
    *level*, completed by its builder."""
    task_id, work = await _task_with_work(tmp_path, status="in_progress")
    async with async_session_factory() as db:
        db.add(
            SpecDocument(
                id="doc-flow-fast",
                project_id=P,
                path="spec/changes/flow-fast/spec.json",
                title="Flow fast",
                phase="approved",
                kind="change-spec",
            )
        )
        (await db.get(Loop, "loop-checks")).spec_document_id = "doc-flow-fast"
        (await db.get(AIJob, "job-checks")).enabled = True
        await db.commit()
    build_id = await _build_row(
        level, driver="flow", loop_id="loop-checks", document_id="doc-flow-fast"
    )
    await _in_build(task_id, build_id, level)
    await _completed_by(task_id, "builder")
    return task_id, work


@pytest.mark.asyncio
async def test_flow_fast_approves_once_the_check_run_passes(app, tmp_path):
    task_id, work = await _a_flow_fast_task(tmp_path)
    await _project([PASS])

    with _scheduling():
        await _tick("job-checks")  # the checks are undecided: the firing asks for a run
    await project_checks.drain()
    async with async_session_factory() as db:
        assert (await db.get(Task, task_id)).status == "completed"
    with _scheduling():
        await _tick("job-checks")

    async with async_session_factory() as db:
        assert (await db.get(Task, task_id)).status == "approved"
    last = (await _transitions(task_id))[-1]
    assert (last.to_status, last.origin, last.job_id, last.level) == (
        "approved",
        "job",
        "job-checks",
        "fast",
    )
    assert await _review_entries(task_id) == []
    assert work in commits_on(tmp_path, "main")


# ---------------------------------------------------------------------------------------------
# red-checks-at-fast (checks-hold-at-every-level)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checks_hold_at_fast_for_the_builder_and_the_flow(app, tmp_path):
    task_id, work = await _a_flow_fast_task(tmp_path)
    await _project([FAIL])
    async with async_session_factory() as db:  # decided under review, as the gate tests do
        task = await db.get(Task, task_id)
        task.status = "under_review"
        await db.commit()
    await project_checks.request_run(P, task_id)
    await project_checks.drain()
    async with async_session_factory() as db:
        (await db.get(Task, task_id)).status = "completed"
        await db.commit()

    refusal, _ = await _update(task_id, "approved", "builder")
    assert refusal is not None
    assert "boom: 2 != 3" in _said(refusal) or "checks" in _said(refusal)
    with _scheduling():
        await _tick("job-checks")

    async with async_session_factory() as db:
        assert (await db.get(Task, task_id)).status != "approved"
    assert work not in commits_on(tmp_path, "main")
    assert builds.allows_automatic_override("fast") is True
    assert builds.allows_automatic_override("reviewed") is True
    assert builds.allows_automatic_override("gated") is False


# ---------------------------------------------------------------------------------------------
# fast-close-as-built
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_already_built_at_fast_approves_at_once(app, auth_headers, tmp_path):
    from .test_close_spec_tasks_already_built import KEYS, _approved_document
    from .test_task_integration import commit_on_branch, git, make_repo, set_main_branch

    make_repo(tmp_path)
    work = commit_on_branch(tmp_path, "feature", "built.py", "x = 1\n")
    git(tmp_path, "checkout", "-q", "main")
    git(tmp_path, "merge", "-q", "--ff-only", "feature")
    await set_main_branch("main")
    headers = await _author()
    await _approved_document(app, auth_headers, headers)

    closed = await app.post(
        f"{BASE}/documents/spec/changes/built-already/spec.json/close-already-built",
        json={"commits": [work], "level": "fast"},
        headers=auth_headers,
    )

    assert closed.status_code == 200, closed.text
    async with async_session_factory() as db:
        tasks = list((await db.execute(select(Task))).scalars())
    assert len(tasks) == len(KEYS)
    assert {t.status for t in tasks} == {"approved"}
    approvals = [
        row for task in tasks for row in await _transitions(task.id) if row.to_status == "approved"
    ]
    assert len(approvals) == len(KEYS)
    assert all(work[:12] in (row.note or "") for row in approvals)
    assert all("already built" in (row.note or "") for row in approvals)
    async with async_session_factory() as db:
        pieces = list((await db.execute(select(RequirementEvidence))).scalars())
    assert len(pieces) == len(KEYS)
    assert {(piece.kind, piece.review_state) for piece in pieces} == {("already_built", "accepted")}


async def _author():
    async with async_session_factory() as db:
        db.add(
            Run(
                id="run-author",
                project_id=P,
                agent="Architect",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_author-secret"),
            )
        )
        await db.commit()
    return {"Authorization": "Bearer aw_run_author-secret"}


# ---------------------------------------------------------------------------------------------
# reviewed-reports-gaps / gated-needs-evidence
# ---------------------------------------------------------------------------------------------


async def _two_requirement_task(app, auth_headers, level):
    """A task serving FR-1 and FR-2 of a sketch-rigor document, in a build at *level*, with
    accepted evidence for FR-1 only, completed by dev."""
    headers = await _author()
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Levels demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Levels demo",
                "requirements": [
                    {"key": "alpha", "statement": "It does alpha", "modal": "MUST"},
                    {"key": "beta", "statement": "It does beta", "modal": "MUST"},
                ],
            },
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    async with async_session_factory() as db:
        for name in ("dev", "qa"):
            db.add(Agent(id=f"ag-lv-{name}", project_id=P, name=name))
        document = (
            await db.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()
        assert (document.rigor or "sketch") == "sketch"
        document_id = document.id
        await db.commit()
    task = await app.post(
        TASKS, json={"title": "Both", "requirement_ids": ["FR-1", "FR-2"]}, headers=auth_headers
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["id"]
    await _evidence(app, auth_headers, "FR-1")
    build_id = await _build_row(level, document_id=document_id)
    await _in_build(task_id, build_id, level)
    await _completed_by(task_id, "dev")
    return task_id


async def _evidence(app, auth_headers, identifier):
    recorded = await app.post(
        f"{BASE}/spec/evidence",
        json={
            "identifier": identifier,
            "document": PATH,
            "kind": "manual_observation",
            "summary": f"{identifier} observed working",
        },
        headers=auth_headers,
    )
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["review_state"] == "accepted"


@pytest.mark.asyncio
async def test_reviewed_refuses_the_builder_and_reports_the_gap(app, auth_headers):
    task_id = await _two_requirement_task(app, auth_headers, "reviewed")

    refusal, _ = await _update(task_id, "approved", "dev")
    assert refusal is not None
    refusal, _ = await _update(task_id, "under_review", "qa")
    assert refusal is None, _said(refusal)
    refusal, response = await _update(task_id, "approved", "qa")

    assert refusal is None, _said(refusal)
    assert response.status == "approved"
    assert [entry["identifier"] for entry in response.approval_report] == ["FR-2"]


@pytest.mark.asyncio
async def test_gated_refuses_until_every_requirement_has_accepted_evidence(app, auth_headers):
    task_id = await _two_requirement_task(app, auth_headers, "gated")
    refusal, _ = await _update(task_id, "under_review", "qa")
    assert refusal is None, _said(refusal)

    refusal, _ = await _update(task_id, "approved", "qa")

    assert refusal is not None
    assert "FR-2" in _said(refusal)
    await _evidence(app, auth_headers, "FR-2")
    refusal, response = await _update(task_id, "approved", "qa")
    assert refusal is None, _said(refusal)
    assert response.status == "approved"


# ---------------------------------------------------------------------------------------------
# checks-hold-at-every-level: slice M's automatic override, per level
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("level", ["fast", "reviewed", "gated"])
async def test_the_hubs_override_lands_at_fast_and_reviewed_never_at_gated(app, tmp_path, level):
    """A task whose only failure is shared with a red main (slice M's drive), in a build at *level*,
    approved by a reviewer through the agent route: Fast and Reviewed land it over the failure as
    the Hub's override; Gated holds it for the operator ("fail on main too"), nothing merged."""
    from . import test_a_red_main_does_not_hold_the_night as red

    red._repo(tmp_path)
    await red._loop()
    work = await red._task(tmp_path, red.TASK, {"feature.py": "x = 1\n"})
    build_id = await _build_row(level, loop_id=red.LOOP)
    await _in_build(red.TASK, build_id, level)
    await red._configure()
    await red._checked(red.TASK)

    approved = await red._reviewer_approves(app, red.TASK)

    if level == "gated":
        assert approved.status_code == 409, approved.text
        assert "fail on main too" in approved.json()["detail"]["message"]
        assert work not in commits_on(tmp_path, "main")
    else:
        assert approved.status_code == 200, approved.text
        assert work in commits_on(tmp_path, "main")
        assert (await red._approval(red.TASK)).override_by == "hub"
