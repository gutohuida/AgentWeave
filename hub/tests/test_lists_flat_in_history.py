"""The agent and conversation lists read each newest row, not the history behind it.

`the-app-stays-responsive-while-agents-run`, task lists-flat (FR-5, FR-7). GET /agents and both
conversation lists used to load every `context_warning` row the project had ever recorded and group
every output row by session, only to use the newest of each. On the operator's database that made
`/agents` cost 80-220ms, and 1.8s at ten times its history.

Two things are pinned here:

* The answers are the ones the full-history reads gave. The reference below *is* the pre-change
  algorithm — every row, newest first, through `usable_context_reading` — run on a fixture with
  many readings, several sessions and both of the rule's fallback cases.
* No statement those routes issue reads `event_logs` or `agent_outputs` except through the indexes
  of migration 0144. Each statement a request sends is captured and put back to SQLite as
  `EXPLAIN QUERY PLAN`; the old reads plan as a search of `ix_event_logs_event_type` or
  `ix_agent_outputs_project_agent`, which visit every row of that type or agent.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest
from sqlalchemy import event, select

from hub.context_readings import usable_context_reading
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory, engine
from hub.db.models import AgentOutput, EventLog
from hub.utils import short_id

PROJECT = "proj-test"
T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


async def _sync_agents(app, auth_headers, *names):
    response = await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {name: {"runner": "manual"} for name in names}}},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


def _reading(percent, session_id, conversation_id, minute) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "status": "measured",
        "source": "test",
        "percent": percent,
        "context_tokens": None if percent is None else int(percent * 1000),
        "limit_tokens": 100_000,
        "observed_at": 1_786_800_000.0 + minute,
        "conversation_id": conversation_id,
    }
    if session_id is not None:
        data["session_id"] = session_id
    return data


async def _build_history() -> Dict[str, List[str]]:
    """Three agents, five conversations, a few hundred readings and outputs.

    * `reader`'s two conversations each end on a reading with no percentage, so the newest row
      hides the measured one behind it in the same session — the fallback the rule exists for.
    * `lagging` ends on a reading with no percentage whose session never measured anything, while
      an older session did: the rule must not reach across sessions.
    * `plain` ends on a reading with no session at all.
    * Outputs span several sessions per agent, the newest output naming no session.
    """
    conversations: Dict[str, List[str]] = {}
    minute = 0
    async with async_session_factory() as db:

        def reading(agent, data):
            nonlocal minute
            minute += 1
            db.add(
                EventLog(
                    id=f"evt-{short_id()}",
                    project_id=PROJECT,
                    event_type="context_warning",
                    agent=agent,
                    severity="info",
                    data=data,
                    timestamp=T0 + timedelta(minutes=minute),
                )
            )

        def output(agent, conversation_id, session_id):
            nonlocal minute
            minute += 1
            db.add(
                AgentOutput(
                    id=f"out-{short_id()}",
                    project_id=PROJECT,
                    agent=agent,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    content="line",
                    timestamp=T0 + timedelta(minutes=minute),
                )
            )

        for agent, count in (("reader", 2), ("lagging", 2), ("plain", 1)):
            conversations[agent] = []
            for _ in range(count):
                conversation = new_conversation(project_id=PROJECT, agent=agent, origin="operator")
                conversation.title = "Thread"
                db.add(conversation)
                conversations[agent].append(conversation.id)
        await db.flush()

        reader_a, reader_b = conversations["reader"]
        for i in range(60):
            reading("reader", _reading(10 + i * 0.1, "s-a", reader_a, minute))
            output("reader", reader_a, "s-a")
        reading("reader", _reading(None, "s-a", reader_a, minute))
        for i in range(60):
            reading("reader", _reading(30 + i * 0.1, "s-b", reader_b, minute))
            output("reader", reader_b, "s-b")
        reading("reader", _reading(None, "s-b", reader_b, minute))
        output("reader", reader_b, None)

        lag_old, lag_new = conversations["lagging"]
        for i in range(40):
            reading("lagging", _reading(50 + i * 0.1, "s-old", lag_old, minute))
            output("lagging", lag_old, "s-old")
        for _ in range(5):
            reading("lagging", _reading(None, "s-new", lag_new, minute))
            output("lagging", lag_new, "s-new")

        (plain,) = conversations["plain"]
        for i in range(20):
            reading("plain", _reading(70 + i * 0.1, "s-p", plain, minute))
        reading("plain", _reading(None, None, plain, minute))
        await db.commit()
    return conversations


async def _reference() -> Dict[str, Dict[str, Any]]:
    """What the pre-change routes computed: every row, newest first, grouped in Python."""
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(EventLog)
                    .where(EventLog.project_id == PROJECT, EventLog.event_type == "context_warning")
                    .order_by(EventLog.timestamp.desc())
                )
            )
            .scalars()
            .all()
        )
        outputs = (
            await db.execute(
                select(AgentOutput.agent, AgentOutput.session_id, AgentOutput.timestamp).where(
                    AgentOutput.project_id == PROJECT
                )
            )
        ).all()
    by_agent: Dict[str, List[Any]] = {}
    by_conversation: Dict[str, List[Any]] = {}
    for row in rows:
        by_agent.setdefault(row.agent, []).append(row.data)
        if isinstance(row.data, dict) and row.data.get("conversation_id"):
            by_conversation.setdefault(row.data["conversation_id"], []).append(row.data)
    sessions: Dict[tuple, List[datetime]] = {}
    last_output: Dict[str, datetime] = {}
    for agent, session_id, timestamp in outputs:
        last_output[agent] = max(last_output.get(agent, timestamp), timestamp)
        if session_id is not None:
            sessions.setdefault((agent, session_id), []).append(timestamp)
    started: Dict[str, datetime] = {}
    newest_session_end: Dict[str, datetime] = {}
    for (agent, _session_id), stamps in sessions.items():
        if agent not in newest_session_end or max(stamps) > newest_session_end[agent]:
            newest_session_end[agent] = max(stamps)
            started[agent] = min(stamps)
    return {
        "agent_context": {a: usable_context_reading(r) for a, r in by_agent.items()},
        "conversation_context": {c: usable_context_reading(r) for c, r in by_conversation.items()},
        "session_started_at": started,
        "last_seen": last_output,
    }


def _same_instant(body_value, expected: datetime) -> bool:
    observed = datetime.fromisoformat(body_value.replace("Z", "+00:00"))
    return observed == expected


@pytest.mark.asyncio
async def test_lists_answer_what_the_full_history_answered(app, auth_headers):
    await _sync_agents(app, auth_headers, "reader", "lagging", "plain")
    conversations = await _build_history()
    expected = await _reference()

    # The fixture reaches both of the rule's fallback cases, or this would prove little.
    assert expected["agent_context"]["reader"]["percent"] == pytest.approx(35.9)
    assert expected["agent_context"]["lagging"]["percent"] is None
    assert expected["agent_context"]["plain"]["percent"] is None

    agents = await app.get(f"/api/v1/projects/{PROJECT}/agents", headers=auth_headers)
    assert agents.status_code == 200, agents.text
    summaries = {row["name"]: row for row in agents.json()}
    for name in ("reader", "lagging", "plain"):
        assert summaries[name]["context_usage"] == expected["agent_context"][name], name
        for field in ("session_started_at", "last_seen"):
            want = expected[field].get(name)
            if want is None:
                assert summaries[name][field] is None, (name, field)
            else:
                assert _same_instant(summaries[name][field], want), (name, field)

    everything = await app.get(f"/api/v1/projects/{PROJECT}/conversations", headers=auth_headers)
    assert everything.status_code == 200, everything.text
    listed = {}
    for agent in conversations:
        response = await app.get(
            f"/api/v1/projects/{PROJECT}/agent/{agent}/conversations", headers=auth_headers
        )
        assert response.status_code == 200, response.text
        listed.update({row["id"]: row for row in response.json()})
    project_wide = everything.json()
    project_rows = project_wide["conversations"] if isinstance(project_wide, dict) else project_wide
    for row in project_rows:
        listed.setdefault(row["id"], row)
        assert row["context_usage"] == expected["conversation_context"].get(row["id"]), row["id"]
    for ids in conversations.values():
        for conversation_id in ids:
            assert listed[conversation_id]["context_usage"] == expected["conversation_context"].get(
                conversation_id
            ), conversation_id


#: The indexes of migration 0144. A plan step on `event_logs` or `agent_outputs` through any other
#: access path visits rows in proportion to the history, which is what FR-5 forbids.
_FLAT_INDEXES = (
    "ix_event_logs_context_agent_ts",
    "ix_event_logs_context_conversation_ts",
    "ix_event_logs_context_session_ts",
    "ix_agent_outputs_project_agent_ts",
    "ix_agent_outputs_project_agent_session_ts",
)


@pytest.mark.asyncio
async def test_no_list_statement_reads_history_outside_the_flat_indexes(app, auth_headers):
    await _sync_agents(app, auth_headers, "reader", "lagging", "plain")
    await _build_history()

    statements: List[tuple] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append((statement, parameters))

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        for url in (
            f"/api/v1/projects/{PROJECT}/agents",
            f"/api/v1/projects/{PROJECT}/conversations",
            f"/api/v1/projects/{PROJECT}/agent/reader/conversations",
            f"/api/v1/projects/{PROJECT}/agent/lagging/conversations",
            f"/api/v1/projects/{PROJECT}/agent/plain/conversations",
        ):
            response = await app.get(url, headers=auth_headers)
            assert response.status_code == 200, response.text
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)

    reads_history = [s for s in statements if "event_logs" in s[0] or "agent_outputs" in s[0]]
    assert reads_history, "the routes no longer read readings or outputs at all?"

    offending = []
    async with engine.connect() as conn:
        for statement, parameters in reads_history:
            plan = (
                await conn.exec_driver_sql("EXPLAIN QUERY PLAN " + statement, tuple(parameters))
            ).all()
            for step in plan:
                detail = step[-1]
                touches = " event_logs" in detail or " agent_outputs" in detail
                if touches and not any(index in detail for index in _FLAT_INDEXES):
                    offending.append((detail, statement.split("\n")[0][:120]))
    assert not offending, offending
