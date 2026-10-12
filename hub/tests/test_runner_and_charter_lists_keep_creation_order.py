"""F177: the runner and charter lists keep creation order when two rows share a `created_at`.

Both lists ordered by `created_at` alone. Windows' timer ticks about every 15.6 ms, so two
consecutive creates can carry one timestamp, and SQLite then returned the tied rows in index
(name) order. `rowid` is the tiebreaker: it is assigned in insert order.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import update

from hub.db.engine import async_session_factory
from hub.db.models import Charter, Runner

TICK = datetime(2026, 10, 12, 1, 0, 0, tzinfo=timezone.utc)


async def _create(app, auth_headers, collection, body):
    response = await app.post(
        f"/api/v1/projects/proj-test/{collection}", json=body, headers=auth_headers
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _listed_names(app, auth_headers, collection, ids):
    response = await app.get(f"/api/v1/projects/proj-test/{collection}", headers=auth_headers)
    assert response.status_code == 200
    return [row["name"] for row in response.json() if row["id"] in ids]


@pytest.mark.asyncio
async def test_runners_created_within_one_tick_list_in_creation_order(app, auth_headers):
    first = await _create(app, auth_headers, "runners", {"name": "ZB", "cli": "claude"})
    second = await _create(app, auth_headers, "runners", {"name": "ZA", "cli": "claude"})
    async with async_session_factory() as session:
        await session.execute(
            update(Runner).where(Runner.id.in_([first, second])).values(created_at=TICK)
        )
        await session.commit()

    assert await _listed_names(app, auth_headers, "runners", {first, second}) == ["ZB", "ZA"]


@pytest.mark.asyncio
async def test_charters_created_within_one_tick_list_in_creation_order(app, auth_headers):
    first = await _create(app, auth_headers, "charters", {"name": "ZB", "content": "b"})
    second = await _create(app, auth_headers, "charters", {"name": "ZA", "content": "a"})
    async with async_session_factory() as session:
        await session.execute(
            update(Charter).where(Charter.id.in_([first, second])).values(created_at=TICK)
        )
        await session.commit()

    assert await _listed_names(app, auth_headers, "charters", {first, second}) == ["ZB", "ZA"]
