"""The timeline route carries each run's own facts (`a-turn-says-how-it-ended`, phase 1).

Phase 0 observed the defect live on 2026-09-01: a run the operator stopped had `stopped` in its
`Run` row, and the timeline route said `started` — because the client reconstructed the outcome
from event *names* in an array the route returns newest-first, and the reducer it used kept the
last value it saw. The route never carried the fact it already had.

These tests are written against the route, not the client: the response is an envelope of the
events and a map of run facts keyed by `run_id`, and the map is obtained by looking those ids up
rather than by any query whose coverage depends on an ordering or a limit.
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import EventLog, Run

PROJECT = "proj-test"
BASE = f"/api/v1/projects/{PROJECT}"
AGENT = "alice"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _sync_agent(app, auth_headers, name: str = AGENT) -> None:
    response = await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {name: {"runner": "manual"}}}},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def _add(*rows) -> None:
    async with async_session_factory() as session:
        for row in rows:
            session.add(row)
        await session.commit()


def _run(run_id: str, *, status: str, started_at: datetime, **kwargs) -> Run:
    return Run(
        id=run_id,
        project_id=PROJECT,
        agent=AGENT,
        status=status,
        started_at=started_at,
        **kwargs,
    )


def _event(event_id: str, *, event_type: str, timestamp: datetime, data: dict) -> EventLog:
    return EventLog(
        id=event_id,
        project_id=PROJECT,
        event_type=event_type,
        agent=AGENT,
        timestamp=timestamp,
        data=data,
    )


async def _timeline(app, auth_headers) -> dict:
    response = await app.get(f"{BASE}/agents/{AGENT}/timeline", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_response_carries_events_and_a_keyed_map_of_run_facts(app, auth_headers):
    """*The timeline carries each run's own facts* — "The response carries both halves"."""
    await _sync_agent(app, auth_headers)
    started = _now() - timedelta(minutes=5)
    ended = started + timedelta(seconds=42)
    await _add(
        _run(
            "run-facts",
            status="stopped",
            started_at=started,
            ended_at=ended,
            exit_code=143,
        ),
        _event(
            "evt-facts",
            event_type="run_stopped",
            timestamp=ended,
            data={"run_id": "run-facts"},
        ),
    )

    body = await _timeline(app, auth_headers)

    assert isinstance(body, dict), "the response is an envelope, not a bare array"
    assert {"events", "runs"} <= set(body)
    assert [e["id"] for e in body["events"]] == ["evt-facts"]

    facts = body["runs"]["run-facts"]
    assert facts["status"] == "stopped"
    assert facts["exit_code"] == 143
    assert datetime.fromisoformat(facts["started_at"]) == started
    assert datetime.fromisoformat(facts["ended_at"]) == ended


@pytest.mark.asyncio
async def test_a_run_still_executing_reports_started(app, auth_headers):
    """Design D5 — `Run.status` `running` is renamed to the client's `started` at the boundary."""
    await _sync_agent(app, auth_headers)
    started = _now() - timedelta(seconds=10)
    await _add(
        _run("run-live", status="running", started_at=started),
        _event(
            "evt-live",
            event_type="run_started",
            timestamp=started,
            data={"run_id": "run-live"},
        ),
    )

    body = await _timeline(app, auth_headers)

    facts = body["runs"]["run-live"]
    assert facts["status"] == "started"
    assert facts["exit_code"] is None
    assert facts["ended_at"] is None


@pytest.mark.asyncio
async def test_facts_come_from_the_run_row_not_from_the_events(app, auth_headers):
    """*The facts come from the run, not from the events*.

    The run's lifecycle event says it completed; the row was corrected to `stopped` afterwards.
    This is the shape phase 0 measured live — the database said `stopped`, the route said
    `started` — so the assertion is on the row winning, not merely on a field being present.
    """
    await _sync_agent(app, auth_headers)
    started = _now() - timedelta(minutes=3)
    await _add(
        _run(
            "run-corrected",
            status="stopped",
            started_at=started,
            ended_at=started + timedelta(seconds=5),
            exit_code=143,
        ),
        _event(
            "evt-corrected",
            event_type="run_completed",
            timestamp=started + timedelta(seconds=5),
            data={"run_id": "run-corrected", "exit_code": 0},
        ),
    )

    body = await _timeline(app, auth_headers)

    assert body["runs"]["run-corrected"]["status"] == "stopped"
    assert body["runs"]["run-corrected"]["exit_code"] == 143


