"""Tests for `reachable-by-a-human` section 1: severity normalisation.

`persist_event` (`hub/hub/utils.py`) must map any out-of-vocabulary `severity` string to `"warn"`
before writing the row, so a call site (or an external `POST /logs` caller) cannot introduce a
spelling the operator's views (`EventRow.tsx`'s `SEVERITY_CHIP`, `ActivityLog.tsx`'s
`SEVERITY_FILTERS`) do not recognise. The enumerated set is `{"info", "warn", "error", "debug"}`.
"""

import json

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import EventLog
from hub.sse import sse_manager
from hub.utils import persist_event


@pytest.mark.asyncio
async def test_persist_event_normalises_unknown_severity(app):
    """1.1: an out-of-vocabulary severity (the historical `"warning"` spelling, and a made-up one)
    is written to the row as `"warn"`, not passed through unchanged."""
    async with async_session_factory() as db:
        for bad_spelling in ("warning", "critical"):
            await persist_event(
                db,
                "proj-test",
                "severity_normalisation_test",
                {"spelling": bad_spelling},
                severity=bad_spelling,
            )

        rows = (
            (
                await db.execute(
                    select(EventLog).where(EventLog.event_type == "severity_normalisation_test")
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 2
    assert {row.severity for row in rows} == {"warn"}


@pytest.mark.asyncio
async def test_persist_event_passes_through_enumerated_severities(app):
    """1.2: each of the enumerated set's own members is written unchanged, not remapped."""
    enumerated = ("info", "warn", "error", "debug")
    async with async_session_factory() as db:
        for value in enumerated:
            await persist_event(
                db,
                "proj-test",
                "severity_passthrough_test",
                {"value": value},
                severity=value,
            )

        rows = (
            (
                await db.execute(
                    select(EventLog).where(EventLog.event_type == "severity_passthrough_test")
                )
            )
            .scalars()
            .all()
        )
    written = {row.data["value"]: row.severity for row in rows}
    assert written == {value: value for value in enumerated}


@pytest.mark.asyncio
async def test_push_log_normalises_persisted_severity(app, auth_headers):
    """1.5: `POST /logs` with an out-of-vocabulary severity persists the normalised value."""
    resp = await app.post(
        "/api/v1/projects/proj-test/logs",
        json={"event_type": "push_log_severity_test", "severity": "critical"},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    async with async_session_factory() as db:
        row = (
            await db.execute(
                select(EventLog).where(EventLog.event_type == "push_log_severity_test")
            )
        ).scalar_one()
    assert row.severity == "warn"


@pytest.mark.asyncio
async def test_push_log_broadcast_carries_normalised_severity(app, auth_headers):
    """1.6 (found in Q1-R2): the SSE broadcast `push_log` sends must carry the same normalised
    severity as the persisted row, not the raw request body's spelling — `logs.py`'s broadcast
    dict is built independently of the write and would otherwise still ship the raw value to a
    live subscriber."""
    queue = sse_manager.subscribe("proj-test")
    try:
        resp = await app.post(
            "/api/v1/projects/proj-test/logs",
            json={"event_type": "push_log_broadcast_severity_test", "severity": "critical"},
            headers=auth_headers,
        )
        assert resp.status_code == 201

        event = await queue.get()
        while event.event != "log_event":
            event = await queue.get()
        payload = json.loads(event.data)
    finally:
        sse_manager.unsubscribe("proj-test", queue)

    assert payload["severity"] == "warn"
