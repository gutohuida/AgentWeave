"""Project-scoped accounting aggregation and budget API contracts."""

from datetime import datetime, timedelta, timezone

import pytest

from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import Project, Run, TurnUsage
from hub.usage_accounting import project_budget_state


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
        "unpriced_turns": 1,
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
            "unpriced_turns": 0,
        },
        {
            "agent": "codex",
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "measured_turns": 0,
            "unavailable_turns": 1,
            "api_equivalent_usd_micros": None,
            "unpriced_turns": 1,
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
        "unpriced_turns": 0,
    }


@pytest.mark.asyncio
async def test_unpriced_turns_counts_every_turn_with_no_reported_cost(app, auth_headers) -> None:
    async with async_session_factory() as session:
        session.add(Run(id="run-priced", project_id="proj-test", agent="claude"))
        session.add(
            TurnUsage(
                id="usage-priced",
                run_id="run-priced",
                project_id="proj-test",
                agent="claude",
                status="measured",
                total_tokens=10,
                api_equivalent_usd_micros=1000,
            )
        )
        # A Codex-shaped turn: tokens reported, no cost — neither Codex path passes one.
        session.add(Run(id="run-codex", project_id="proj-test", agent="codex"))
        session.add(
            TurnUsage(
                id="usage-codex",
                run_id="run-codex",
                project_id="proj-test",
                agent="codex",
                status="measured",
                total_tokens=20,
            )
        )
        session.add(Run(id="run-unavailable", project_id="proj-test", agent="codex"))
        session.add(
            TurnUsage(
                id="usage-unavailable",
                run_id="run-unavailable",
                project_id="proj-test",
                agent="codex",
                status="unavailable",
            )
        )
        await session.commit()

    data = (await app.get("/api/v1/projects/proj-test/accounting", headers=auth_headers)).json()
    assert data["project"]["api_equivalent_usd_micros"] == 1000
    assert data["project"]["unpriced_turns"] == 2
    assert data["preferred_display"] == {
        "kind": "api_equivalent",
        "label": "API-equivalent estimate",
        "usd_micros": 1000,
        "unpriced_turns": 2,
    }


@pytest.mark.asyncio
async def test_unpriced_turns_is_per_agent_in_the_routes_own_order(app, auth_headers) -> None:
    async with async_session_factory() as session:
        session.add(Run(id="run-alpha", project_id="proj-test", agent="alpha"))
        session.add(
            TurnUsage(
                id="usage-alpha",
                run_id="run-alpha",
                project_id="proj-test",
                agent="alpha",
                status="measured",
                total_tokens=5,
            )
        )
        session.add(Run(id="run-zulu", project_id="proj-test", agent="zulu"))
        session.add(
            TurnUsage(
                id="usage-zulu",
                run_id="run-zulu",
                project_id="proj-test",
                agent="zulu",
                status="measured",
                total_tokens=5,
                api_equivalent_usd_micros=500,
            )
        )
        await session.commit()

    data = (await app.get("/api/v1/projects/proj-test/accounting", headers=auth_headers)).json()
    assert [(agent["agent"], agent["unpriced_turns"]) for agent in data["agents"]] == [
        ("alpha", 1),
        ("zulu", 0),
    ]


@pytest.mark.asyncio
async def test_unpriced_turns_is_zero_when_every_turn_is_priced(app, auth_headers) -> None:
    async with async_session_factory() as session:
        session.add(Run(id="run-only", project_id="proj-test", agent="claude"))
        session.add(
            TurnUsage(
                id="usage-only",
                run_id="run-only",
                project_id="proj-test",
                agent="claude",
                status="measured",
                total_tokens=5,
                api_equivalent_usd_micros=2500,
            )
        )
        await session.commit()

    data = (await app.get("/api/v1/projects/proj-test/accounting", headers=auth_headers)).json()
    assert data["project"]["unpriced_turns"] == 0
    assert data["preferred_display"]["unpriced_turns"] == 0


