"""Every task status, in every holder situation, has an agent that can move it on.

`every-task-can-always-be-moved-on`, FR-1, FR-3, FR-4, FR-8. Four times in four days a task sat in a
state nobody could move: rules that were each sensible, checked in about sixteen places. The
acceptance drive is this file, run on master 43301a6 first: `completed` held by its author, outside a
flow, had no agent mover (QA's `update_task(under_review)` came back 403 because the author held it).

The enumeration drives `update_task_for_actor`, the route's own entry point, so it fails on master
rather than agreeing with a new function that does not exist there.
"""

import itertools
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from hub.api.v1.agent_trigger import review_dispatch_refusal
from hub.api.v1.tasks import update_task_for_actor
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Build, RequirementEvidence, SpecRequirement, Task
from hub.schemas.tasks import TaskUpdate
from hub.task_transition_service import TransitionRefusedError, apply_transition
from hub.task_transitions import BAND_TERMINAL, STATUS_BANDS, TRANSITIONS, run_actor

from .test_a_stalled_project_wakes_the_mender import mender_run

pytestmark = pytest.mark.asyncio

AUTHOR = "mv-author"
OTHER = "mv-other"
MENDER = "mender"
#: A build's lead (`a-build-has-a-driver-a-level-and-its-people`, FR-12): a holder, and a mover.
LEAD = "mv-lead"
RESET = "/api/v1/agent-actions/mender/tasks/{}/reset"

NON_TERMINAL = sorted(s for s, band in STATUS_BANDS.items() if band != BAND_TERMINAL)
HOLDERS = ("none", "author", "other", "mender")
#: The build levels, and no build at all (slice D): a level is an input to the one decision and
#: must add no dead end.
LEVELS = (None, "fast", "reviewed", "gated")
_ids = itertools.count(1)
_HOLDER_AGENT = {"none": None, "author": AUTHOR, "other": OTHER, "mender": MENDER, "lead": LEAD}


async def _task(status: str, holder: str, level: Optional[str] = None) -> str:
    """A task in *status* whose author is AUTHOR, held as *holder* says, in a build at *level*
    led by LEAD (none when *level* is None).

    Completed through the machine so the author is on the record; the mender holder is the case
    the 2026-10-25 retrospective measured -- the mender re-recorded evidence and so became an author.
    """
    n = next(_ids)
    task_id = f"task-mv-{n}"
    async with async_session_factory() as session:
        task = Task(
            id=task_id, project_id="proj-test", title=task_id, status="in_progress", assignee=None
        )
        if level is not None:
            build_id = f"build-mv-{n}"
            session.add(
                Build(
                    id=build_id,
                    project_id="proj-test",
                    document_id=f"doc-mv-build-{n}",
                    state="running",
                    driver="lead",
                    level=level,
                    builders=[],
                    reviewers=[],
                    lead=LEAD,
                    landing="main",
                )
            )
            task.build_id, task.level = build_id, level
        session.add(task)
        await session.flush()
        await apply_transition(session, task, "completed", run_actor(f"run-mv-{n}", AUTHOR))
        task.status = status
        task.assignee = _HOLDER_AGENT[holder]
        if holder == "mender":
            session.add(
                SpecRequirement(
                    id=f"req-mv-{n}",
                    project_id="proj-test",
                    document_id=f"doc-mv-{n}",
                    identifier="FR-1",
                    key="fr-1",
                    digest="d" * 64,
                )
            )
            session.add(
                RequirementEvidence(
                    id=f"ev-mv-{n}",
                    project_id="proj-test",
                    requirement_id=f"req-mv-{n}",
                    task_id=task_id,
                    digest="d" * 64,
                    kind="artifact_diff",
                    actor_kind="agent",
                    actor=MENDER,
                    summary="re-recorded",
                )
            )
        await session.commit()
    return task_id


async def _agents(lead: bool = False) -> None:
    async with async_session_factory() as session:
        for name in (AUTHOR, OTHER, *([LEAD] if lead else [])):
            session.add(Agent(id=f"ag-{name}", project_id="proj-test", name=name))
        await session.commit()


async def _move(task_id: str, to_status: str, agent: str):
    """The agent route's call. Returns `(None, task)` when allowed, `(refusal, task)` when not."""
    async with async_session_factory() as session:
        try:
            await update_task_for_actor(
                task_id,
                TaskUpdate(status=to_status),
                project_id="proj-test",
                actor=run_actor(f"run-act-{next(_ids)}", agent),
                session=session,
            )
        except (HTTPException, TransitionRefusedError) as refusal:
            return refusal, None
    async with async_session_factory() as session:
        return None, await session.get(Task, task_id)


def _detail(refusal) -> str:
    return str(refusal.detail if isinstance(refusal, HTTPException) else refusal)


