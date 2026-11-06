"""Flaky tests the approval checks found, raised to the operator.

The check gate re-runs a failure once before it counts against the task (`project_checks.
confirm_failure`); a failure that passes the second time is recorded on the run's result as
`flaky`, approval goes on, and the test goes on the project's known-failing list as flaky with its
owner fix task (`known_failing`, `failures-already-known-are-on-a-list-not-re-argued` FR-2, FR-5).
That list is where a flake is kept, and the Overview shows it (`GET /checks/known-failing`,
FR-11); nothing is reconstructed from old check runs or the event log (FR-12). What this module
still writes is one `event_logs` row per flake (`FLAKY_EVENT`, so the Logs show when a test
flaked).

`FIX_TASK_EVENT` rows are what the Hub wrote when it filed a fix task, before the list and since
(`known_failing._file_fix_task`); `fix_tasks_by_test` reads them, so a test an open fix task already
names is never filed for twice.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.engine import async_session_factory
from .db.models import EventLog, Task, TaskCheckRun
from .sse import sse_manager
from .utils import persist_event

logger = logging.getLogger(__name__)

#: One row per flake, written when the gate records it (the Logs show when a test flaked).
FLAKY_EVENT = "check_flaky"
#: What the dashboard listens for: the list changed.
SSE_EVENT = "checks_flaky"
#: The Hub filed a fix task for failures a check run found that were not its task's:
#: `data = {"task_id", "tests", "kinds", "checks", "run_id", "main_sha", "found_by"}`.
FIX_TASK_EVENT = "checks_fix_task_filed"
#: A fix task in one of these is closed; a test it named may be filed for again.
_CLOSED_STATUSES = ("approved", "rejected")


def flakes_in(results: Any) -> List[Tuple[str, List[str], str]]:
    """The flakes one run's results recorded: (check name, failed test ids, how it was re-run).

    An empty test list means the whole check was re-run (its report named no failing test)."""
    found: List[Tuple[str, List[str], str]] = []
    for result in results or []:
        if not isinstance(result, dict) or not isinstance(result.get("flaky"), dict):
            continue
        flaky = result["flaky"]
        first = flaky.get("first") if isinstance(flaky.get("first"), dict) else {}
        tests = [str(t) for t in (flaky.get("tests") or first.get("failed_tests") or []) if t]
        found.append((str(result.get("name") or "check"), tests, str(flaky.get("how") or "check")))
    return found


async def record_flake(run_id: str, result: Dict[str, Any]) -> None:
    """Note one flake the gate just recorded: a Logs row and a dashboard refresh. Never raises —
    the run's own result already holds the flake, so a failed note loses nothing durable."""
    try:
        found = flakes_in([result])
        if not found:
            return
        check, tests, how = found[0]
        async with async_session_factory() as session:
            run = await session.get(TaskCheckRun, run_id)
            if run is None:
                return
            data = {
                "run_id": run_id,
                "task_id": run.task_id,
                "check": check,
                "tests": tests,
                "how": how,
            }
            await persist_event(session, run.project_id, FLAKY_EVENT, data, severity="warn")
            await sse_manager.broadcast(run.project_id, SSE_EVENT, data)
    except Exception:  # noqa: BLE001
        logger.warning("could not note the flake in check run %s", run_id, exc_info=True)


# --- fix tasks the Hub files itself (`a-red-main-does-not-hold-the-night`, D5) ---------------------


def normalised_test(test: str) -> str:
    """A test id as recorded: the report's own, so nothing but surrounding space is changed."""
    return test.strip()


async def _fix_events(session: AsyncSession, project_id: str) -> List[Dict[str, Any]]:
    """Every fix task the Hub filed in *project_id*, oldest first."""
    rows = (
        (
            await session.execute(
                select(EventLog.data)
                .where(EventLog.project_id == project_id, EventLog.event_type == FIX_TASK_EVENT)
                .order_by(EventLog.timestamp.asc(), EventLog.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return [row for row in rows if isinstance(row, dict) and row.get("task_id")]


async def fix_tasks_by_test(
    session: AsyncSession, project_id: str, *, open_only: bool
) -> Dict[str, str]:
    """Test id (normalised) to the latest Hub-filed fix task naming it; with *open_only*, only fix
    tasks that are not yet approved or rejected (what a new failure is deduplicated against)."""
    events = await _fix_events(session, project_id)
    statuses: Dict[str, Optional[str]] = {}
    if open_only and events:
        ids = list({data["task_id"] for data in events})
        statuses = {
            row[0]: row[1]
            for row in (
                await session.execute(select(Task.id, Task.status).where(Task.id.in_(ids)))
            ).all()
        }
    found: Dict[str, str] = {}
    for data in events:
        if open_only and statuses.get(data["task_id"]) in (None, *_CLOSED_STATUSES):
            continue
        for test in data.get("tests") or []:
            found[normalised_test(str(test))] = data["task_id"]
    return found
