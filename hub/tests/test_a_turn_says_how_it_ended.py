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
from unittest.mock import MagicMock, patch

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import EventLog, Run

# Phase 2 drives real runs through both spawn paths, and the fakes that make that possible already
# exist. Imported rather than re-declared, as `test_agent_default_permission_mode.py` does.
from tests.test_agent_trigger import (
    _await_background_run,
    _bind_codex_app_server_runner,
    _fake_pty,
    _fake_run_turn,
    _stoppable_pty,
    _wait_for_active_pty,
)

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


# ---------------------------------------------------------------------------
# Phase 2 — the terminal status line is persisted
#
# Design D6, re-argued in round RA and scoped by round RB. Both spawn paths broadcast
# `{"phase": "completed", "exit_code": N}` when a run ends and persist nothing, so once the live
# SSE stream is gone the exit code is unrecoverable and `lastRunSettled` has no fast signal for a
# run that did not finish.
#
# The row that satisfies `isSuccessCompletionEntry` today is written by a *different* producer —
# `runner_parsing.py:356`, reached only for `runner in ("claude", "claude_proxy", "native")`
# (`agent_trigger.py:1867`). `status_event("completed")` occurs exactly once in the whole Hub. So
# these tests are runner-scoped on purpose: a completed run on a Claude runner already has such a
# row and proves nothing, a completed Codex run has never had one, and a stopped or failed run has
# never had one on either runner. `interrupted` is deliberately absent — `reconcile_interrupted_runs`
# writes an `EventLog` row and no `AgentOutput`, because no Hub process was alive to write one.
# ---------------------------------------------------------------------------


async def _output_rows(app, auth_headers, agent: str, run_id: str) -> list:
    """Every `AgentOutput` row the run produced, read back through the route the client uses."""
    response = await app.get(f"{BASE}/agents/{agent}/output?limit=1000", headers=auth_headers)
    assert response.status_code == 200, response.text
    return [row for row in response.json() if row["run_id"] == run_id]


def _completion_rows(rows: list) -> list:
    """The Python mirror of `isSuccessCompletionEntry` (`agentTimelineModel.ts:24-28`).

    Restated rather than imported because it lives in TypeScript; the client-side half of the
    predicate is asserted in `agentTimelineModel.test.ts`, including that codex's own
    `phase="plan"` status row does **not** match it.
    """
    return [
        row
        for row in rows
        if row["kind"] == "status" and (row["payload"] or {}).get("phase") == "completed"
    ]


async def _run_row(run_id: str) -> Run:
    async with async_session_factory() as db:
        return await db.get(Run, run_id)