# --------------------------------------------------------------------------------------
# FR-1: the invariant
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("level", LEVELS)
async def test_every_unfinished_status_and_holder_has_a_mover(app, level):
    """Each non-terminal status, held each way: some agent can move it to some other status --
    at every build level and outside any build, with a build's lead among the holders and the
    movers (slice D, FR-12).

    `blocked` is exempt by design (its mover is the operator). `approved` is left out of the
    targets because approving runs the merge gates, which this question is not about; the
    verdict half of a review is `revision_needed`, reached under the same author rule.
    """
    await _agents(lead=level is not None)
    holders = HOLDERS if level is None else (*HOLDERS, "lead")
    movers = (AUTHOR, OTHER, MENDER) if level is None else (AUTHOR, OTHER, MENDER, LEAD)
    stuck = []
    for status, holder in itertools.product(NON_TERMINAL, holders):
        if status == "blocked":
            continue
        targets = [t for t in TRANSITIONS[status] if t not in ("approved", "blocked")]
        moved = None
        for agent, target in itertools.product(movers, targets):
            refusal, _ = await _move(await _task(status, holder, level), target, agent)
            if refusal is None:
                moved = (agent, target)
                break
        if moved is None:
            stuck.append(f"{status} held by {holder}")
    assert not stuck, f"no agent can move at level {level}: {stuck}"


@pytest.mark.parametrize("level", ["fast", "reviewed", "gated"])
async def test_a_completed_task_in_a_build_is_approved_only_where_its_level_says(app, level):
    """The level's own edge (D4): from `completed`, the builder and the lead approve at Fast and
    nowhere else; another agent never does, and review stays open to it at every level."""
    from hub.task_transition_service import decide_move

    await _agents(lead=True)
    task_id = await _task("completed", "author", level)
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        for agent in (AUTHOR, LEAD):
            verdict = await decide_move(session, task, "approved", run_actor("run-lv", agent))
            assert verdict.allowed == (level == "fast"), (agent, level, verdict.reason)
            if not verdict.allowed:
                assert level in (verdict.reason or ""), verdict.reason
        assert not (await decide_move(session, task, "approved", run_actor("run-o", OTHER))).allowed
    refusal, _ = await _move(task_id, "under_review", OTHER)
    assert refusal is None, _detail(refusal)


# --------------------------------------------------------------------------------------
# FR-3 / FR-4
# --------------------------------------------------------------------------------------


async def test_a_reviewer_takes_completed_work_and_becomes_its_holder(app):
    await _agents()
    task_id = await _task("completed", "author")
    refusal, task = await _move(task_id, "under_review", OTHER)
    assert refusal is None, _detail(refusal)
    assert task.status == "under_review"
    assert task.assignee == OTHER
    # And can then send it back, or approve it: the author rule no longer stands in the way.
    from hub.task_transition_service import decide_move
    from hub.task_transitions import run_actor as actor_of

    async with async_session_factory() as session:
        held = await session.get(Task, task_id)
        for verdict in ("approved", "revision_needed"):
            assert (await decide_move(session, held, verdict, actor_of("run-x", OTHER))).allowed
    sent_back, task = await _move(task_id, "revision_needed", OTHER)
    assert sent_back is None, _detail(sent_back)


@pytest.mark.parametrize("target", ["under_review", "approved"])
async def test_the_author_cannot_review_its_own_work(app, target):
    await _agents()
    refusal, _ = await _move(await _task("completed", "author"), target, AUTHOR)
    assert refusal is not None


@pytest.mark.parametrize("target", ["under_review", "approved"])
async def test_a_mender_that_re_recorded_evidence_cannot_review_it(app, target):
    await _agents()
    task_id = await _task("completed", "mender")
    refusal, _ = await _move(task_id, target, MENDER)
    assert refusal is not None
    headers = await mender_run()
    from httpx import ASGITransport, AsyncClient  # noqa: F401

    refused = await app.post(
        RESET.format(task_id), json={"status": "under_review", "assignee": MENDER}, headers=headers
    )
    assert refused.status_code in (400, 403), refused.text


# --------------------------------------------------------------------------------------
# FR-8: one answer on every path
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("holder", ["none", "author", "other"])
@pytest.mark.parametrize("reviewer", [AUTHOR, OTHER])
async def test_every_path_gives_the_same_answer_for_entering_review(app, holder, reviewer):
    """`update_task`, the flow's review claim and the mender's reset, for one reviewer and holder.

    Compared on completed work, the status review is entered from: the dispatch refuses any other
    status for a different reason (it is not an edge), which is not an author question.
    """
    await _agents()
    task_id = await _task("completed", holder)
    mender = await mender_run()

    refusal, _ = await _move(task_id, "under_review", reviewer)
    async with async_session_factory() as session:
        dispatch = await review_dispatch_refusal(
            session, await session.get(Task, task_id), reviewer=reviewer
        )
    with patch("hub.turn_scheduler.schedule_accepted", AsyncMock()):
        reset = await app.post(
            RESET.format(task_id),
            json={"status": "under_review", "assignee": reviewer},
            headers=mender,
        )

    verdicts = {
        "update_task": refusal is not None,
        "review claim": dispatch is not None,
        # A mender hand-off for an allowed reviewer may still stop at a missing git checkout (409);
        # the author rule's own answer is 403.
        "mender reset": reset.status_code == 403,
    }
    assert len(set(verdicts.values())) == 1, (verdicts, refusal, dispatch, reset.text)
    if refusal is not None:
        clause = "recorded as completing it"
        assert clause in _detail(refusal)
        assert clause in dispatch[1]
        assert clause in reset.json()["detail"]


