"""Every Hub timestamp column must come back timezone-aware, not just timezone-typed.

SQLite has no timezone storage. A `DateTime(timezone=True)` column round-trips a value written
aware as **naive** once it has actually gone through the DBAPI — the column type declares intent,
SQLite silently drops it. Left uncorrected, a naive value crosses the API with no offset, and
`hub/ui/src/lib/hubTime.ts` used to compensate for exactly that on the read side. This is the
server-side fix: `hub.db.models.UTCDateTime` relabels a naive result as UTC in one place, at the
ORM boundary, so nothing downstream — a Pydantic response schema, a raw `.isoformat()` call — ever
sees a naive value that actually came from the database.
"""

from datetime import timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Project


@pytest.mark.asyncio
async def test_orm_datetime_columns_round_trip_as_timezone_aware(app) -> None:
    async with async_session_factory() as session:
        session.add(Project(id="proj-tz-roundtrip", name="TZ Roundtrip Test"))
        await session.commit()

    # A fresh session forces a real read from SQLite rather than returning the
    # in-memory object still held by the identity map.
    async with async_session_factory() as session:
        refetched = await session.get(Project, "proj-tz-roundtrip")
        assert refetched is not None
        assert refetched.created_at.tzinfo is not None
        assert refetched.created_at.utcoffset() == timezone.utc.utcoffset(None)


@pytest.mark.asyncio
async def test_runner_response_timestamps_carry_a_utc_offset(app, auth_headers) -> None:
    # The bootstrap project's runners are seeded by init_db() before this test runs, so the
    # GET below reads created_at/updated_at back out of SQLite for real — the exact path that
    # used to lose the offset.
    resp = await app.get("/api/v1/projects/proj-test/runners", headers=auth_headers)
    assert resp.status_code == 200
    runners = resp.json()
    assert runners, "expected the seeded default runners"
    for runner in runners:
        for field in ("created_at", "updated_at"):
            value = runner[field]
            assert value.endswith("Z") or "+" in value.split("T", 1)[1], (
                f"{field}={value!r} has no UTC offset — a client parsing this as a bare "
                "date-time will read it as local time"
            )
