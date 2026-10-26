"""The mender is the Hub's repair agent, never a flow's builder or reviewer.

Measured on the operator's Hub (loop-df5f74816122, 2026-10-25): the flow's 16:15 firing assigned
task-0759b1b3aa12, a build task, to `mender`, because `_roster_availability` read every open agent
with a runner as staffable. The mender then built, completed and re-recorded evidence for it, and
the Hub counted it as the task's author -- which is what later held the task in `completed` with no
agent able to move it on.
"""

import pytest
from sqlalchemy import select

from hub import stalls
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Task
from hub.scheduler import decide_firing, resolve_reviewer

from .test_a_flow_does_not_hand_fresh_work_to_its_named_reviewer import _flow
from .test_agent_trigger import _init_repo
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio


async def _make_the_mender_the_hubs():
    async with async_session_factory() as db:
        mender = (await db.execute(select(Agent).where(Agent.name == stalls.MENDER))).scalar_one()
        mender.config = {"hub_role": stalls.HUB_ROLE}
        await db.commit()


async def test_a_flow_does_not_hand_build_work_to_the_mender(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, "builder", stalls.MENDER)
    await _make_the_mender_the_hubs()
    async with async_session_factory() as db:
        loop = await _flow(db, repo, delivery={})
        decision = await decide_firing(db, loop, default_agent="builder")
    assert [s.agent for s in decision.selections] == ["builder"]


async def test_the_review_ladder_does_not_offer_a_review_to_the_mender(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, "builder", stalls.MENDER)
    await _make_the_mender_the_hubs()
    async with async_session_factory() as db:
        task = Task(id="task-mender-rev", project_id="proj-test", title="t", status="completed")
        db.add(task)
        await db.commit()
        choice = await resolve_reviewer(
            db, task, project_id="proj-test", exclude={"builder": "is the one that completed it"}
        )
    assert choice.agent is None
    assert stalls.MENDER not in (choice.reason or "")
