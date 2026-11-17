"""The 'Landing time and flaky tests' dashboard every project has (`landing-time-and-test-
flakiness-are-measured`, FR-8).

An ordinary saved dashboard (`Dashboard`): its panels are queries over the dashboard query's
project-scoped views, so the operator can edit or delete it like any other, and it needs no UI of
its own. A new project is given it when it is created (`seed`); a project that existed before is
given it by migration 0181, which carries its own copy of these panels as they were then.

A batch from before its landing record (FR-7) has NULL in each field it did not record, and every
panel shows that as 'not recorded' or leaves the batch out, never as 0.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .check_history import TEN_FLAKIEST_SQL
from .db.models import Dashboard
from .utils import short_id

NAME = "Landing time and flaky tests"
DESCRIPTION = (
    "How long approved work waits and is checked before it lands, and which tests flake. "
    "Wait is from the earliest task ready to land until the batch's checks held a slot; check "
    "time is from then until its last check run ended. A batch from before these were recorded "
    "shows 'not recorded'."
)
#: Who a seeded dashboard reads as saved by.
AUTHOR = "hub"

#: Minutes between two stored timestamps.
_MINUTES = "round((julianday({end}) - julianday({start})) * 1440, 1)"
_WAIT = _MINUTES.format(start="ready_at", end="slot_at")
_CHECK_TIME = _MINUTES.format(start="slot_at", end="checks_ended_at")

BATCHES_SQL = f"""select id as batch,
       created_at as formed_at,
       case when ready_at is null or slot_at is null then 'not recorded'
            else {_WAIT} end as "wait (min)",
       case when slot_at is null or checks_ended_at is null then 'not recorded'
            else {_CHECK_TIME} end as "check time (min)",
       coalesce(check_runs, 'not recorded') as "check runs",
       state as outcome
from landing_batches
order by created_at desc
limit 50"""

MEDIAN_SQL = f"""with recent as (
  select {_CHECK_TIME} as minutes
  from landing_batches
  where slot_at is not null and checks_ended_at is not null
  order by created_at desc
  limit 20
), ordered as (
  select minutes, row_number() over (order by minutes) as r, count(*) over () as n from recent
)
select round(avg(minutes), 1) as "median check time (min)"
from ordered
where r in ((n + 1) / 2, (n + 2) / 2)"""

OVER_TIME_SQL = f"""select created_at as formed_at, {_CHECK_TIME} as "check time (min)"
from landing_batches
where slot_at is not null and checks_ended_at is not null
order by created_at asc"""

PANELS: List[Dict[str, str]] = [
    {"title": "Landing batches, newest first", "query": BATCHES_SQL, "kind": "table"},
    {
        "title": "Median landing check time, last 20 batches (min)",
        "query": MEDIAN_SQL,
        "kind": "number",
    },
    {"title": "Landing check time over time (min)", "query": OVER_TIME_SQL, "kind": "line"},
    {"title": "Ten flakiest tests", "query": TEN_FLAKIEST_SQL, "kind": "table"},
]


def panels() -> List[Dict[str, Any]]:
    """The panels as a new dashboard stores them, each with its own id."""
    return [{"id": f"pnl-{short_id()}", **panel} for panel in PANELS]


async def seed(session: AsyncSession, project_id: str) -> None:
    """Give *project_id* the dashboard, unless it already has one of that name. Not committed."""
    taken = await session.scalar(
        select(Dashboard.id).where(Dashboard.project_id == project_id, Dashboard.name == NAME)
    )
    if taken is not None:
        return
    now = datetime.now(timezone.utc)
    session.add(
        Dashboard(
            id=f"dash-{short_id()}",
            project_id=project_id,
            name=NAME,
            description=DESCRIPTION,
            panels=panels(),
            author=AUTHOR,
            created_at=now,
            updated_at=now,
            version=1,
        )
    )
