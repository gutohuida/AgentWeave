"""The build retrospective fires once the run that approved the last task has ended.

:8000, 2026-11-04: both retrospectives (evt-6c6d19e61f20, evt-dc38021f39ec) read the approving QA
and QA2 runs (run-14a3aa435478, run-df2d93e14e9a) as still running with no cost and no model. A
reviewer approves inside its own turn, the firing assembled the record at that commit, and the
run's end and usage are recorded only when the turn ends: 01:24:13 approved, 01:24:18 assembled,
01:24:22 ended with $0.64 of Opus.
"""

import pytest
from sqlalchemy import select

from hub import build_retrospective as br
from hub.db.engine import async_session_factory
from hub.db.models import Run, Task
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

from .test_build_retrospective import (
    P,
    _configure,
    _document,
    _firings,
    _seed,
    _task,
    _usage,
    _Worker,
)

REVIEWER_RUN = "run-qa-approves"


@pytest.fixture
def worker(monkeypatch):
    def install():
        fake = _Worker()
        monkeypatch.setattr(br, "run_worker", fake)
        return fake

    return install


async def _approved_by_a_running_reviewer():
    await _seed(
        _document(),
        _task("t1", assignee="qa"),
        Run(
            id=REVIEWER_RUN, project_id=P, agent="qa", task_id="t1", status="running", turn_depth=0
        ),
    )
    async with async_session_factory() as session:
        task = await session.get(Task, "t1")
        await apply_transition(session, task, "approved", run_actor(REVIEWER_RUN, "qa"))
        await session.commit()


async def _end_the_run():
    async with async_session_factory() as session:
        run = (await session.execute(select(Run).where(Run.id == REVIEWER_RUN))).scalar_one()
        run.status = "completed"
        session.add(_usage(REVIEWER_RUN, "qa", micros=642_610, tokens=631_908))
        await session.commit()


def _approving_run_in(prompt):
    return prompt[prompt.index(REVIEWER_RUN) :][:600]


@pytest.mark.asyncio
async def test_the_firing_waits_for_the_approving_run_and_reads_its_cost(app, auth_headers, worker):
    fake = worker()
    await _configure(app, auth_headers)
    await _approved_by_a_running_reviewer()

    assert await _firings() == [] and fake.calls == []

    await _end_the_run()
    br.after_run(P, REVIEWER_RUN)

    (firing,) = await _firings()
    assert firing["trigger"] == br.LAST_TASK_APPROVED
    [call] = fake.calls
    reading = _approving_run_in(call["prompt"])
    assert '"status": "completed"' in reading and '"cost_usd_micros": 642610' in reading


@pytest.mark.asyncio
async def test_an_approving_run_that_already_ended_fires_at_once(app, auth_headers, worker):
    fake = worker()
    await _configure(app, auth_headers)
    await _seed(
        _document(),
        _task("t1", assignee="qa"),
        Run(
            id=REVIEWER_RUN, project_id=P, agent="qa", task_id="t1", status="running", turn_depth=0
        ),
    )
    async with async_session_factory() as session:
        task = await session.get(Task, "t1")
        await apply_transition(session, task, "approved", run_actor(REVIEWER_RUN, "qa"))
        run = await session.get(Run, REVIEWER_RUN)
        run.status = "completed"  # ended before the approval's commit was seen
        await session.commit()

    assert len(await _firings()) == 1 and len(fake.calls) == 1


@pytest.mark.asyncio
async def test_a_run_that_never_ends_does_not_hold_the_review_forever(
    app, auth_headers, worker, monkeypatch
):
    fake = worker()
    monkeypatch.setattr(br, "RUN_END_WAIT_SECONDS", 0.05)
    await _configure(app, auth_headers)
    await _approved_by_a_running_reviewer()
    await _firings()
    timer = br._run_end_timers.get(REVIEWER_RUN)
    assert timer is not None
    await timer

    assert len(await _firings()) == 1 and len(fake.calls) == 1