@pytest.mark.asyncio
async def test_copilot_credits_aggregate_alongside_claude_tokens(app, auth_headers) -> None:
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        session.add(Run(id="run-credits-claude", project_id="proj-test", agent="a-claude"))
        session.add(
            TurnUsage(
                id="usage-credits-claude",
                run_id="run-credits-claude",
                project_id="proj-test",
                agent="a-claude",
                status="measured",
                runner="claude",
                total_tokens=1000,
                observed_at=now,
            )
        )
        session.add(Run(id="run-credits-copilot-1", project_id="proj-test", agent="b-copilot"))
        session.add(
            TurnUsage(
                id="usage-credits-copilot-1",
                run_id="run-credits-copilot-1",
                project_id="proj-test",
                agent="b-copilot",
                status="measured",
                runner="copilot",
                total_tokens=500,
                ai_nano_aiu=200_000_000,
                premium_requests=1.0,
                observed_at=now + timedelta(seconds=2),
            )
        )
        session.add(Run(id="run-credits-copilot-2", project_id="proj-test", agent="b-copilot"))
        session.add(
            TurnUsage(
                id="usage-credits-copilot-2",
                run_id="run-credits-copilot-2",
                project_id="proj-test",
                agent="b-copilot",
                status="measured",
                runner="copilot",
                total_tokens=300,
                ai_nano_aiu=75_856_000,
                premium_requests=0.5,
                observed_at=now + timedelta(seconds=4),
            )
        )
        await session.commit()

    data = (await app.get("/api/v1/projects/proj-test/accounting", headers=auth_headers)).json()
    assert data["project"]["total_tokens"] == 1800
    assert data["project"]["ai_nano_aiu"] == 275856000
    assert data["project"]["premium_requests"] == 1.5
    assert data["budget"]["used_tokens"] == 1800

    assert [agent["agent"] for agent in data["agents"]] == ["a-claude", "b-copilot"]
    assert data["agents"][0]["ai_nano_aiu"] is None
    assert data["agents"][1]["ai_nano_aiu"] == 275856000

    # observed_at descending: copilot-2 (newest), copilot-1, claude (oldest).
    recent = data["recent_turns"][:3]
    assert [turn["total_tokens"] for turn in recent] == [300, 500, 1000]
    assert [turn["ai_nano_aiu"] for turn in recent] == [75856000, 200000000, None]

    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        assert project is not None
        project.token_budget = 1801
        await session.commit()

    async with async_session_factory() as session:
        state = await project_budget_state(session, "proj-test")
    assert state["exhausted"] is False
    assert state["used_tokens"] == 1800


@pytest.mark.asyncio
async def test_claude_only_project_has_null_credits_everywhere(app, auth_headers) -> None:
    """Task 1.11, first half: a project with no Copilot row reports the two new credit keys
    as null — in `project`, every `agents[]` entry and every `recent_turns[]` row — and its
    allowance `preferred_display` is unchanged except for the new `runner` key, carrying the
    allowance row's own runner ("claude"), not a hardcoded provider name."""
    await _seed_usage()

    data = (await app.get("/api/v1/projects/proj-test/accounting", headers=auth_headers)).json()

    assert data["project"]["ai_nano_aiu"] is None
    assert data["project"]["premium_requests"] is None
    for agent in data["agents"]:
        assert agent["ai_nano_aiu"] is None
        assert agent["premium_requests"] is None
    assert data["recent_turns"]
    for turn in data["recent_turns"]:
        assert turn["ai_nano_aiu"] is None
        assert turn["premium_requests"] is None

    assert data["preferred_display"] == {
        "kind": "allowance",
        "label": "Rate-limit allowance",
        "allowance": {"five_hour": {"remaining_percent": 64}},
        "runner": "claude",
    }


