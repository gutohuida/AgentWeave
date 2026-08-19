"""Project-scoped accounting aggregation and budget API contracts."""

from datetime import datetime, timedelta, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Project, Run, TurnUsage


async def _seed_usage() -> None:
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        assert project is not None
        project.token_budget = 300
        other = Project(id="proj-other-accounting", name="Other", token_budget=1)
        session.add(other)
        now = datetime.now(timezone.utc)
        rows = [
            ("run-a1", "claude", "measured", 100, 20, 120, 10_000, None, now),
            (
                "run-a2",
                "claude",
                "measured",
                80,
                30,
                110,
                20_000,
                {"five_hour": {"remaining_percent": 64}},
                now + timedelta(seconds=2),
            ),
            ("run-b1", "codex", "unavailable", None, None, None, None, None, now),
        ]
        for index, (
            run_id,
            agent,
            status,
            input_tokens,
            output_tokens,
            total_tokens,
            cost,
            allowance,
            observed_at,
        ) in enumerate(rows):
            session.add(Run(id=run_id, project_id=project.id, agent=agent, status="completed"))
            session.add(
                TurnUsage(
                    id=f"usage-{index}",
                    run_id=run_id,
                    project_id=project.id,
                    agent=agent,
                    status=status,
                    runner=agent,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    api_equivalent_usd_micros=cost,
                    allowance=allowance,
                    observed_at=observed_at,
                )
            )
        session.add(Run(id="run-other", project_id=other.id, agent="claude", status="completed"))
        session.add(
            TurnUsage(
                id="usage-other",
                run_id="run-other",
                project_id=other.id,
                agent="claude",
                status="measured",
                input_tokens=999,
                output_tokens=1,
                total_tokens=1000,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_accounting_aggregates_by_agent_and_project_without_cross_project_leak(
    app, auth_headers
) -> None:
    await _seed_usage()

    response = await app.get("/api/v1/projects/proj-test/accounting", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    assert data["project"] == {
        "input_tokens": 180,
        "output_tokens": 50,
        "total_tokens": 230,
        "measured_turns": 2,
        "unavailable_turns": 1,
        "api_equivalent_usd_micros": 30_000,
    }
    assert data["agents"] == [
        {
            "agent": "claude",
            "input_tokens": 180,
            "output_tokens": 50,
            "total_tokens": 230,
            "measured_turns": 2,
            "unavailable_turns": 0,
            "api_equivalent_usd_micros": 30_000,
        },
        {
            "agent": "codex",
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "measured_turns": 0,
            "unavailable_turns": 1,
            "api_equivalent_usd_micros": None,
        },
    ]
    assert data["budget"] == {
        "limit_tokens": 300,
        "used_tokens": 230,
        "remaining_tokens": 70,
        "exhausted": False,
    }
    assert all(turn["total_tokens"] != 1000 for turn in data["recent_turns"])


@pytest.mark.asyncio
async def test_allowance_precedes_api_equivalent_and_unavailable_is_not_zero(
    app, auth_headers
) -> None:
    await _seed_usage()

    data = (await app.get("/api/v1/projects/proj-test/accounting", headers=auth_headers)).json()
    assert data["preferred_display"] == {
        "kind": "allowance",
        "label": "Rate-limit allowance",
        "allowance": {"five_hour": {"remaining_percent": 64}},
    }
    unavailable = next(turn for turn in data["recent_turns"] if turn["status"] == "unavailable")
    assert unavailable["total_tokens"] is None


@pytest.mark.asyncio
async def test_api_equivalent_label_is_explicit_when_no_allowance(app, auth_headers) -> None:
    async with async_session_factory() as session:
        session.add(Run(id="run-cost", project_id="proj-test", agent="claude"))
        session.add(
            TurnUsage(
                id="usage-cost",
                run_id="run-cost",
                project_id="proj-test",
                agent="claude",
                status="measured",
                input_tokens=9,
                output_tokens=1,
                total_tokens=10,
                api_equivalent_usd_micros=12_500,
            )
        )
        await session.commit()

    display = (await app.get("/api/v1/projects/proj-test/accounting", headers=auth_headers)).json()[
        "preferred_display"
    ]
    assert display == {
        "kind": "api_equivalent",
        "label": "API-equivalent estimate",
        "usd_micros": 12_500,
    }


@pytest.mark.asyncio
async def test_budget_patch_accepts_positive_or_null_and_rejects_nonpositive(
    app, auth_headers
) -> None:
    enabled = await app.patch(
        "/api/v1/projects/proj-test/accounting/budget",
        json={"token_budget": 42},
        headers=auth_headers,
    )
    assert enabled.status_code == 200
    assert enabled.json()["limit_tokens"] == 42

    for invalid in (0, -1):
        response = await app.patch(
            "/api/v1/projects/proj-test/accounting/budget",
            json={"token_budget": invalid},
            headers=auth_headers,
        )
        assert response.status_code == 422

    disabled = await app.patch(
        "/api/v1/projects/proj-test/accounting/budget",
        json={"token_budget": None},
        headers=auth_headers,
    )
    assert disabled.status_code == 200
    assert disabled.json() == {
        "limit_tokens": None,
        "used_tokens": 0,
        "remaining_tokens": None,
        "exhausted": False,
    }


@pytest.mark.asyncio
async def test_conversation_accounting_sums_that_conversation_and_ignores_the_project_cap(
    app, auth_headers
) -> None:
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        assert project is not None
        # More rows than `accounting_snapshot`'s `recent_limit` default (50) — a conversation
        # rollup has to be a real aggregate, not a slice of the project-wide recent window.
        for index in range(60):
            run_id = f"run-conv-many-{index}"
            session.add(
                Run(id=run_id, project_id=project.id, agent="claude", conversation_id="conv-many")
            )
            session.add(
                TurnUsage(
                    id=f"usage-conv-many-{index}",
                    run_id=run_id,
                    project_id=project.id,
                    agent="claude",
                    status="measured",
                    total_tokens=10,
                )
            )
        session.add(
            Run(
                id="run-conv-other",
                project_id=project.id,
                agent="claude",
                conversation_id="conv-other",
            )
        )
        session.add(
            TurnUsage(
                id="usage-conv-other",
                run_id="run-conv-other",
                project_id=project.id,
                agent="claude",
                status="measured",
                total_tokens=777,
            )
        )
        await session.commit()

    response = await app.get(
        "/api/v1/projects/proj-test/accounting/conversations/conv-many", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json() == {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": 600,
        "measured_turns": 60,
        "unavailable_turns": 0,
        "api_equivalent_usd_micros": None,
    }


@pytest.mark.asyncio
async def test_conversation_accounting_unknown_conversation_is_zero_not_404(
    app, auth_headers
) -> None:
    response = await app.get(
        "/api/v1/projects/proj-test/accounting/conversations/conv-nonexistent", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["measured_turns"] == 0


@pytest.mark.asyncio
async def test_accounting_routes_require_auth(app) -> None:
    assert (await app.get("/api/v1/projects/proj-test/accounting")).status_code == 401
    assert (
        await app.patch("/api/v1/projects/proj-test/accounting/budget", json={"token_budget": 10})
    ).status_code == 401
    assert (
        await app.get("/api/v1/projects/proj-test/accounting/conversations/conv-many")
    ).status_code == 401
