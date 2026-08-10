"""The transition machine over HTTP — both routes, both transports, and the refusal shape.

The service tests drive `apply_transition` directly. These go through the API, which is what an
agent and the operator actually reach, and cover the parts only the wiring can get wrong: the right
actor arriving at the choke point, the refusal becoming the right status code, the SSE broadcast
firing only on a real change, and creation being narrowed on both transports.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run, TaskTransition

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"
TASKS = f"/api/v1/projects/{PROJECT}/tasks"
AGENT_TASKS = "/api/v1/agent-actions/tasks"


async def _active_run(run_id: str, agent: str = "worker") -> dict[str, str]:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id=PROJECT,
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _create(app, auth_headers, title="A task", status="pending"):
    response = await app.post(TASKS, json={"title": title, "status": status}, headers=auth_headers)
    return response


async def _patch(app, headers, task_id, status, *, agent_route=False):
    url = f"{AGENT_TASKS}/{task_id}" if agent_route else f"{TASKS}/{task_id}"
    return await app.patch(url, json={"status": status}, headers=headers)


# ---------------------------------------------------------------------------
# Creation is restricted to entry statuses, on both transports (D10)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["pending", "assigned"])
async def test_operator_may_create_a_task_at_an_entry_status(app, auth_headers, status):
    response = await _create(app, auth_headers, f"entry-{status}", status)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == status


@pytest.mark.parametrize("status", ["in_progress", "completed", "under_review", "approved"])
async def test_operator_cannot_create_a_task_past_the_entry_point(app, auth_headers, status):
    response = await _create(app, auth_headers, f"bad-{status}", status)
    assert response.status_code == 422, response.text


async def test_an_agent_cannot_create_an_already_approved_task(app, auth_headers):
    """The hole the 2026-08-10 scan found: `AgentTaskCreate.status` accepted any of the eight, so a
    run could reach `approved` by creating a task there and never transitioning at all."""
    headers = await _active_run("run-create-approved")
    response = await app.post(
        AGENT_TASKS, json={"title": "sneaky", "status": "approved"}, headers=headers
    )
    assert response.status_code == 422, response.text


async def test_the_two_transports_agree_on_what_create_accepts(app, auth_headers):
    """`agent-capability-plane` requires MCP be a thin adapter with the same operations. MCP's
    `create_task` exposes no `status` at all, so HTTP must not offer a wider door."""
    import inspect

    from hub import mcp_server

    # `@mcp.tool()` may or may not wrap the function depending on fastmcp's version, so reach the
    # underlying callable either way rather than pinning to one shape.
    create_task = getattr(mcp_server.create_task, "fn", mcp_server.create_task)
    signature = inspect.signature(create_task)
    assert "status" not in signature.parameters

    headers = await _active_run("run-parity")
    for status in ("completed", "approved"):
        response = await app.post(
            AGENT_TASKS, json={"title": f"parity-{status}", "status": status}, headers=headers
        )
        assert response.status_code == 422, f"HTTP accepted {status} where MCP cannot offer it"


# ---------------------------------------------------------------------------
# The operator route carries an operator actor
# ---------------------------------------------------------------------------


async def test_the_operator_walks_the_lifecycle_and_the_history_names_them(app, auth_headers):
    task_id = (await _create(app, auth_headers, "operator lifecycle")).json()["id"]

    for status in ("in_progress", "completed", "under_review", "approved"):
        response = await _patch(app, auth_headers, task_id, status)
        assert response.status_code == 200, f"{status}: {response.text}"

    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(TaskTransition)
                    .where(TaskTransition.task_id == task_id)
                    .order_by(TaskTransition.sequence)
                )
            )
            .scalars()
            .all()
        )
    assert [(r.from_status, r.to_status) for r in rows] == [
        ("pending", "in_progress"),
        ("in_progress", "completed"),
        ("completed", "under_review"),
        ("under_review", "approved"),
    ]
    assert {r.actor_kind for r in rows} == {"operator"}
    assert {r.run_id for r in rows} == {None}


async def test_an_illegal_operator_move_is_a_409_naming_what_is_reachable(app, auth_headers):
    task_id = (await _create(app, auth_headers, "illegal operator move")).json()["id"]
    response = await _patch(app, auth_headers, task_id, "approved")

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "pending" in detail
    assert "in_progress" in detail


async def test_the_operator_may_reject_before_review_and_reopen_afterwards(app, auth_headers):
    """D9's operator-only edges, over the route the status control will use."""
    rejected_id = (await _create(app, auth_headers, "obsolete")).json()["id"]
    assert (await _patch(app, auth_headers, rejected_id, "rejected")).status_code == 200
    assert (await _patch(app, auth_headers, rejected_id, "pending")).status_code == 200

    approved_id = (await _create(app, auth_headers, "reopen me")).json()["id"]
    for status in ("in_progress", "completed", "under_review", "approved"):
        assert (await _patch(app, auth_headers, approved_id, status)).status_code == 200
    assert (await _patch(app, auth_headers, approved_id, "revision_needed")).status_code == 200


