"""Flaky tests the approval checks found, raised to the operator for a round of fixing.

The check gate re-runs a failure once before it counts against the task (`project_checks.
confirm_failure`); a failure that passes the second time is recorded on the run's result as
`flaky` and approval goes on. That keeps a flake from blocking someone else's work, but on its own
it hides the flake: the reviewer's briefing names it once, and nobody is asked to fix it. This
module is the other half: every flake the gate records is collected here, per test, and the
operator sees the list on the Overview until they hand it to a task (or dismiss it).

Nothing new is stored for a flake. The source is the check runs' own `results`, which already keep
the first attempt; what *is* stored is the operator's "handled through" mark, as an `event_logs`
row (`HANDLED_EVENT`), so a list the operator has dealt with does not come back until a test
flakes again.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.engine import async_session_factory
from .db.models import EventLog, TaskCheckRun
from .sse import sse_manager
from .utils import persist_event

logger = logging.getLogger(__name__)

#: One row per flake, written when the gate records it (the Logs show when a test flaked).
FLAKY_EVENT = "check_flaky"
#: The operator dealt with the flakes seen up to `data["through"]` (a task was made, or dismissed).
HANDLED_EVENT = "checks_flaky_handled"
#: What the dashboard listens for: the list changed.
SSE_EVENT = "checks_flaky"
#: How far back the list looks. A flake older than this that never recurred is not worth a round.
WINDOW_DAYS = 30
#: The check runs read for one report, newest first: a bound, not a page.
MAX_RUNS = 2000


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def flakes_in(results: Any) -> List[Tuple[str, List[str], str]]:
    """The flakes one run's results recorded: (check name, failed test ids, how it was re-run).

    An empty test list means the whole check was re-run (pytest did not name every failure)."""
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
    #: The pytest node id, or None when the whole check flaked without naming a test.
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
    """The project's open flaky tests, most recently seen first, and what was last done about them.

    Open: flaked within `WINDOW_DAYS` and after the last "handled through" mark. A test that flakes
    again after the operator handed the list to a task is open again — the fix did not hold."""
    now = now or datetime.now(timezone.utc)
    handled = await _handled(session, project_id)
    cutoff = now - timedelta(days=WINDOW_DAYS)
    through = None
    if handled and handled.get("through"):
        try:
            through = _aware(datetime.fromisoformat(str(handled["through"])))
        except ValueError:
            through = None
    since = max(cutoff, through) if through else cutoff
    rows = (
        await session.execute(
            select(
                TaskCheckRun.id, TaskCheckRun.task_id, TaskCheckRun.started_at, TaskCheckRun.results
            )
            .where(TaskCheckRun.project_id == project_id, TaskCheckRun.started_at > since)
            .order_by(TaskCheckRun.started_at.desc())
            .limit(MAX_RUNS)
        )
    ).all()
    by_key: Dict[Tuple[str, Optional[str]], FlakyTest] = {}
    for run_id, task_id, started_at, results in reversed(rows):
        seen = _aware(started_at)
        for check, tests, _how in flakes_in(results):
            for test in tests or [None]:
                entry = by_key.setdefault((check, test), FlakyTest(check=check, test=test))
                entry.occurrences += 1
                entry.first_seen = entry.first_seen or seen
                entry.last_seen = seen
                if task_id not in entry.task_ids:
                    entry.task_ids.append(task_id)
                entry.run_ids.append(run_id)
    flaky = sorted(
        by_key.values(),
        key=lambda f: (f.last_seen or now, f.occurrences),
        reverse=True,
    )
    return {
        "window_days": WINDOW_DAYS,
        "flaky": [f.as_dict() for f in flaky],
        "handled": handled,
    }


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
        "Done when each listed test passes 20 consecutive runs under `-n 8` alongside the full "
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
