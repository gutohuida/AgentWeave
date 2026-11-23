"""POST /overview/visit, the operator's visit record (`overview-at-a-glance-with-dashboard-and-
briefing-tabs`, task visits-and-note): the Hub half of ac-last-visit-none, and algorithm
'record-visit' -- a visit within 30 minutes of the last keeps 'since you last looked' where it was,
and GET /overview never moves it.

The visit clock is set back by writing the row, as the acceptance drive does."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import OverviewVisit, Task, TaskIntegration

from .conftest import TEST_PROJECT_ID

P = TEST_PROJECT_ID
URL = f"/api/v1/projects/{P}/overview"


async def _visit(app, auth_headers) -> Dict[str, Any]:
    response = await app.post(f"{URL}/visit", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _read(app, auth_headers) -> Dict[str, Any]:
    response = await app.get(URL, headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _set_back(**delta: float) -> datetime:
    """Move the stored last visit back by *delta*, as if it happened that long ago."""
    async with async_session_factory() as db:
        row = await db.get(OverviewVisit, P)
        row.last_visit_at = row.last_visit_at - timedelta(**delta)
        moved = row.last_visit_at
        await db.commit()
    return moved if moved.tzinfo else moved.replace(tzinfo=timezone.utc)


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value)


@pytest.mark.asyncio
async def test_a_project_never_visited_has_no_record_and_a_second_visit_counts_from_the_first(
    app, auth_headers
):
    """ac-last-visit-none (Hub half)."""
    before = await _read(app, auth_headers)
    assert before["visit"] is None

    first = await _visit(app, auth_headers)
    assert first["previous_at"] is None
    assert first["note_started"] is False
    read = await _read(app, auth_headers)
    assert read["visit"] == {"previous_at": None, "last_at": first["current_at"]}

    first_at = await _set_back(hours=2)
    second = await _visit(app, auth_headers)
    assert _at(second["previous_at"]) == first_at
    assert (await _read(app, auth_headers))["visit"]["previous_at"] == second["previous_at"]


@pytest.mark.asyncio
async def test_a_visit_within_30_minutes_keeps_the_previous_visit(app, auth_headers):
    await _visit(app, auth_headers)
    first_at = await _set_back(hours=3)
    second = await _visit(app, auth_headers)
    assert _at(second["previous_at"]) == first_at

    # Switching away and back 10 minutes later is the same visit: previous stays put.
    await _set_back(minutes=10)
    third = await _visit(app, auth_headers)
    assert third["previous_at"] == second["previous_at"]
    read = await _read(app, auth_headers)
    assert read["visit"]["previous_at"] == second["previous_at"]
    assert read["visit"]["last_at"] == third["current_at"]


@pytest.mark.asyncio
async def test_reading_the_overview_never_moves_the_visit(app, auth_headers):
    first = await _visit(app, auth_headers)
    for _ in range(3):
        assert (await _read(app, auth_headers))["visit"]["last_at"] == first["current_at"]


@pytest.mark.asyncio
async def test_finished_counts_from_the_previous_visit_when_it_is_before_today(app, auth_headers):
    """'Since you last looked' counts what finished after the visit before the current one: a task
    landed two days ago, after a visit three days ago, is listed although it is not today's."""
    await _visit(app, auth_headers)
    await _set_back(days=3)
    async with async_session_factory() as db:
        db.add(Task(id="t-old", project_id=P, title="Landed two days ago", status="approved"))
        await db.flush()
        db.add(
            TaskIntegration(
                id="tint-old",
                project_id=P,
                task_id="t-old",
                outcome="merged",
                actor_kind="operator",
                created_at=datetime.now(timezone.utc) - timedelta(days=2),
            )
        )
        await db.commit()
    assert "t-old" not in {f["task_id"] for f in (await _read(app, auth_headers))["finished"]}
    await _visit(app, auth_headers)
    assert "t-old" in {f["task_id"] for f in (await _read(app, auth_headers))["finished"]}
