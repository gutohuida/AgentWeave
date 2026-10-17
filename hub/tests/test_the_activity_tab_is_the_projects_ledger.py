"""The project's ledger (slice project-ledger): `GET /projects/{id}/ledger`.

The Activity tab renders the lanes in the order this route returns them, so these tests pin it:
merges, divergences and messages newest first, spend by day oldest first.
"""

from datetime import datetime, timedelta, timezone

from hub.db.engine import async_session_factory
from hub.db.models import (
    EventLog,
    Message,
    Run,
    RunDivergence,
    Task,
    TaskIntegration,
    TurnUsage,
    WorkerInvocation,
)

LEDGER = "/api/v1/projects/proj-test/ledger"
T0 = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)


async def seed():
    async with async_session_factory() as session:
        session.add_all(
            [
                Task(id="task-a", project_id="proj-test", title="Watch", spec_document_id=None),
                Task(id="task-b", project_id="proj-test", title="Tags", created_by_run_id="run-a"),
                Run(
                    id="run-a",
                    project_id="proj-test",
                    agent="builder",
                    status="completed",
                    turn_depth=0,
                    task_id="task-a",
                ),
                Run(
                    id="run-b",
                    project_id="proj-test",
                    agent="tester",
                    status="completed",
                    turn_depth=0,
                    task_id="task-b",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                TaskIntegration(
                    id="tin-old",
                    project_id="proj-test",
                    task_id="task-a",
                    outcome="merged",
                    commit_sha="aaa",
                    target_branch="main",
                    actor_kind="operator",
                    created_at=T0,
                ),
                TaskIntegration(
                    id="tin-new",
                    project_id="proj-test",
                    task_id="task-b",
                    outcome="skipped",
                    reason="already integrated",
                    actor_kind="operator",
                    created_at=T0 + timedelta(days=1),
                ),
                TurnUsage(
                    id="tu-1",
                    run_id="run-a",
                    project_id="proj-test",
                    agent="builder",
                    status="measured",
                    total_tokens=1000,
                    api_equivalent_usd_micros=2_000_000,
                    observed_at=T0,
                ),
                TurnUsage(
                    id="tu-2",
                    run_id="run-b",
                    project_id="proj-test",
                    agent="tester",
                    status="measured",
                    total_tokens=500,
                    api_equivalent_usd_micros=500_000,
                    observed_at=T0 + timedelta(days=1),
                ),
                WorkerInvocation(
                    id="wi-1",
                    project_id="proj-test",
                    kind="title",
                    prompt_version="v1",
                    cli="claude",
                    outcome="ok",
                    cost_usd_micros=100_000,
                    total_tokens=50,
                    created_at=T0,
                ),
                RunDivergence(
                    id="rdv-1",
                    project_id="proj-test",
                    run_id="run-a",
                    agent="builder",
                    task_id="task-a",
                    task_status_at_end="in_progress",
                    run_exit_status="completed",
                    policy_applied="surface",
                    outcome="surfaced",
                    created_at=T0,
                ),
                Message(
                    id="msg-agents",
                    project_id="proj-test",
                    sender="builder",
                    recipient="tester",
                    content="ready for you",
                    timestamp=T0,
                ),
                Message(
                    id="msg-op",
                    project_id="proj-test",
                    sender="user",
                    recipient="builder",
                    content="hi",
                    timestamp=T0,
                ),
                *[
                    EventLog(
                        id=f"ev-cw-{i}",
                        project_id="proj-test",
                        event_type="context_warning",
                        agent="builder",
                        severity="warn",
                        timestamp=T0 + timedelta(minutes=i),
                    )
                    for i in range(3)
                ],
            ]
        )
        await session.commit()


async def test_the_ledger_lanes_and_their_order(app, auth_headers):
    await seed()
    response = await app.get(LEDGER, headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert [m["id"] for m in body["merges"]] == ["tin-new", "tin-old"]
    assert body["merges"][1]["task_title"] == "Watch"
    assert body["totals"]["merged"] == 1 and body["totals"]["integrations"] == 2

    spend = body["spend"]
    assert spend["total_usd"] == 2.6
    assert spend["worker_usd"] == 0.1
    assert [d["day"] for d in spend["by_day"]] == ["2026-10-15", "2026-10-16"]
    assert [d["usd"] for d in spend["by_day"]] == [2.1, 0.5]
    assert [(a["agent"], a["usd"]) for a in spend["by_agent"]] == [
        ("builder", 2.0),
        ("tester", 0.5),
    ]
    assert [(t["task_id"], t["usd"]) for t in spend["by_task"]] == [
        ("task-a", 2.0),
        ("task-b", 0.5),
    ]

    assert [d["id"] for d in body["divergences"]] == ["rdv-1"]
    assert [m["id"] for m in body["messages"]] == ["msg-agents"], "operator messages are not lanes"
    assert body["origins"] == {"spec": 0, "loop": 0, "agent": 1, "operator": 1}
    [notice] = body["notices"]
    assert notice["kind"] == "context_warning" and notice["count"] == 3
    assert notice["by_agent"] == [{"agent": "builder", "count": 3}]


async def test_an_empty_project_has_an_empty_ledger(app, auth_headers):
    body = (await app.get(LEDGER, headers=auth_headers)).json()
    assert body["merges"] == [] and body["notices"] == []
    assert body["spend"]["total_usd"] == 0 and body["spend"]["by_day"] == []
