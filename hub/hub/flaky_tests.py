"""Flaky tests the approval checks found, raised to the operator.

The check gate re-runs a failure once before it counts against the task (`project_checks.
confirm_failure`); a failure that passes the second time is recorded on the run's result as
`flaky`, approval goes on, and the test goes on the project's known-failing list as flaky with its
owner fix task (`known_failing`, `failures-already-known-are-on-a-list-not-re-argued` FR-2, FR-5).
That list is where a flake is kept: `report` reads its flaky entries, and nothing is reconstructed
from old check runs or the event log (FR-12). What this module still writes is one `event_logs`
row per flake (`FLAKY_EVENT`, so the Logs show when a test flaked) and the operator's "handled
through" mark (`HANDLED_EVENT`), until the list replaces this one on the Overview (task `ui`).

`FIX_TASK_EVENT` rows are what the Hub wrote when it filed a fix task, before the list and since
(`known_failing._file_fix_task`); `fix_tasks_by_test` reads them, so a test an open fix task already
names is never filed for twice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.engine import async_session_factory
from .db.models import EventLog, Task, TaskCheckRun
from .sse import sse_manager
from .utils import persist_event

logger = logging.getLogger(__name__)

#: One row per flake, written when the gate records it (the Logs show when a test flaked).
FLAKY_EVENT = "check_flaky"
#: The operator dealt with the flakes seen up to `data["through"]` (a task was made, or dismissed).
HANDLED_EVENT = "checks_flaky_handled"
#: What the dashboard listens for: the list changed.
SSE_EVENT = "checks_flaky"
#: The Hub filed a fix task for failures a check run found that were not its task's:
#: `data = {"task_id", "tests", "kinds", "checks", "run_id", "main_sha", "found_by"}`.
FIX_TASK_EVENT = "checks_fix_task_filed"
#: A fix task in one of these is closed; a test it named may be filed for again.
_CLOSED_STATUSES = ("approved", "rejected")


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


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


@dataclass
class FlakyTest:
    check: str
    #: The test id the check's report gave (`classname::name`), or None when the whole check
    #: flaked without naming a test.
    test: Optional[str]
    occurrences: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    task_ids: List[str] = field(default_factory=list)
    run_ids: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "check": self.check,
            "test": self.test,
            "occurrences": self.occurrences,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "task_ids": self.task_ids,
            "run_ids": self.run_ids[-5:],
        }


async def _handled(session: AsyncSession, project_id: str) -> Optional[Dict[str, Any]]:
    row = (
        await session.execute(
            select(EventLog.data, EventLog.timestamp)
            .where(EventLog.project_id == project_id, EventLog.event_type == HANDLED_EVENT)
            .order_by(EventLog.timestamp.desc())
            .limit(1)
        )
    ).first()
    if row is None or not isinstance(row[0], dict):
        return None
    return {**row[0], "at": _aware(row[1]).isoformat() if row[1] else None}


async def report(
    session: AsyncSession, project_id: str, *, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """The project's flaky tests: the flaky entries on its known-failing list, most recently seen
    first, and what was last done about them. Read from the list alone (FR-12): a test comes off it
    by the list's own rule (`known_failing`), not by a window over old runs. Open: last seen after
    the last "handled through" mark, which filing an entry's fix task sets, so a flake that already
    has its fix task shows again only once it flakes again."""
    from .db.models import KnownFailingTest

    handled = await _handled(session, project_id)
    through = None
    if handled and handled.get("through"):
        try:
            through = _aware(datetime.fromisoformat(str(handled["through"])))
        except ValueError:
            through = None
    rows = (
        (
            await session.execute(
                select(KnownFailingTest)
                .where(
                    KnownFailingTest.project_id == project_id,
                    KnownFailingTest.kind == "flaky",
                )
                .order_by(KnownFailingTest.last_seen.desc(), KnownFailingTest.id.asc())
            )
        )
        .scalars()
        .all()
    )
    flaky = [
        FlakyTest(
            check=row.check_name,
            test=row.test or None,
            occurrences=1,
            first_seen=_aware(row.first_seen),
            last_seen=_aware(row.last_seen),
            task_ids=[row.fix_task_id] if row.fix_task_id else [],
            run_ids=[row.added_by_run] if row.added_by_run else [],
        )
        for row in rows
        if through is None or (_aware(row.last_seen) or through) > through
    ]
    return {"flaky": [f.as_dict() for f in flaky], "handled": handled}


def fix_task_text(flaky: Iterable[Dict[str, Any]]) -> Tuple[str, str]:
    """The title and description of a task asking for the listed flakes to be fixed."""
    items = list(flaky)
    tests = [f for f in items if f.get("test")]
    whole = [f for f in items if not f.get("test")]
    count = len(tests) + len(whole)
    title = f"Fix {count} flaky test{'s' if count != 1 else ''} the approval checks found"
    lines = [
        "The approval checks re-ran these failures and they passed the second time, so approval "
        "went on. Each one cost a gate run and hides real failures. Make each test deterministic "
        "under load: wait for the event it means instead of a fixed time, use a fake clock, or "
        "remove a shared-state race. Do not quarantine or weaken what the test guards.",
        "",
    ]
    for f in tests:
        lines.append(
            f"- `{f['test']}` ({f['check']}): flaked {f['occurrences']}x, last {f.get('last_seen')}"
            f", seen on {', '.join(f.get('task_ids') or [])}"
        )
    for f in whole:
        lines.append(
            f"- check `{f['check']}` (no failing test named; the whole check was re-run): "
            f"flaked {f['occurrences']}x, last {f.get('last_seen')}"
        )
    lines += [
        "",
        "Done when each listed test passes 20 consecutive runs under load alongside the full "
        "suite, and the fix explains the race it removed.",
    ]
    return title, "\n".join(lines)


async def mark_handled(
    session: AsyncSession,
    project_id: str,
    *,
    through: str,
    task_id: Optional[str],
    count: int,
) -> None:
    """Record that the operator dealt with the flakes seen up to *through*."""
    await persist_event(
        session,
        project_id,
        HANDLED_EVENT,
        {"through": through, "task_id": task_id, "count": count},
    )
    await sse_manager.broadcast(project_id, SSE_EVENT, {"handled": True, "task_id": task_id})


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
