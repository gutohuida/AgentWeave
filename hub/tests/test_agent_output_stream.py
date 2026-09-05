"""Structured AgentOutput persistence, projection, and ordering tests."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import AgentOutput
from hub.sse import sse_manager


async def _project_id(app, auth_headers) -> str:
    response = await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)
    assert response.status_code == 200
    return response.json()["project_id"]


async def _add_output(
    project_id: str,
    *,
    output_id: str,
    agent: str,
    content: str,
    timestamp: datetime,
    sequence: int | None = None,
) -> None:
    async with async_session_factory() as session:
        session.add(
            AgentOutput(
                id=output_id,
                project_id=project_id,
                agent=agent,
                content=content,
                timestamp=timestamp,
                run_id="run-ordering" if sequence is not None else None,
                sequence=sequence,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_structured_output_round_trip_and_legacy_row(app, auth_headers):
    agent = "stream-roundtrip"
    structured = {
        "content": "Running tests",
        "session_id": "sess-stream",
        "kind": "tool_use",
        "payload": {
            "version": 1,
            "call_id": "call-1",
            "tool_name": "pytest",
            "summary": "Running tests",
        },
        "run_id": "run-1",
        "sequence": 2,
    }
    response = await app.post(
        f"/api/v1/projects/proj-test/agents/{agent}/output",
        json=structured,
        headers=auth_headers,
    )
    assert response.status_code == 201

    legacy_response = await app.post(
        f"/api/v1/projects/proj-test/agents/{agent}/output",
        json={"content": "legacy text", "session_id": "sess-stream"},
        headers=auth_headers,
    )
    assert legacy_response.status_code == 201

    response = await app.get(
        f"/api/v1/projects/proj-test/agents/{agent}/output", headers=auth_headers
    )
    assert response.status_code == 200
    rows = response.json()
    structured_row = next(row for row in rows if row["content"] == "Running tests")
    assert structured_row["kind"] == structured["kind"]
    assert structured_row["payload"] == structured["payload"]
    assert structured_row["run_id"] == structured["run_id"]
    assert structured_row["sequence"] == structured["sequence"]

    legacy_row = next(row for row in rows if row["content"] == "legacy text")
    assert legacy_row["kind"] is None
    assert legacy_row["payload"] is None
    assert legacy_row["run_id"] is None
    assert legacy_row["sequence"] is None


@pytest.mark.asyncio
async def test_output_ingress_rejects_unknown_kind_and_oversized_payload(app, auth_headers):
    unknown_kind = await app.post(
        "/api/v1/projects/proj-test/agents/stream-reject/output",
        json={
            "content": "bad kind",
            "kind": "progress",
            "payload": {"version": 1},
        },
        headers=auth_headers,
    )
    assert unknown_kind.status_code == 422

    oversized = await app.post(
        "/api/v1/projects/proj-test/agents/stream-reject/output",
        json={
            "content": "large payload",
            "kind": "diagnostic",
            "payload": {"version": 1, "message": "x" * (64 * 1024)},
        },
        headers=auth_headers,
    )
    assert oversized.status_code == 422
    assert "65536" in oversized.text


@pytest.mark.asyncio
async def test_structured_output_is_carried_by_sse(app, auth_headers):
    project_id = await _project_id(app, auth_headers)
    queue = sse_manager.subscribe(project_id)
    try:
        response = await app.post(
            "/api/v1/projects/proj-test/agents/stream-sse/output",
            json={
                "content": "Thinking",
                "kind": "thinking",
                "payload": {"version": 1, "text": "Thinking"},
                "run_id": "run-sse",
                "sequence": 4,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        event = queue.get_nowait()
        assert event.event == "agent_output"
        data = json.loads(event.data)
        assert data["kind"] == "thinking"
        assert data["payload"] == {"version": 1, "text": "Thinking"}
        assert data["run_id"] == "run-sse"
        assert data["sequence"] == 4
    finally:
        sse_manager.unsubscribe(project_id, queue)


@pytest.mark.asyncio
async def test_chat_history_preserves_structured_output_fields(app, auth_headers):
    response = await app.post(
        "/api/v1/projects/proj-test/agents/stream-chat/output",
        json={
            "content": "Done",
            "session_id": "sess-chat-stream",
            "kind": "status",
            "payload": {"version": 1, "phase": "completed"},
            "run_id": "run-chat",
            "sequence": 7,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201

    conversations = await app.get(
        "/api/v1/projects/proj-test/agent/stream-chat/conversations", headers=auth_headers
    )
    conversation_id = conversations.json()[0]["id"]
    response = await app.get(
        f"/api/v1/projects/proj-test/agent/stream-chat/chat/{conversation_id}", headers=auth_headers
    )
    assert response.status_code == 200
    message = next(item for item in response.json()["entries"] if item["kind"] == "agent_output")
    assert message["output_kind"] == "status"
    assert message["payload"] == {"version": 1, "phase": "completed"}
    assert message["run_id"] == "run-chat"
    assert message["sequence"] == 7


@pytest.mark.asyncio
async def test_default_output_query_returns_newest_window_chronologically(app, auth_headers):
    project_id = await _project_id(app, auth_headers)
    agent = "stream-window"
    base = datetime.now(timezone.utc) - timedelta(hours=1)
    rows = [
        ("window-1", base, 1),
        ("window-2", base + timedelta(seconds=1), 1),
        ("window-3a", base + timedelta(seconds=2), 1),
        ("window-3b", base + timedelta(seconds=2), 2),
        ("window-4", base + timedelta(seconds=3), 1),
    ]
    for output_id, timestamp, sequence in rows:
        await _add_output(
            project_id,
            output_id=output_id,
            agent=agent,
            content=output_id,
            timestamp=timestamp,
            sequence=sequence,
        )

    response = await app.get(
        f"/api/v1/projects/proj-test/agents/{agent}/output?limit=3",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == ["window-3a", "window-3b", "window-4"]


@pytest.mark.asyncio
async def test_content_bound_matches_the_cli_stream_contract(app, auth_headers):
    """The CLI truncates stream content to 64 KiB, so the Hub must accept it.

    `text` and `thinking` are the only kinds not already bounded to 8 KiB; a
    lower Hub bound silently 422s them and drops the output line.
    """
    from agentweave.stream_events import (
        MAX_PAYLOAD_BYTES,
        stream_event_transport_fields,
        text_event,
    )

    event = text_event("The quick brown fox jumps over the lazy dog. " * 500)
    event.sequence = 1
    fields = stream_event_transport_fields(event)
    assert len(fields["content"]) > 10000

    accepted = await app.post(
        "/api/v1/projects/proj-test/agents/stream-bounds/output",
        json={
            "content": fields["content"],
            "kind": fields["kind"],
            "payload": fields["payload"],
            "sequence": fields["sequence"],
        },
        headers=auth_headers,
    )
    assert accepted.status_code == 201

    over_contract = await app.post(
        "/api/v1/projects/proj-test/agents/stream-bounds/output",
        json={"content": "x" * (MAX_PAYLOAD_BYTES + 1), "kind": "text"},
        headers=auth_headers,
    )
    assert over_contract.status_code == 422


@pytest.mark.asyncio
async def test_a_recorded_row_carries_its_timestamp_without_a_refresh(app, auth_headers):
    """F287 removed `await db.refresh(row)` from the end of `record_agent_output`.

    The only attribute the function reads that its caller did not set is `row.timestamp`, and
    the SSE broadcast calls `.isoformat()` on it — so if the refresh had been what populated it,
    deleting the refresh would raise `AttributeError: 'NoneType' has no attribute 'isoformat'`
    on every output line. It is not: `AgentOutput.timestamp` is `default=_now`, a Python-side
    default applied at flush, and `expire_on_commit=False` leaves it in place across the commit.

    This test fails if that column ever becomes server-side, which is the change that would make
    the refresh load-bearing again.
    """
    from datetime import timezone as _tz

    from hub.output_recording import record_agent_output

    project_id = await _project_id(app, auth_headers)
    queue = sse_manager.subscribe(project_id)
    try:
        async with async_session_factory() as session:
            row = await record_agent_output(
                session,
                project_id,
                "no-refresh",
                content="one line",
                session_id="sess-no-refresh",
                kind="text",
                payload=None,
                run_id="run-no-refresh",
                sequence=1,
            )
            # Populated on the instance the caller gets back, not merely in the database.
            assert row.timestamp is not None
            assert isinstance(row.timestamp, datetime)
            assert row.timestamp.tzinfo is not None
            in_memory = row.timestamp

        # And identical to what was persisted — a refresh's only possible contribution would have
        # been to correct a divergence, so there must not be one.
        async with async_session_factory() as verify:
            stored = await verify.get(AgentOutput, row.id)
            assert stored is not None
            assert stored.timestamp.astimezone(_tz.utc) == in_memory.astimezone(_tz.utc)

        # The broadcast that reads it went out with the same value.
        event = queue.get_nowait()
        assert event.event == "agent_output"
        assert json.loads(event.data)["timestamp"] == in_memory.isoformat()
    finally:
        sse_manager.unsubscribe(project_id, queue)


@pytest.mark.asyncio
async def test_recording_an_output_row_issues_no_select_of_the_row_it_just_wrote(app, auth_headers):
    """The cost F287 is about: one extra `SELECT ... WHERE id = ?` per streamed line.

    Every agent output on both runners funnels through `record_agent_output`, so a redundant
    primary-key read here is paid once per line of every turn. This pins that no statement issued
    after the INSERT reads `agent_outputs` back — restoring `await db.refresh(row)` fails it.
    """
    from sqlalchemy import event as sa_event

    from hub.db.engine import engine
    from hub.output_recording import record_agent_output

    project_id = await _project_id(app, auth_headers)
    statements: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.split()))

    sa_event.listen(engine.sync_engine, "before_cursor_execute", _capture)
    try:
        async with async_session_factory() as session:
            await record_agent_output(
                session,
                project_id,
                "no-extra-select",
                content="one line",
                session_id="sess-no-extra-select",
                kind="text",
                payload=None,
                run_id="run-no-extra-select",
                sequence=1,
            )
    finally:
        sa_event.remove(engine.sync_engine, "before_cursor_execute", _capture)

    inserts = [i for i, s in enumerate(statements) if s.startswith("INSERT INTO agent_outputs")]
    assert len(inserts) == 1, statements
    after_insert = statements[inserts[0] + 1 :]
    reads_back = [
        s
        for s in after_insert
        if s.startswith("SELECT") and "FROM agent_outputs" in s and "agent_outputs.id = ?" in s
    ]
    assert reads_back == [], reads_back