@pytest.mark.asyncio
async def test_an_event_naming_an_unknown_run_leaves_the_key_absent(app, auth_headers):
    """*An unknown run degrades rather than fails* — no row, no key, no error."""
    await _sync_agent(app, auth_headers)
    when = _now() - timedelta(minutes=1)
    await _add(
        _event(
            "evt-ghost",
            event_type="run_completed",
            timestamp=when,
            data={"run_id": "run-that-has-no-row"},
        ),
    )

    body = await _timeline(app, auth_headers)

    assert [e["id"] for e in body["events"]] == ["evt-ghost"]
    assert "run-that-has-no-row" not in body["runs"]
    assert body["runs"] == {}


@pytest.mark.asyncio
async def test_the_map_carries_no_run_the_events_do_not_name(app, auth_headers):
    """*The map is scoped to the events*.

    The agent owns 60 runs, each named by exactly one event. Only the newest 50 events come back,
    so the map must hold exactly those 50 runs — the ten whose events fell outside the window are
    absent even though they belong to this agent in this project.
    """
    await _sync_agent(app, auth_headers)
    base = _now() - timedelta(hours=2)
    rows = []
    for index in range(60):
        run_id = f"run-window-{index:02d}"
        moment = base + timedelta(minutes=index)
        rows.append(_run(run_id, status="completed", started_at=moment, ended_at=moment))
        rows.append(
            _event(
                f"evt-window-{index:02d}",
                event_type="run_completed",
                timestamp=moment,
                data={"run_id": run_id},
            )
        )
    await _add(*rows)

    body = await _timeline(app, auth_headers)

    named = {e["data"]["run_id"] for e in body["events"]}
    assert len(body["events"]) == 50
    assert set(body["runs"]) == named
    for index in range(10):
        assert f"run-window-{index:02d}" not in body["runs"]


@pytest.mark.asyncio
async def test_an_old_run_named_by_a_recent_event_keeps_its_outcome(app, auth_headers):
    """*An old run named by a recent event keeps its outcome* (task 1.4b).

    `run_reconciliation.reconcile_interrupted_runs` sweeps every still-`running` row at Hub start
    and writes its `run_interrupted` event *then* — phase 0 measured the gap live on 2026-09-01:
    a `run_interrupted` row at 22:24:01 against a `Run.started_at` of 22:22:13, a distance equal
    to the outage and to nothing about the run. So an agent's newest event routinely names its
    oldest run.

    This test exists to reject a `Run` query ordered by `started_at` desc and limited: the
    interrupted run started before all 60 others, and its event is the newest of them all.
    """
    await _sync_agent(app, auth_headers)
    restart = _now()
    ancient = restart - timedelta(days=9)
    rows = [
        _run("run-ancient", status="interrupted", started_at=ancient, ended_at=restart),
        # The reconciliation shape: an old run, its lifecycle event stamped at restart time.
        _event(
            "evt-ancient",
            event_type="run_interrupted",
            timestamp=restart,
            data={"run_id": "run-ancient"},
        ),
    ]
    for index in range(60):
        run_id = f"run-recent-{index:02d}"
        moment = restart - timedelta(minutes=60 - index)
        rows.append(_run(run_id, status="completed", started_at=moment, ended_at=moment))
        rows.append(
            _event(
                f"evt-recent-{index:02d}",
                event_type="run_completed",
                timestamp=moment,
                data={"run_id": run_id},
            )
        )
    await _add(*rows)

    body = await _timeline(app, auth_headers)

    assert body["events"][0]["id"] == "evt-ancient", "the ancient run's event is the newest"
    assert "run-ancient" in body["runs"], (
        "the run that started first is named by the newest event; a start-time ranking with a "
        "limit misses exactly this run"
    )
    assert body["runs"]["run-ancient"]["status"] == "interrupted"

    # And coverage is total, not merely inclusive of the awkward case.
    named = {e["data"]["run_id"] for e in body["events"] if "run_id" in (e["data"] or {})}
    assert named <= set(body["runs"])
