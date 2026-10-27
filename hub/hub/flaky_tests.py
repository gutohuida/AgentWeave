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

**Failures the checks found that are not the task's** (`a-red-main-does-not-hold-the-night`, D5):
when a check run ends with failures that are main's (the same test ids fail on main) or flakes, and
the project's automatic override is on, the Hub files one fix task for them itself
(`file_fix_task`), deduplicated by test id against the open fix tasks it filed before, and in the
held task's flow when that is live, as critical so the flow staffs it first. Which task was filed
for which tests is an `event_logs` row (`FIX_TASK_EVENT`), not a task column: the override at
approval names the task from it, and a fix task is never landed over the very tests it was filed
for.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

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


# --- fix tasks the Hub files itself (`a-red-main-does-not-hold-the-night`, D5) ---------------------


def _key(test: str) -> str:
    return test.strip().replace("\\", "/")


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


async def filed_for(session: AsyncSession, task: Task) -> List[str]:
    """The test ids *task* was filed to fix, where the Hub filed it; `[]` for any other task. An
    override is never automatic over these on the task itself (FR-4): a fix task that did not fix
    its test would otherwise land itself over the very failure it was filed for."""
    tests: List[str] = []
    for data in await _fix_events(session, task.project_id):
        if data["task_id"] == task.id:
            tests += [str(t) for t in data.get("tests") or []]
    return tests


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
            found[_key(str(test))] = data["task_id"]
    return found


def fix_task_text_for(
    entries: Sequence[Dict[str, str]], *, run: TaskCheckRun, found_by: str
) -> Tuple[str, str]:
    """The title and description of a fix task the Hub files for *entries* (`{"check", "test",
    "kind"}`) found by *run* on task *found_by*'s work: each test with its check and kind, the main
    commit, the run, its failure excerpt, and when it is done."""
    main = (run.main_sha or "")[:12]
    on_main = [e for e in entries if e["kind"] != "flaky"]
    flaky = [e for e in entries if e["kind"] == "flaky"]
    if len(entries) == 1:
        entry = entries[0]
        title = (
            f"Fix flaky test {entry['test']}"
            if entry["kind"] == "flaky"
            else f"Fix {entry['test']}: it fails on main"
        )
    else:
        title = f"Fix {len(entries)} tests the approval checks found failing on main or flaky"
    lines = [
        f"The project's checks found these failures on task {found_by}'s work, in check run "
        f"{run.id} on main {main}, and they are not that task's: approving it lands its work with "
        "an override the Hub records, and this task fixes them.",
        "",
    ]
    for entry in on_main:
        lines.append(f"- `{entry['test']}` ({entry['check']}): fails on main at {main} too")
    for entry in flaky:
        lines.append(
            f"- `{entry['test']}` ({entry['check']}): flaky -- failed in the run and passed when "
            "rerun on its own"
        )
    excerpts = []
    for result in run.results or []:
        if not isinstance(result, dict) or not any(
            e["check"] == result.get("name") for e in entries
        ):
            continue
        first = (result.get("flaky") or {}).get("first") or {}
        text = str(
            result.get("failure_excerpt")
            or (result.get("output_tail") if not result.get("flaky") else "")
            or first.get("output_tail")
            or ""
        ).strip()
        if text:
            excerpts.append(f"{result.get('name')}:\n{text[-2000:]}")
    if excerpts:
        lines += ["", "What the run printed:", "", *excerpts]
    lines += [
        "",
        "Done when these ids pass on main: " + ", ".join(e["test"] for e in entries) + ".",
    ]
    if flaky:
        lines.append(
            "A flaky test is made deterministic under load (wait for the event it means, not a "
            "fixed time; a fake clock; no shared-state race). Do not quarantine or weaken it."
        )
    return title[:256], "\n".join(lines)[:10000]


_filing_locks: Dict[int, asyncio.Lock] = {}


def _filing_lock() -> asyncio.Lock:
    """One filing at a time per event loop, so two runs ending together file one task."""
    loop_id = id(asyncio.get_running_loop())
    if loop_id not in _filing_locks:
        _filing_locks[loop_id] = asyncio.Lock()
    return _filing_locks[loop_id]


async def file_fix_task(run_id: str) -> Optional[str]:
    """At a check run's end: file one fix task for its failures that are not its task's, where the
    project's automatic override is on (`a-red-main-does-not-hold-the-night`, FR-6, FR-7). The id of
    the fix task filed, or `None`. Never raises.

    Deduplicated by test id against the Hub's open fix tasks: ids one of them already names are
    left to it, and only the rest are filed. In the found-by task's flow, as `critical`, when that
    flow is live (the next firing staffs it ahead of every other pending task); otherwise pending
    and unassigned. Filed with the operator's authority, as `POST /checks/flaky/handled` files one.
    A flake's filing marks the flaky-test list handled with the task, so the Overview does not ask
    for it twice."""
    from . import flow_advance, project_checks, requirement_gate
    from .api.v1.tasks import create_task_for_actor
    from .schemas.tasks import TaskCreate
    from .task_transitions import operator

    try:
        async with _filing_lock(), async_session_factory() as session:
            run = await session.get(TaskCheckRun, run_id)
            if run is None or run.state not in ("passed", "failed"):
                return None
            task = await session.get(Task, run.task_id)
            if task is None or not await requirement_gate.automatic_override_allowed(session, task):
                return None
            found = project_checks.not_the_tasks(
                run.results, excluded=await filed_for(session, task)
            )
            if not found:
                return None
            covered = await fix_tasks_by_test(session, task.project_id, open_only=True)
            new = [entry for entry in found if _key(entry["test"]) not in covered]
            if not new:
                return None
            loop_id = task.loop_id if await flow_advance.is_live(session, task.loop_id) else None
            title, description = fix_task_text_for(new, run=run, found_by=task.id)
            project_id, found_by, main_sha = task.project_id, task.id, run.main_sha
            started = _aware(run.started_at) or datetime.now(timezone.utc)

            async def recorded(task: Task) -> None:
                # In the task's own commit: a fix task the dedup cannot see, or one that cannot be
                # reviewed and landed in a flow (no requirement, no evidence), never exists.
                task.merges_branch_tip = True
                await persist_event(
                    session,
                    project_id,
                    FIX_TASK_EVENT,
                    {
                        "task_id": task.id,
                        "tests": [entry["test"] for entry in new],
                        "kinds": {entry["test"]: entry["kind"] for entry in new},
                        "checks": sorted({entry["check"] for entry in new}),
                        "run_id": run_id,
                        "main_sha": main_sha,
                        "found_by": found_by,
                    },
                    loop_id=loop_id,
                    commit=False,
                )

            created = await create_task_for_actor(
                TaskCreate(
                    title=title, description=description, priority="critical", loop_id=loop_id
                ),
                project_id=project_id,
                assigner=None,
                created_by_run_id=None,
                actor=operator(),
                session=session,
                before_commit=recorded,
            )
            flakes = [entry for entry in new if entry["kind"] == project_checks.FLAKY]
            if flakes:
                await mark_handled(
                    session,
                    project_id,
                    through=started.isoformat(),
                    task_id=created.id,
                    count=len(flakes),
                )
        if loop_id:
            flow_advance.request(loop_id)
        return created.id
    except Exception:  # noqa: BLE001 -- the override still lands; the operator sees the failure
        logger.warning("could not file a fix task for check run %s", run_id, exc_info=True)
        return None