@pytest.mark.asyncio
async def test_a_stopped_run_persists_its_terminal_status_line(app, auth_headers, bind_runner):
    """*A run's terminal status line is persisted* — the process path, stopped.

    The case no runner covers today: the process is killed before Claude emits its `result`
    line, so nothing writes a `phase="completed"` row and the exit code exists only in the
    broadcast.
    """
    agent = "phase2-stopped"
    await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {agent: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner(agent, cli="claude")

    fake_session = _stoppable_pty()
    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=fake_session)
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            trigger = await app.post(
                f"{BASE}/agent/trigger",
                json={"agent": agent, "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            run_id = trigger.json()["run_id"]
            await _wait_for_active_pty(run_id)
            stop = await app.post(f"{BASE}/agent/{agent}/stop", headers=auth_headers)
            assert stop.status_code == 200
            await _await_background_run()

    assert (await _run_row(run_id)).status == "stopped"
    settled = _completion_rows(await _output_rows(app, auth_headers, agent, run_id))
    assert len(settled) == 1, "a stopped run's terminal status line is persisted exactly once"
    assert settled[0]["content"] == "Run stopped (exit 15)."
    assert settled[0]["payload"]["exit_code"] == 15, "the exit code outlives the live stream"


@pytest.mark.asyncio
async def test_a_failed_run_persists_its_terminal_status_line(app, auth_headers, bind_runner):
    """*A run's terminal status line is persisted* — the process path, failed.

    A non-zero exit takes Claude's `result` line down the `is_error` branch
    (`runner_parsing.py:346-350`), which is an `error_event` with `kind="error"` — never a
    `status` row. So this run, too, has never had a settled signal.
    """
    agent = "phase2-failed"
    await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {agent: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner(agent, cli="claude")

    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"error","is_error":true,"session_id":"sess-p2-fail"}\n'],
        exit_code=1,
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            trigger = await app.post(
                f"{BASE}/agent/trigger",
                json={"agent": agent, "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            run_id = trigger.json()["run_id"]
            # A failed run hands its input back and retries to the cap; every attempt is a
            # separate run, and the assertions below name this one.
            await _await_background_run()

    assert (await _run_row(run_id)).status == "failed"
    rows = await _output_rows(app, auth_headers, agent, run_id)
    assert [r for r in rows if r["kind"] == "error"], "the error line is still its own row"
    settled = _completion_rows(rows)
    assert len(settled) == 1, "a failed run's terminal status line is persisted exactly once"
    assert settled[0]["content"] == "Run failed (exit 1)."
    assert settled[0]["payload"]["exit_code"] == 1


@pytest.mark.asyncio
async def test_an_app_server_run_that_was_stopped_persists_its_terminal_status_line(
    app, auth_headers
):
    """*A run's terminal status line is persisted* — the app-server path, stopped.

    `TurnOutcome.status == "interrupted"` is this transport's deliberate stop and maps to
    `stopped` (`agent_trigger.py:2628`). It is not the `interrupted` **run status**, which only
    `run_reconciliation.py:65` ever assigns and which this change cannot reach.
    """
    agent = "phase2-appserver-stopped"
    await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {agent: {"runner": "codex"}}}},
        headers=auth_headers,
    )
    await _bind_codex_app_server_runner(app, auth_headers)(agent)

    fake_run_turn = _fake_run_turn(thread_id="thread-p2-stop", status="interrupted")
    with patch("hub.api.v1.agent_trigger.codex_run_turn", fake_run_turn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
            trigger = await app.post(
                f"{BASE}/agent/trigger",
                json={"agent": agent, "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            run_id = trigger.json()["run_id"]
            await _await_background_run()

    assert (await _run_row(run_id)).status == "stopped"
    settled = _completion_rows(await _output_rows(app, auth_headers, agent, run_id))
    assert len(settled) == 1
    assert settled[0]["content"] == "Run stopped (exit 1)."
    assert settled[0]["payload"]["exit_code"] == 1


@pytest.mark.asyncio
async def test_an_app_server_run_that_failed_persists_its_terminal_status_line(app, auth_headers):
    """*A run's terminal status line is persisted* — the app-server path, failed."""
    agent = "phase2-appserver-failed"
    await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {agent: {"runner": "codex"}}}},
        headers=auth_headers,
    )
    await _bind_codex_app_server_runner(app, auth_headers)(agent)

    fake_run_turn = _fake_run_turn(
        thread_id="thread-p2-fail", status="failed", error="the runtime went away"
    )
    with patch("hub.api.v1.agent_trigger.codex_run_turn", fake_run_turn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
            trigger = await app.post(
                f"{BASE}/agent/trigger",
                json={"agent": agent, "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            run_id = trigger.json()["run_id"]
            await _await_background_run()

    assert (await _run_row(run_id)).status == "failed"
    settled = _completion_rows(await _output_rows(app, auth_headers, agent, run_id))
    assert len(settled) == 1
    assert settled[0]["content"] == "Run failed (exit 1)."
    assert settled[0]["payload"]["exit_code"] == 1


@pytest.mark.asyncio
async def test_a_completed_claude_run_carries_the_pair_and_only_one_holds_the_exit_code(
    app, auth_headers, bind_runner
):
    """*A run's terminal status line is persisted* — the duplication, stated so it is not removed.

    A completed run on a **Claude** runner ends with two entries satisfying
    `isSuccessCompletionEntry`: the stream parser's (`content="Completed"`, payload carrying
    `version`/`phase`/`summary`) and the finalize block's (`content="Run completed (exit 0)."`,
    payload carrying `phase`/`exit_code`). `AgentTimeline.tsx:430` returns `null` for each, so
    nothing is drawn twice — asserted on the client in `agentTimeline.test.tsx`.

    Do not "de-duplicate" this pair. Removing the parser's row deletes the only signal that works
    today; removing the finalize block's for a completed run makes the durable exit code
    outcome-dependent. The runner binding is explicit because the pair exists only where
    `parse_claude_line` runs (round RB).
    """
    agent = "phase2-completed-claude"
    await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {agent: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner(agent, cli="claude")

    fake_spawn = _fake_pty(
        [
            '{"type":"system","subtype":"init","session_id":"sess-p2-ok"}\n',
            '{"type":"assistant","message":{"content":[{"type":"text","text":"done"}]},'
            '"session_id":"sess-p2-ok"}\n',
            '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-p2-ok"}\n',
        ]
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            trigger = await app.post(
                f"{BASE}/agent/trigger",
                json={"agent": agent, "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            run_id = trigger.json()["run_id"]
            await _await_background_run()

    assert (await _run_row(run_id)).status == "completed"
    settled = _completion_rows(await _output_rows(app, auth_headers, agent, run_id))
    assert len(settled) == 2, "the parser's row and the finalize block's, both matching"

    parser_row = next(r for r in settled if r["content"] == "Completed")
    assert parser_row["payload"]["summary"] == "Completed"
    assert "exit_code" not in parser_row["payload"], "the parser knows no exit code"

    finalize_row = next(r for r in settled if r["content"] == "Run completed (exit 0).")
    assert finalize_row["payload"]["exit_code"] == 0, "the exit code lives on this one alone"


@pytest.mark.asyncio
async def test_a_completed_codex_run_gains_its_first_settled_signal(app, auth_headers):
    """*It does not depend on the runner announcing its own completion* — the Codex case.

    `parse_claude_line` is selected only for the three Claude-family runner values, and neither
    Codex transport emits a completion sentinel: `parse_codex_line`'s only `status_event` is
    `"plan"` (`runner_parsing.py:574`) and the app-server's only one is `"plan"`
    (`codex_appserver.py:544`). So a Codex run has never had a persisted `phase="completed"` row
    for **any** outcome, a clean completion included, and this change gives it its first — not a
    second. F270.
    """
    from hub.runner_events import status_event

    agent = "phase2-completed-codex"
    await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {agent: {"runner": "codex"}}}},
        headers=auth_headers,
    )
    await _bind_codex_app_server_runner(app, auth_headers)(agent)

    plan = status_event("plan", summary="read the file; change it")
    fake_run_turn = _fake_run_turn(thread_id="thread-p2-codex", status="completed", events=(plan,))
    with patch("hub.api.v1.agent_trigger.codex_run_turn", fake_run_turn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/codex"):
            trigger = await app.post(
                f"{BASE}/agent/trigger",
                json={"agent": agent, "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            run_id = trigger.json()["run_id"]
            await _await_background_run()

    assert (await _run_row(run_id)).status == "completed"
    rows = await _output_rows(app, auth_headers, agent, run_id)

    # The turn's own status row is the plan, and it is not a completion — the client-side half of
    # this claim is `agentTimelineModel.test.ts`'s "leaves a non-terminal status phase alone".
    plan_rows = [r for r in rows if r["kind"] == "status" and r["payload"]["phase"] == "plan"]
    assert len(plan_rows) == 1
    assert plan_rows[0] not in _completion_rows(rows)

    settled = _completion_rows(rows)
    assert len(settled) == 1, "exactly one, and it is the finalize block's — codex writes no other"
    assert settled[0]["content"] == "Run completed (exit 0)."
    assert settled[0]["payload"]["exit_code"] == 0
