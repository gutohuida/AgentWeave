"""Durable accounting model contracts."""

import pytest
from sqlalchemy.exc import IntegrityError

from hub.db.engine import async_session_factory
from hub.db.models import Project, Run, TurnUsage


@pytest.mark.asyncio
async def test_measured_turn_usage_round_trips_once_per_run(app) -> None:
    async with async_session_factory() as session:
        project = Project(id="proj-accounting", name="Accounting", token_budget=50_000)
        run = Run(
            id="run-accounting",
            project_id=project.id,
            agent="codex",
            initiator="autonomous",
        )
        session.add_all([project, run])
        await session.flush()
        usage = TurnUsage(
            id="usage-accounting",
            run_id=run.id,
            project_id=project.id,
            agent="codex",
            status="measured",
            runner="codex",
            input_tokens=120,
            output_tokens=30,
            total_tokens=150,
            cache_read_tokens=80,
            reasoning_tokens=10,
        )
        session.add(usage)
        await session.commit()
        await session.refresh(project)
        await session.refresh(run)
        await session.refresh(usage)

        assert project.token_budget == 50_000
        assert run.initiator == "autonomous"
        assert usage.total_tokens == 150
        assert usage.observed_at is not None

        session.add(
            TurnUsage(
                id="usage-duplicate",
                run_id=run.id,
                project_id=project.id,
                agent="codex",
                status="unavailable",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_unavailable_usage_has_no_fabricated_token_values(app) -> None:
    async with async_session_factory() as session:
        project = Project(id="proj-unavailable", name="Unavailable")
        run = Run(id="run-unavailable", project_id=project.id, agent="claude")
        session.add_all([project, run])
        await session.flush()
        usage = TurnUsage(
            id="usage-unavailable",
            run_id=run.id,
            project_id=project.id,
            agent="claude",
            status="unavailable",
            runner="claude",
        )
        session.add(usage)
        await session.commit()
        await session.refresh(project)
        await session.refresh(run)
        await session.refresh(usage)

        assert project.token_budget is None
        assert run.initiator == "operator"
        assert usage.input_tokens is None
        assert usage.output_tokens is None
        assert usage.total_tokens is None
