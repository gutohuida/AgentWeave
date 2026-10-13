"""F456: an operator trigger on a spent token budget runs, and the answer and timeline say so."""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import EventLog, Project, Run, TurnUsage

from .test_accounting_budget import (
    _completed_claude_spawn,
    _configure_agent,
    asyncio_gather_background_runs,
)


async def _spend(limit: int, used: int) -> None:
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.token_budget = limit
        if used:
            session.add(
                Run(id="run-f456-hist", project_id="proj-test", agent="h", status="completed")
            )
            session.add(
                TurnUsage(
                    id="usage-f456-hist",
                    run_id="run-f456-hist",
                    project_id="proj-test",
                    agent="h",
                    status="measured",
                    input_tokens=used,
                    output_tokens=0,
                    total_tokens=used,
                )
            )
        await session.commit()


async def _trigger(app, auth_headers, name):
    with (
        patch("hub.api.v1.agent_trigger.PtySession.spawn", _completed_claude_spawn("f456")),
        patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"),
    ):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": name, "message": "go"},
            headers=auth_headers,
        )
        await asyncio_gather_background_runs()
    return response


async def _passed_over_events():
    async with async_session_factory() as session:
        return (
            (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == "token_budget_passed_over")
                )
            )
            .scalars()
            .all()
        )


@pytest.mark.asyncio
async def test_operator_trigger_on_a_spent_budget_says_it_was_passed_over(
    app, auth_headers, bind_runner
) -> None:
    name = "f456-over"
    await _configure_agent(app, auth_headers, bind_runner, name)
    await _spend(limit=100, used=100)

    response = await _trigger(app, auth_headers, name)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "running"
    assert "token budget is spent" in body["budget_note"]
    events = await _passed_over_events()
    assert len(events) == 1
    assert events[0].agent == name


@pytest.mark.asyncio
async def test_operator_trigger_under_budget_says_nothing_about_it(
    app, auth_headers, bind_runner
) -> None:
    name = "f456-under"
    await _configure_agent(app, auth_headers, bind_runner, name)
    await _spend(limit=1000, used=10)

    response = await _trigger(app, auth_headers, name)

    assert response.status_code == 200, response.text
    assert response.json()["budget_note"] is None
    assert await _passed_over_events() == []
