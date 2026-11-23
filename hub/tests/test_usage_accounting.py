"""The mender's spending is manager work, not an agent's turns (FR-11, mender-spend-attribution)."""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Run, TurnUsage


def _turn(agent: str, model: str, micros: int, tokens: int) -> tuple[Run, TurnUsage]:
    return (
        Run(id=f"run-{agent}", project_id="proj-test", agent=agent),
        TurnUsage(
            id=f"usage-{agent}",
            run_id=f"run-{agent}",
            project_id="proj-test",
            agent=agent,
            status="measured",
            model=model,
            total_tokens=tokens,
            output_tokens=tokens // 2,
            api_equivalent_usd_micros=micros,
        ),
    )


@pytest.mark.asyncio
async def test_mender_spend_is_a_workers_line_and_the_project_total_is_unchanged(
    app, auth_headers
) -> None:
    async with async_session_factory() as session:
        for run, usage in (
            _turn("claude", "M-agent", 50_000, 100),
            _turn("mender", "M", 100_000, 40),
        ):
            session.add(run)
            session.add(usage)
        await session.commit()

    data = (await app.get("/api/v1/projects/proj-test/accounting", headers=auth_headers)).json()

    assert [a["agent"] for a in data["agents"]] == ["claude"]
    assert data["agents"][0]["api_equivalent_usd_micros"] == 50_000
    (line,) = [w for w in data["workers"] if w["kind"] == "mender"]
    assert line["api_equivalent_usd_micros"] == 100_000
    assert line["total_tokens"] == 40
    assert line["measured_calls"] == 1
    # The same $0.15 and 140 tokens as when the mender was counted among the agents.
    assert data["project"]["api_equivalent_usd_micros"] == 150_000
    assert data["project"]["total_tokens"] == 140
    # The row still names the model it ran on, which is what a by-model breakdown reads.
    async with async_session_factory() as session:
        row = await session.get(TurnUsage, "usage-mender")
        assert row.model == "M"


@pytest.mark.asyncio
async def test_no_mender_turns_adds_no_mender_line(app, auth_headers) -> None:
    async with async_session_factory() as session:
        run, usage = _turn("claude", "M", 1000, 10)
        session.add(run)
        session.add(usage)
        await session.commit()
    data = (await app.get("/api/v1/projects/proj-test/accounting", headers=auth_headers)).json()
    assert [w["kind"] for w in data["workers"]] == []
