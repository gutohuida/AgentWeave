"""Review independence compares profiles, not names (`fold-duplicate-agents-into-one-profile-with-
their-history-kept`, FR-9, task independence-by-profile).

DeveloperOpus completes a task and records evidence for it, and is then folded into Developer. At
every site that keeps an agent off its own work -- the transition guards, the review dispatch, the
evidence decision, the reviewer ladder and the filing check -- Developer is refused naming its
profile, and QA, another profile, is not (folded-author-blocks-profile). With nothing folded the
same sites refuse the same name as before (same-name-still-refused).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hub import requirement_evidence
from hub.agent_profiles import widen_to_profiles
from hub.api.v1.agent_trigger import review_dispatch_refusal
from hub.builds import own_checker_refusal
from hub.db.engine import async_session_factory
from hub.db.models import Agent, RequirementEvidence, Task, TaskTransition
from hub.review_on_completion import _choose
from hub.scheduler import resolve_reviewer
from hub.spec_lifecycle import Actor
from hub.task_transition_service import authorship_reason, decide_move
from hub.task_transitions import Actor as TransitionActor

P = "proj-test"
AGENTS = f"/api/v1/projects/{P}/agents"


async def _add(*rows) -> None:
    async with async_session_factory() as db:
        for row in rows:
            db.add(row)
        await db.commit()


async def _authored(task_id: str, author: str, *, status: str = "completed", **columns) -> None:
    """A task *author* completed and recorded evidence for, held by nobody."""
    await _add(
        Task(
            id=task_id,
            project_id=P,
            readable_id=task_id.upper(),
            title=f"Task {task_id}",
            status=status,
            **columns,
        ),
        TaskTransition(
            id=f"tt-{task_id}",
            project_id=P,
            task_id=task_id,
            from_status="in_progress",
            to_status="completed",
            actor_kind="run",
            actor_agent=author,
        ),
        RequirementEvidence(
            id=f"ev-{task_id}",
            project_id=P,
            requirement_id="spreq-x",
            digest="d" * 64,
            kind="test_result",
            actor_kind="agent",
            actor=author,
            task_id=task_id,
        ),
    )


async def _grant(*names: str) -> None:
    """Grant *names* evidence acceptance, so the own-work refusal is what a decision meets: it is
    checked after the grant, where the same-name refusal always stood."""
    async with async_session_factory() as db:
        for agent in (
            await db.execute(select(Agent).where(Agent.project_id == P, Agent.name.in_(names)))
        ).scalars():
            agent.can_accept_evidence = True
        await db.commit()


async def _fold(app, headers, name: str, into: str) -> None:
    resp = await app.post(f"{AGENTS}/{name}/fold", json={"into": into}, headers=headers)
    assert resp.status_code == 200, resp.text


@pytest.fixture
async def folded(app, auth_headers, add_agent):
    """DeveloperOpus's completed, evidenced task `t-1`, then DeveloperOpus folded into Developer."""
    for name in ("Developer", "DeveloperOpus", "QA"):
        await add_agent(name)
    await _authored("t-1", "DeveloperOpus")
    await _fold(app, auth_headers, "DeveloperOpus", "Developer")
    return "t-1"


def _run_of(agent: str) -> TransitionActor:
    """A run of *agent* that the operator did not start, so it keeps the map's edges."""
    return TransitionActor(kind="run", run_id=f"run-{agent.lower()}", agent=agent)


# ------------------------------------------------------------ folded-author-blocks-profile


@pytest.mark.asyncio
async def test_the_author_rule_names_the_profile(folded):
    async with async_session_factory() as db:
        task = await db.get(Task, folded)
        reason = await authorship_reason(db, task, "Developer")
        assert reason is not None
        assert "profile 'Developer'" in reason and "'DeveloperOpus'" in reason
        assert await authorship_reason(db, task, "QA") is None


@pytest.mark.asyncio
async def test_a_run_of_the_profile_may_not_approve_or_return_it(folded):
    async with async_session_factory() as db:
        task = await db.get(Task, folded)
        task.status, task.assignee = "under_review", "QA"
        for to_status in ("approved", "revision_needed"):
            verdict = await decide_move(db, task, to_status, _run_of("Developer"))
            assert verdict.allowed is False, to_status
            assert "profile 'Developer'" in verdict.reason
        allowed = await decide_move(db, task, "approved", _run_of("QA"))
        assert allowed.allowed is True, allowed.reason


@pytest.mark.asyncio
async def test_the_profile_may_not_be_entered_as_its_reviewer(folded):
    async with async_session_factory() as db:
        task = await db.get(Task, folded)
        verdict = await decide_move(db, task, "under_review", _run_of("Developer"))
        assert verdict.allowed is False
        assert "profile 'Developer'" in verdict.reason
        taken = await decide_move(db, task, "under_review", _run_of("QA"))
        assert taken.allowed is True and taken.holder == "QA"


@pytest.mark.asyncio
async def test_a_review_turn_for_the_profile_is_refused_before_it_starts(folded):
    async with async_session_factory() as db:
        task = await db.get(Task, folded)
        refused = await review_dispatch_refusal(db, task, reviewer="Developer")
        assert refused is not None and refused[0] == 403
        assert "profile 'Developer'" in refused[1]
        assert await review_dispatch_refusal(db, task, reviewer="QA") is None