@pytest.mark.asyncio
async def test_newer_copilot_allowance_displaces_claude_with_its_own_runner_name(
    app, auth_headers
) -> None:
    """Task 1.11, second half: `preferred_display` picks the newest allowance row (R2) and
    names *that* row's runner — a newer Copilot reading displaces an older Claude one and
    carries `runner: "copilot"`, not the stale Claude name."""
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        session.add(Run(id="run-allowance-claude", project_id="proj-test", agent="claude"))
        session.add(
            TurnUsage(
                id="usage-allowance-claude",
                run_id="run-allowance-claude",
                project_id="proj-test",
                agent="claude",
                status="measured",
                runner="claude",
                total_tokens=10,
                allowance={"five_hour": {"remaining_percent": 90}},
                observed_at=now,
            )
        )
        session.add(Run(id="run-allowance-copilot", project_id="proj-test", agent="copilot"))
        session.add(
            TurnUsage(
                id="usage-allowance-copilot",
                run_id="run-allowance-copilot",
                project_id="proj-test",
                agent="copilot",
                status="measured",
                runner="copilot",
                total_tokens=20,
                ai_nano_aiu=1_000_000,
                premium_requests=0.1,
                allowance={"monthly": {"remaining_percent": 96}},
                observed_at=now + timedelta(seconds=5),
            )
        )
        await session.commit()

    data = (await app.get("/api/v1/projects/proj-test/accounting", headers=auth_headers)).json()
    assert data["preferred_display"] == {
        "kind": "allowance",
        "label": "Rate-limit allowance",
        "allowance": {"monthly": {"remaining_percent": 96}},
        "runner": "copilot",
    }


@pytest.mark.asyncio
async def test_conversation_accounting_sums_a_conversations_copilot_credits(
    app, auth_headers
) -> None:
    """Task 1.11, third half: `GET /accounting/conversations/{id}` is a real aggregate, not a
    slice of the project-wide recent window (see the 60-row test above) — and that aggregate
    now sums credits too, across every Copilot turn in the conversation."""
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        assert project is not None
        conversation = new_conversation(project_id=project.id, agent="copilot", origin="operator")
        conversation.id = conversation.lineage_id = "conv-credits"
        session.add(conversation)
        session.add(
            Run(
                id="run-conv-credits-1",
                project_id=project.id,
                agent="copilot",
                conversation_id="conv-credits",
            )
        )
        session.add(
            TurnUsage(
                id="usage-conv-credits-1",
                run_id="run-conv-credits-1",
                project_id=project.id,
                agent="copilot",
                status="measured",
                runner="copilot",
                total_tokens=50,
                ai_nano_aiu=200_000_000,
                premium_requests=1.0,
            )
        )
        session.add(
            Run(
                id="run-conv-credits-2",
                project_id=project.id,
                agent="copilot",
                conversation_id="conv-credits",
            )
        )
        session.add(
            TurnUsage(
                id="usage-conv-credits-2",
                run_id="run-conv-credits-2",
                project_id=project.id,
                agent="copilot",
                status="measured",
                runner="copilot",
                total_tokens=30,
                ai_nano_aiu=75_856_000,
                premium_requests=0.5,
            )
        )
        await session.commit()

    response = await app.get(
        "/api/v1/projects/proj-test/accounting/conversations/conv-credits", headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_tokens"] == 80
    assert body["ai_nano_aiu"] == 275856000
    assert body["premium_requests"] == 1.5


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
        # The route answers only for a conversation this project has (F239).
        conversation = new_conversation(project_id=project.id, agent="claude", origin="operator")
        conversation.id = conversation.lineage_id = "conv-many"
        session.add(conversation)
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
        "unpriced_turns": 60,
    }


@pytest.mark.asyncio
async def test_conversation_accounting_unknown_conversation_is_404_not_zero(
    app, auth_headers
) -> None:
    """Reversed by F239: a zero for a conversation that does not exist read as "this cost
    nothing", indistinguishable from a real, unmeasured conversation."""
    response = await app.get(
        "/api/v1/projects/proj-test/accounting/conversations/conv-nonexistent", headers=auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


@pytest.mark.asyncio
async def test_accounting_routes_require_auth(app) -> None:
    assert (await app.get("/api/v1/projects/proj-test/accounting")).status_code == 401
    assert (
        await app.patch("/api/v1/projects/proj-test/accounting/budget", json={"token_budget": 10})
    ).status_code == 401
    assert (
        await app.get("/api/v1/projects/proj-test/accounting/conversations/conv-many")
    ).status_code == 401
