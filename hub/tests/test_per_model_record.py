"""FR-14 of `every-task-comes-with-a-recommended-builder-and-checker`: the per-model record.

Tasks built under two models, one agent rebound from one to the other between tasks, some
send-backs and an unpriced turn -- read through the agent route the `read_model_record` tool calls.
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub import mcp_server
from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Run, Task, TaskTransition, TurnUsage

from .test_spec_archive import run_headers  # noqa: F401

P = "proj-test"
ROUTE = "/api/v1/agent-actions/model-record"
T0 = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
OPUS, SONNET = "claude-opus-5-5", "claude-sonnet-5-5"


def _at(minutes):
    return T0 + timedelta(minutes=minutes)


def _task(task_id, status="approved"):
    return Task(id=task_id, project_id=P, title=task_id, status=status, created_at=_at(0))


def _run(run_id, task, minute, model, micros, agent="dev", usage=True):
    rows = [
        Run(
            id=run_id,
            project_id=P,
            agent=agent,
            task_id=task,
            status="completed",
            started_at=_at(minute),
        )
    ]
    if usage:
        rows.append(
            TurnUsage(
                id=f"use-{run_id}",
                run_id=run_id,
                project_id=P,
                agent=agent,
                status="measured",
                model=model,
                total_tokens=10,
                input_tokens=9,
                output_tokens=1,
                api_equivalent_usd_micros=micros,
            )
        )
    return rows


def _send_back(move_id, task, reason_class):
    return TaskTransition(
        id=move_id,
        project_id=P,
        task_id=task,
        from_status="under_review",
        to_status="revision_needed",
        actor_kind="operator",
        reason_class=reason_class,
        created_at=_at(50),
    )


async def _seed(*rows):
    async with async_session_factory() as session:
        session.add_all(rows)
        await session.commit()


@pytest.mark.asyncio
async def test_each_task_counts_under_the_model_that_ran_it(app, run_headers):  # noqa: F811
    await _seed(
        _task("t-a"),
        _task("t-b"),
        _task("t-c", status="under_review"),
        _task("t-d"),
    )
    await _seed(
        # "dev" runs t-a under Opus, is rebound to Sonnet, then runs t-b and t-c under Sonnet
        *_run("r-a", "t-a", 1, OPUS, 4000),
        *_run("r-b", "t-b", 10, SONNET, 1000),
        *_run("r-b2", "t-b", 11, SONNET, 500),
        *_run("r-c", "t-c", 20, SONNET, None),  # a priced-less turn
        *_run("r-d", "t-d", 30, None, None, usage=False),  # no usage row at all
    )
    await _seed(
        _send_back("m1", "t-a", "defect"),
        _send_back("m2", "t-b", "defect"),
        _send_back("m3", "t-b", "flaky"),
        _send_back("m4", "t-c", None),
    )

    response = await app.get(ROUTE, headers=run_headers)
    assert response.status_code == 200, response.text
    record = {row["model"]: row for row in response.json()["models"]}

    assert set(record) == {OPUS, SONNET, "unknown"}
    assert record[OPUS]["tasks_built"] == 1
    assert record[OPUS]["cost_usd_micros"] == 4000
    assert record[OPUS]["send_backs"]["defect"] == 1
    assert record[OPUS]["send_backs"]["total"] == 1

    sonnet = record[SONNET]
    assert sonnet["tasks_built"] == 2
    assert [t["task_id"] for t in sonnet["tasks"]] == ["t-b", "t-c"]
    assert sonnet["tasks_approved"] == 1
    assert sonnet["turns"] == 3
    assert sonnet["priced_turns"] == 2
    assert sonnet["unpriced_turns"] == 1
    assert sonnet["cost_usd_micros"] == 1500  # the unpriced turn adds nothing and is not hidden
    assert sonnet["send_backs"]["defect"] == 1
    assert sonnet["send_backs"]["flaky"] == 1
    assert sonnet["send_backs"]["unclassified"] == 1
    assert sonnet["send_backs"]["total"] == 3

    assert record["unknown"]["tasks_built"] == 1
    assert record["unknown"]["unpriced_turns"] == 1

    sample = response.json()["sample"]
    assert sample["tasks_built"] == sum(r["tasks_built"] for r in record.values()) == 4
    assert sample["turns"] == 5
    assert sample["unpriced_turns"] == 2


@pytest.mark.asyncio
async def test_a_review_turn_is_not_a_build_turn(app, run_headers):  # noqa: F811
    """Real review runs carry Run.task_id; only the delivered queue entry marks them."""
    await _seed(_task("t-x"))
    await _seed(
        *_run("r-build1", "t-x", 1, SONNET, 1000, agent="dev"),
        *_run("r-build2", "t-x", 2, SONNET, 2000, agent="dev"),
        # the checker's turn, later and under another model, shaped as the runtime binds it
        *_run("r-review", "t-x", 60, OPUS, 9000, agent="qa"),
        *_run("r-live", "t-x", 61, None, None, agent="dev", usage=False),
    )
    await _seed(
        InboundQueueEntry(
            id="q-review",
            project_id=P,
            agent="qa",
            origin_type="operator",
            content="review it",
            hop_depth=0,
            state="delivered",
            task_id="t-x",
            review_task_id="t-x",
            delivered_in_run_id="r-review",
        ),
        _send_back("m-x", "t-x", "defect"),
    )
    live = await _live_run("r-live")

    response = await app.get(ROUTE, headers=run_headers)
    record = {row["model"]: row for row in response.json()["models"]}

    assert set(record) == {SONNET}, "the reviewer's model must not appear as a builder"
    assert record[SONNET]["tasks_built"] == 1
    assert record[SONNET]["turns"] == 2
    assert record[SONNET]["cost_usd_micros"] == 3000
    assert record[SONNET]["send_backs"]["defect"] == 1
    assert record[SONNET]["running_turns"] == 1
    assert record[SONNET]["unpriced_turns"] == 0
    assert live


async def _live_run(run_id):
    from sqlalchemy import update

    async with async_session_factory() as session:
        await session.execute(update(Run).where(Run.id == run_id).values(status="running"))
        await session.commit()
    return True


@pytest.mark.asyncio
async def test_a_project_with_no_work_reads_empty(app, run_headers):  # noqa: F811
    response = await app.get(ROUTE, headers=run_headers)
    assert response.status_code == 200
    assert response.json()["models"] == []
    assert response.json()["sample"]["tasks_built"] == 0


def test_the_tool_is_registered_and_reads_the_route(monkeypatch):
    seen = []
    monkeypatch.setattr(
        mcp_server, "_hub_request", lambda method, path, *a, **k: seen.append((method, path)) or {}
    )
    mcp_server.read_model_record()
    assert seen == [("GET", "/model-record")]
    assert "read_model_record" in mcp_server._CALLABLE_TOOLS
