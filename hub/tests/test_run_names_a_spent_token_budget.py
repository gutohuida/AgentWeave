"""F441 -- pressing Run on a flow whose in-flight task is staffed to an idle agent that cannot start
its queued turn names the budget that holds it, rather than saying the task is "already being
worked".

`_held_in_flight_reasons` named only a provider hold. The project's token budget refuses an
autonomous turn the same way (`turn_scheduler._attempt_turn`), and the queued input waits.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Project, Run, TurnUsage

from .test_a_held_agent_is_busy import _queue
from .test_board_agent_role import live_scheduler  # noqa: F401  (fixture)
from .test_flow_width import _flow as _width_flow
from .test_flow_width import _task
from .test_review_turn import _roster

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("live_scheduler")]


async def _spend_the_budget(limit=100):
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.token_budget = limit
        db.add(Run(id="run-f441-history", project_id="proj-test", agent="hist", status="completed"))
        await db.flush()
        db.add(
            TurnUsage(
                id="usage-f441-history",
                run_id="run-f441-history",
                project_id="proj-test",
                agent="hist",
                status="measured",
                input_tokens=limit,
                output_tokens=0,
                total_tokens=limit,
            )
        )
        await db.commit()


async def _press(app, auth_headers, bind_runner, *, suffix, queue_origin):
    dev, lead = f"f441-dev-{suffix}", f"f441-lead-{suffix}"
    await _roster(app, auth_headers, bind_runner, dev, lead)
    async with async_session_factory() as db:
        job, loop = await _width_flow(db, suffix=f"f441-{suffix}", agent=lead)
        task = await _task(db, loop, f"f441-{suffix}", status="assigned", assignee=dev)
    await _queue(dev, f"conv-f441-{suffix}", origin_type=queue_origin, task_id=task.id)
    await _spend_the_budget()
    res = await app.post(f"/api/v1/projects/proj-test/jobs/{job.id}/run", headers=auth_headers)
    return dev, res


async def test_an_idle_assignee_waiting_on_the_token_budget_is_not_called_worked(
    app, auth_headers, bind_runner
):
    dev, res = await _press(app, auth_headers, bind_runner, suffix="job", queue_origin="job")

    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert "token budget" in detail
    assert dev in detail
    assert "already being worked" not in detail
    assert "nothing is wrong" not in detail


async def test_an_operators_input_is_not_held_by_the_token_budget(app, auth_headers, bind_runner):
    """The scheduler lets an operator's turn through a spent budget, so it is not named as held."""
    _dev, res = await _press(app, auth_headers, bind_runner, suffix="op", queue_origin="operator")

    assert res.status_code == 409, res.text
    assert "token budget" not in res.json()["detail"]