async def test_the_board_is_offered_exactly_the_moves_the_decision_allows(app, auth_headers):
    """The operator's moves for a task are `decide_move`'s answer, not the map's.

    Review is entered by naming who reviews (`reviewers`), so `under_review` is offered from a
    completed task exactly when some agent the decision allows as its holder exists: a task its
    author holds is not offered the move that keeps the author, and is offered the hand-off.
    """
    from hub.task_transition_service import decide_move
    from hub.task_transitions import allowed_targets, operator

    await _agents()
    for status, holder in itertools.product(NON_TERMINAL, HOLDERS):
        task_id = await _task(status, holder)
        routed = await app.get(
            f"/api/v1/projects/proj-test/tasks/{task_id}/moves", headers=auth_headers
        )
        assert routed.status_code == 200, routed.text
        async with async_session_factory() as session:
            task = await session.get(Task, task_id)
            expected = []
            for t in sorted(allowed_targets(status, "operator")):
                if (await decide_move(session, task, t, operator())).allowed:
                    expected.append(t)
            reviewers = []
            if status == "completed":
                for name in (AUTHOR, OTHER, MENDER):
                    task.assignee = name
                    if (await decide_move(session, task, "under_review", operator())).allowed:
                        reviewers.append(name)
                task.assignee = {"none": None, "author": AUTHOR, "other": OTHER, "mender": MENDER}[
                    holder
                ]
                if reviewers and "under_review" not in expected:
                    expected = sorted([*expected, "under_review"])
        assert routed.json()["moves"] == expected, (status, holder)
        if status == "completed":
            # Agents known to the project are AUTHOR and OTHER; the mender is not a roster agent here.
            assert routed.json()["reviewers"] == [r for r in reviewers if r in (AUTHOR, OTHER)]
            assert AUTHOR not in routed.json()["reviewers"]
            assert "under_review" in expected


async def test_the_operator_hands_a_completed_task_to_a_reviewer_who_becomes_its_holder(
    app, auth_headers
):
    await _agents()
    task_id = await _task("completed", "author")
    kept = await app.patch(
        f"/api/v1/projects/proj-test/tasks/{task_id}",
        json={"status": "under_review"},
        headers=auth_headers,
    )
    assert kept.status_code == 403, kept.text
    handed = await app.patch(
        f"/api/v1/projects/proj-test/tasks/{task_id}",
        json={"status": "under_review", "assignee": OTHER},
        headers=auth_headers,
    )
    assert handed.status_code == 200, handed.text
    assert handed.json()["status"] == "under_review"
    assert handed.json()["assignee"] == OTHER


@pytest.mark.parametrize("holder", HOLDERS)
@pytest.mark.parametrize("reviewer", [AUTHOR, OTHER])
@pytest.mark.parametrize(
    "status", [s for s in NON_TERMINAL if s not in ("completed", "under_review")]
)
async def test_entering_review_from_any_other_status_is_refused_on_every_path(
    app, status, holder, reviewer
):
    """FR-8 for the rest of the enumeration: review is entered from `completed` only, so from any
    other status all three paths must refuse. The reasons legitimately differ -- the review claim
    and the reset refuse it as not an edge, `update_task` for its own reason -- so what is
    compared is the verdict, not the wording (the wording is compared on `completed` above)."""
    if (status, "under_review") in {(s, t) for s, ts in TRANSITIONS.items() for t in ts}:
        pytest.skip("review is an edge from this status; covered by the completed comparison")
    await _agents()
    task_id = await _task(status, holder)
    mender = await mender_run()

    refusal, _ = await _move(task_id, "under_review", reviewer)
    async with async_session_factory() as session:
        dispatch = await review_dispatch_refusal(
            session, await session.get(Task, task_id), reviewer=reviewer
        )
    with patch("hub.turn_scheduler.schedule_accepted", AsyncMock()):
        reset = await app.post(
            RESET.format(task_id),
            json={"status": "under_review", "assignee": reviewer},
            headers=mender,
        )

    assert refusal is not None, (status, holder, reviewer)
    assert dispatch is not None, (status, holder, reviewer)
    assert reset.status_code in (400, 403, 409), (status, holder, reviewer, reset.text)
