"""A review turn is told about the evidence gate beside the verdict it can refuse (F357).

Both review channels told the reviewer to end with `approved` or `revision_needed`, and neither said
that `approval-refuses-unaccepted-evidence` refuses `approved` while the task's evidence is still
awaiting a decision. Measured on LoopEngine, 2026-09-14: seven refused approvals, and reviewers told
their peers the task was approved regardless.

Each channel is asserted against the shape the gate actually reads -- a real commit, evidence
naming it, nobody has judged it -- built by the gate's own test fixture rather than by hand.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.api.v1.agents import _render_hub_agent_context
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AIJob, Loop, Run, Task
from hub.review_turn import ReviewContext, verdict_evidence_sentence
from hub.scheduler import _compose_loop_briefing

from .test_approval_refuses_unaccepted_evidence import a_task_with_awaiting_evidence, accept
from .test_task_integration import make_document, make_repo, set_main_branch

PROJECT = "proj-test"
GATE = "This task's evidence is still waiting for a decision"


@pytest.fixture
async def builder():
    """The author whose evidence is awaiting. Declared here, not imported: an imported fixture
    shadows itself in every signature that takes it (see the sibling file's own note)."""
    async with async_session_factory() as session:
        session.add(Agent(id="ag-f357-builder", project_id=PROJECT, name="builder"))
        session.add(
            Run(
                id="run-f357-builder",
                project_id=PROJECT,
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_f357-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_f357-secret"}


async def _reviewer(name, *, granted):
    async with async_session_factory() as session:
        session.add(
            Agent(
                id=f"ag-{name}",
                project_id=PROJECT,
                name=name,
                can_accept_evidence=granted,
            )
        )
        await session.commit()


async def _flow(task_id):
    """A flow (a loop that declares a document), so the review arm of the briefing is reached."""
    async with async_session_factory() as session:
        session.add(
            AIJob(
                id="job-f357",
                project_id=PROJECT,
                name="F357 flow",
                agent="builder",
                message="work the queue",
                cron="*/5 * * * *",
                session_mode="new",
                enabled=False,
            )
        )
        await session.flush()
        document_id = (await session.get(Task, task_id)).spec_document_id
        session.add(
            Loop(
                id="loop-f357",
                project_id=PROJECT,
                job_id="job-f357",
                purpose="build what the document declared",
                spec_document_id=document_id or "doc-f357",
            )
        )
        await session.commit()


async def _review_briefing(task_id, agent):
    async with async_session_factory() as session:
        loop = (await session.execute(select(Loop).where(Loop.id == "loop-f357"))).scalar_one()
        task = await session.get(Task, task_id)
        return await _compose_loop_briefing(session, loop, task, None, is_review=True, agent=agent)


async def _review_context(task_id, agent, workspace):
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        agent_row = (
            await session.execute(
                select(Agent).where(Agent.project_id == PROJECT, Agent.name == agent)
            )
        ).scalar_one()
        rendered = await _render_hub_agent_context(
            agent=agent,
            project_id=PROJECT,
            db=session,
            session_data=None,
            agent_row=agent_row,
            work_dir=str(workspace),
            review=ReviewContext(
                task_id=task.id,
                task_title=task.title,
                reviewer=agent,
                commit_sha="0" * 40,
                evidence_id="ev-f357",
                workspace=workspace,
            ),
        )
    return rendered["context"]


async def _gated_task(app, auth_headers, builder, tmp_path):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    task, evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    await _flow(task)
    return task, evidence


@pytest.mark.asyncio
async def test_an_ungranted_reviewer_is_told_the_approval_can_be_refused_and_what_then(
    app, auth_headers, builder, tmp_path
):
    """The LoopEngine shape: the reviewer holds no grant, and the evidence is awaiting."""
    task, _evidence = await _gated_task(app, auth_headers, builder, tmp_path)
    await _reviewer("checker", granted=False)

    briefing = await _review_briefing(task, "checker")
    context = await _review_context(task, "checker", tmp_path)

    for rendered in (briefing, context):
        assert GATE in rendered
        assert "`FR-1`" in rendered
        assert "Deciding evidence is the operator's, not yours" in rendered
        assert "do not tell anyone the task is approved" in rendered
        assert "You can decide evidence: if the work is right" not in rendered


@pytest.mark.asyncio
async def test_a_granted_reviewer_is_told_to_decide_the_evidence_before_approving(
    app, auth_headers, builder, tmp_path
):
    task, _evidence = await _gated_task(app, auth_headers, builder, tmp_path)
    await _reviewer("tester", granted=True)

    briefing = await _review_briefing(task, "tester")
    context = await _review_context(task, "tester", tmp_path)

    for rendered in (briefing, context):
        assert GATE in rendered
        assert "`decide_evidence` first" in rendered
        assert "Deciding evidence is the operator's, not yours" not in rendered


@pytest.mark.asyncio
async def test_both_channels_carry_the_same_sentence(app, auth_headers, builder, tmp_path):
    """The two channels are one helper's output, so they cannot disagree (the F45 pairing)."""
    task, _evidence = await _gated_task(app, auth_headers, builder, tmp_path)
    await _reviewer("checker", granted=False)

    async with async_session_factory() as session:
        sentence = await verdict_evidence_sentence(
            session, await session.get(Task, task), may_decide=False
        )
    assert sentence is not None
    assert sentence in await _review_briefing(task, "checker")
    assert sentence in await _review_context(task, "checker", tmp_path)


@pytest.mark.asyncio
async def test_nothing_is_said_once_the_evidence_is_decided(app, auth_headers, builder, tmp_path):
    """Keyed on what is waiting now: accepted evidence clears the gate, so the sentence goes."""
    task, evidence = await _gated_task(app, auth_headers, builder, tmp_path)
    await _reviewer("checker", granted=False)
    await accept(app, auth_headers, evidence)

    assert GATE not in await _review_briefing(task, "checker")
    assert GATE not in await _review_context(task, "checker", tmp_path)