# ---------------------------------------------------------------------------
# The agent route carries a run actor
# ---------------------------------------------------------------------------


async def test_an_agent_cannot_skip_review_over_http(app, auth_headers):
    task_id = (await _create(app, auth_headers, "no skipping")).json()["id"]
    headers = await _active_run("run-skip")
    assert (await _patch(app, headers, task_id, "in_progress", agent_route=True)).status_code == 200

    response = await _patch(app, headers, task_id, "approved", agent_route=True)
    assert response.status_code == 409, response.text


async def test_an_agent_cannot_approve_its_own_completion_over_http(app, auth_headers):
    task_id = (await _create(app, auth_headers, "self approval")).json()["id"]
    headers = await _active_run("run-author")

    for status in ("in_progress", "completed", "under_review"):
        assert (
            await _patch(app, headers, task_id, status, agent_route=True)
        ).status_code == 200, status

    response = await _patch(app, headers, task_id, "approved", agent_route=True)
    assert response.status_code == 403, response.text
    assert "different actor" in response.json()["detail"]

    # And a *new run of the same agent* is still refused — the defect live use found on
    # 2026-08-10, when a run-based check let an agent approve on its next turn.
    next_turn = await _active_run("run-author-turn-2", agent="worker")
    refused = await _patch(app, next_turn, task_id, "approved", agent_route=True)
    assert refused.status_code == 403, refused.text

    # A genuinely different agent is entitled to it.
    reviewer = await _active_run("run-reviewer", agent="reviewer")
    assert (await _patch(app, reviewer, task_id, "approved", agent_route=True)).status_code == 200


async def test_an_agent_cannot_reject_work_before_review(app, auth_headers):
    """Abandoning work is the operator's call; at `under_review` rejection is a review outcome."""
    task_id = (await _create(app, auth_headers, "agent reject")).json()["id"]
    headers = await _active_run("run-rejecter")
    assert (await _patch(app, headers, task_id, "in_progress", agent_route=True)).status_code == 200

    response = await _patch(app, headers, task_id, "rejected", agent_route=True)
    assert response.status_code == 409, response.text


# ---------------------------------------------------------------------------
# A refusal leaves nothing behind (4.5)
# ---------------------------------------------------------------------------


async def test_a_refusal_broadcasts_nothing_and_records_nothing(app, auth_headers, monkeypatch):
    task_id = (await _create(app, auth_headers, "no broadcast")).json()["id"]

    events = []

    from hub import sse

    original = sse.sse_manager.broadcast

    async def _spy(project_id, event, payload):
        events.append((event, payload))
        return await original(project_id, event, payload)

    monkeypatch.setattr(sse.sse_manager, "broadcast", _spy)

    refused = await _patch(app, auth_headers, task_id, "approved")
    assert refused.status_code == 409
    assert events == []

    accepted = await _patch(app, auth_headers, task_id, "in_progress")
    assert accepted.status_code == 200
    assert ("task_updated", {"id": task_id, "status": "in_progress"}) in events


async def test_restating_the_current_status_succeeds_and_records_nothing(app, auth_headers):
    task_id = (await _create(app, auth_headers, "noop")).json()["id"]
    response = await _patch(app, auth_headers, task_id, "pending")
    assert response.status_code == 200

    async with async_session_factory() as session:
        rows = (
            (await session.execute(select(TaskTransition).where(TaskTransition.task_id == task_id)))
            .scalars()
            .all()
        )
    assert rows == []


# ---------------------------------------------------------------------------
# The actor-scoped map the control reads (D13)
# ---------------------------------------------------------------------------


async def test_the_allowed_transitions_endpoint_serves_the_operator_view(app, auth_headers):
    response = await app.get(f"{TASKS}/transitions/allowed", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["actor_kind"] == "operator"
    transitions = body["transitions"]
    assert set(transitions) == {
        "pending",
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "revision_needed",
        "approved",
        "rejected",
    }
    # The operator-only edges must be visible, or the control cannot offer them.
    assert transitions["approved"] == ["revision_needed"]
    assert transitions["rejected"] == ["pending"]
    assert "rejected" in transitions["in_progress"]


async def test_every_move_the_endpoint_offers_is_actually_accepted(app, auth_headers):
    """The contract that makes D13 worth having: the control never offers a move that then fails."""
    response = await app.get(f"{TASKS}/transitions/allowed", headers=auth_headers)
    transitions = response.json()["transitions"]

    for from_status, targets in transitions.items():
        for to_status in targets:
            create = await _create(app, auth_headers, f"{from_status}->{to_status}")
            task_id = create.json()["id"]
            # Walk the task to `from_status` the legal way, then take the offered edge.
            async with async_session_factory() as session:
                from hub.db.models import Task

                task = await session.get(Task, task_id)
                task.status = from_status
                await session.commit()

            result = await _patch(app, auth_headers, task_id, to_status)
            assert result.status_code == 200, f"{from_status} -> {to_status}: {result.text}"
