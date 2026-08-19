"""Durable accounting model contracts."""

import pytest
from sqlalchemy.exc import IntegrityError

from hub.db.engine import async_session_factory
from hub.db.models import Project, Run, TurnUsage
from hub.runner_events import AccountingSample
from hub.usage_accounting import conversation_usage, record_turn_usage


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


@pytest.mark.asyncio
async def test_record_turn_usage_is_idempotent_and_preserves_runner_telemetry(app) -> None:
    async with async_session_factory() as session:
        project = Project(id="proj-record", name="Record")
        run = Run(id="run-record", project_id=project.id, agent="claude")
        session.add_all([project, run])
        await session.flush()
        sample = AccountingSample(
            source="claude",
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
            api_equivalent_usd_micros=12_500,
            allowance={"five_hour": {"remaining_percent": 72}},
        )
        first = await record_turn_usage(
            session,
            run_id=run.id,
            project_id=project.id,
            agent="claude",
            runner="claude",
            sample=sample,
        )
        second = await record_turn_usage(
            session,
            run_id=run.id,
            project_id=project.id,
            agent="claude",
            runner="claude",
            sample=None,
        )
        await session.commit()

        assert second.id == first.id
        assert first.status == "measured"
        assert first.total_tokens == 120
        assert first.api_equivalent_usd_micros == 12_500
        assert first.allowance == {"five_hour": {"remaining_percent": 72}}


@pytest.mark.asyncio
async def test_conversation_usage_sums_only_that_conversations_runs(app) -> None:
    async with async_session_factory() as session:
        project = Project(id="proj-conv-usage", name="ConvUsage")
        session.add(project)
        session.add_all(
            [
                Run(
                    id="run-conv-a1",
                    project_id=project.id,
                    agent="claude",
                    conversation_id="conv-a",
                ),
                Run(
                    id="run-conv-a2",
                    project_id=project.id,
                    agent="claude",
                    conversation_id="conv-a",
                ),
                Run(
                    id="run-conv-b1",
                    project_id=project.id,
                    agent="claude",
                    conversation_id="conv-b",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                TurnUsage(
                    id="usage-conv-a1",
                    run_id="run-conv-a1",
                    project_id=project.id,
                    agent="claude",
                    status="measured",
                    total_tokens=100,
                ),
                TurnUsage(
                    id="usage-conv-a2",
                    run_id="run-conv-a2",
                    project_id=project.id,
                    agent="claude",
                    status="measured",
                    total_tokens=50,
                ),
                TurnUsage(
                    id="usage-conv-b1",
                    run_id="run-conv-b1",
                    project_id=project.id,
                    agent="claude",
                    status="measured",
                    total_tokens=999,
                ),
            ]
        )
        await session.commit()

        summary = await conversation_usage(session, project.id, "conv-a")
        assert summary["total_tokens"] == 150
        assert summary["measured_turns"] == 2
        assert summary["unavailable_turns"] == 0

        empty = await conversation_usage(session, project.id, "conv-nonexistent")
        assert empty["total_tokens"] is None
        assert empty["measured_turns"] == 0