@pytest.mark.asyncio
async def test_the_profile_may_not_decide_the_folded_names_evidence(folded):
    await _grant("Developer", "QA")
    async with async_session_factory() as db:
        evidence = await db.get(RequirementEvidence, f"ev-{folded}")
        with pytest.raises(requirement_evidence.EvidenceRefusedError) as refused:
            await requirement_evidence.decide(
                db, evidence, decision="accepted", actor=Actor(kind="agent", name="Developer")
            )
        assert refused.value.code == "self_acceptance"
        assert "profile 'Developer'" in str(refused.value)

        # QA, granted like Developer, is another profile: its decision goes through.
        review = await requirement_evidence.decide(
            db, evidence, decision="accepted", actor=Actor(kind="agent", name="QA")
        )
        assert review.decision == "accepted"


@pytest.mark.asyncio
async def test_a_verdict_by_the_profile_decides_none_of_the_folded_names_pieces(folded):
    async with async_session_factory() as db:
        task = await db.get(Task, folded)
        mine = await requirement_evidence.verdict_pieces(
            db, task, actor=Actor(kind="agent", name="Developer"), decision="rejected"
        )
        assert mine == []


@pytest.mark.asyncio
async def test_the_reviewer_ladder_skips_the_profile(folded, bind_runner):
    await bind_runner("Developer")
    await bind_runner("QA")
    async with async_session_factory() as db:
        task = await db.get(Task, folded)
        exclude = {"DeveloperOpus": "is the one that completed this task"}
        widened = await widen_to_profiles(db, P, exclude)
        assert "profile 'Developer'" in widened["Developer"]
        # "Developer" sorts before "QA": without the profile it would be the one chosen.
        choice = await resolve_reviewer(db, task, project_id=P, exclude=exclude)
        assert choice.agent == "QA", choice


@pytest.mark.asyncio
async def test_a_named_checker_of_the_authors_profile_is_surfaced_not_staffed(app, add_agent):
    for name in ("Developer", "DeveloperOpus", "QA"):
        await add_agent(name)
    await _authored("t-2", "DeveloperOpus", checker="Developer")
    async with async_session_factory() as db:
        source = (
            await db.execute(
                select(Agent).where(Agent.project_id == P, Agent.name == "DeveloperOpus")
            )
        ).scalar_one()
        source.folded_into, source.lifecycle = "Developer", "archived"
        await db.commit()
    async with async_session_factory() as db:
        agent, declared, reason = await _choose(db, await db.get(Task, "t-2"))
        assert agent is None and declared is True
        assert "profile 'Developer'" in reason


@pytest.mark.asyncio
async def test_filing_a_task_whose_builder_and_checker_share_a_profile_is_refused(
    app, auth_headers, add_agent
):
    for name in ("Developer", "DeveloperOpus", "QA"):
        await add_agent(name)
    await _fold(app, auth_headers, "DeveloperOpus", "Developer")
    async with async_session_factory() as db:
        refused = await own_checker_refusal(
            db, None, builder="Developer", assignee=None, checker="DeveloperOpus", project_id=P
        )
        assert refused is not None and "profile 'Developer'" in refused
        assert (
            await own_checker_refusal(
                db, None, builder="Developer", assignee=None, checker="QA", project_id=P
            )
            is None
        )
    filed = await app.post(
        f"/api/v1/projects/{P}/tasks",
        json={
            "title": "Built and checked by one profile",
            "builder": "Developer",
            "checker": "DeveloperOpus",
        },
        headers=auth_headers,
    )
    # Refused before the profile check: a folded name is archived and holds no new task.
    assert filed.status_code == 422, filed.text
    assert "DeveloperOpus" in filed.text


# ------------------------------------------------------------------ same-name-still-refused


@pytest.mark.asyncio
async def test_with_nothing_folded_the_same_name_is_refused_as_before(app, add_agent):
    for name in ("Developer", "QA"):
        await add_agent(name)
    await _authored("t-3", "Developer", status="under_review", assignee="QA")
    async with async_session_factory() as db:
        task = await db.get(Task, "t-3")
        assert await authorship_reason(db, task, "Developer") == (
            "'Developer' is the agent recorded as completing it"
        )
        verdict = await decide_move(db, task, "approved", _run_of("Developer"))
        assert verdict.allowed is False
        assert "profile" not in verdict.reason
        assert (await decide_move(db, task, "approved", _run_of("QA"))).allowed

        evidence = await db.get(RequirementEvidence, "ev-t-3")
        await _grant("Developer")
        with pytest.raises(requirement_evidence.EvidenceRefusedError) as refused:
            await requirement_evidence.decide(
                db, evidence, decision="accepted", actor=Actor(kind="agent", name="Developer")
            )
        assert refused.value.code == "self_acceptance"
        assert str(refused.value).startswith("an agent cannot accept evidence it produced")

        assert await widen_to_profiles(db, P, {"Developer": "x"}) == {"Developer": "x"}
        assert (
            await own_checker_refusal(
                db, None, builder="Developer", assignee=None, checker="QA", project_id=P
            )
            is None
        )
