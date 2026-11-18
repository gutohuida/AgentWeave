"""Flaky tests are quarantined (`the-slow-checks-run-once-per-landing-not-once-per-task-and-flaky-
tests-are-quarantined`, task `quarantine-core`).

A quarantined test (`QuarantinedTest`) is one whose failures count against no gate: it still runs
and is recorded in its history (FR-4), but its failure is not re-run to confirm (FR-3), does not
fail a task's pre-review run or a landing batch (FR-2), and is never added to the known-failing
list (FR-5). It sits beside that list, not in it (design 2).

**Entry** (FR-1) is decided only when a check run records a flip for the test: its flake rate,
counting that flip (`check_history.flake_rates`), above the project's `quarantine_threshold` admits
it, unless the operator marked it never to be quarantined (`NeverQuarantineMark`, FR-8). A test with
no rate (fewer than `check_history.MINIMUM_RUNS` runs) does not enter. A test that left keeps its old
flips in its rate's window, so it returns only on a new flip (design 4) -- and since a quarantined
test is never re-run, its failures record as `failed`, never `flipped` (design 3).

**Exit** (FR-7) is by consecutive passes: each run that ran it and passed it counts one, a failure
sets the count to 0, and reaching the project's `quarantine_exit_passes` releases it. Both settings
are read at each decision (FR-9), so a change needs no restart and releases or admits nothing by
itself.

**Judging** (the spec's algorithm): `excuse` splits a failed result's named failures into those
quarantine excuses and the rest, before its confirmation re-run. A quarantined test whose file the
report names, in a file the work changes, is not excused (FR-6); where the report names no file it
is (design 6, the opposite of `project_checks.touched_tests`). The rest is confirmed and judged
against the known-failing list exactly as without quarantine; where nothing is left the check
passes. The excused tests are named on the result under `RESULT_KEY`.

**Its fix task** (FR-10): entering files one, unless an open fix task already names the test, owned
as the known-failing list owns one (`known_failing.owner_of`, `_open_fix_task_for`). Leaving adds a
note to it and leaves it open.

When quarantine state cannot be read, nothing is excused (the Tier 2 hazard's safe side). Every
entry point here never raises.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import check_history
from .db.engine import async_session_factory
from .db.models import (
    CheckTestOutcome,
    NeverQuarantineMark,
    Project,
    QuarantinedTest,
    Task,
    TaskCheckRun,
)
from .utils import short_id

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.05
DEFAULT_EXIT_PASSES = 20
#: On a check result: `{"tests": [snapshot, ...], "first": {...}}`. `tests` are the failures
#: quarantine excused; `first`, present where they were all its failures, is what the check's run
#: recorded before it was judged passing. `changed_file` names quarantined tests not excused because
#: the work changes the file the report names for them (FR-6).
RESULT_KEY = "quarantine"
#: The fix task's dedupe event's kind for its test (`flaky_tests.FIX_TASK_EVENT`'s `kinds`).
KIND = "quarantined"
#: What the dashboard listens for: quarantine changed.
SSE_EVENT = "quarantine_changed"
#: How many of a test's most recent flips its fix task names.
RECENT_FLIPS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


_locks: Dict[int, asyncio.Lock] = {}


def _lock() -> asyncio.Lock:
    """One change to quarantine at a time per event loop, so two runs recording together admit a
    test once and file one fix task."""
    loop_id = id(asyncio.get_running_loop())
    if loop_id not in _locks:
        _locks[loop_id] = asyncio.Lock()
    return _locks[loop_id]


def settings_of(project: Optional[Project]) -> Tuple[float, int]:
    """*project*'s quarantine threshold and exit number (FR-9), the defaults where unset."""
    threshold = getattr(project, "quarantine_threshold", None)
    passes = getattr(project, "quarantine_exit_passes", None)
    return (
        float(threshold) if threshold is not None else DEFAULT_THRESHOLD,
        int(passes) if passes is not None else DEFAULT_EXIT_PASSES,
    )


def snapshot(row: QuarantinedTest) -> Dict[str, Any]:
    """A quarantined test as a result records it when it is excused: kept after it leaves."""
    return {
        "id": row.id,
        "check": row.check_name,
        "test": row.test_id,
        "flake_rate": row.flake_rate,
        "flips": row.flips,
        "entered_at": _iso(row.entered_at),
        "passes": row.passes,
        "fix_task_id": row.fix_task_id,
    }


# --- reading -------------------------------------------------------------------------------------


async def _marked(session: AsyncSession, project_id: str, check: Optional[str] = None) -> Set[Any]:
    query = select(NeverQuarantineMark.check_name, NeverQuarantineMark.test_id).where(
        NeverQuarantineMark.project_id == project_id
    )
    if check is not None:
        query = query.where(NeverQuarantineMark.check_name == check)
    return {(name, test) for name, test in (await session.execute(query)).all()}


async def _rows(
    session: AsyncSession, project_id: str, check: Optional[str] = None
) -> List[QuarantinedTest]:
    query = select(QuarantinedTest).where(QuarantinedTest.project_id == project_id)
    if check is not None:
        query = query.where(QuarantinedTest.check_name == check)
    return list(
        (
            await session.execute(
                query.order_by(QuarantinedTest.entered_at.desc(), QuarantinedTest.id.asc())
            )
        )
        .scalars()
        .all()
    )


async def for_check(project_id: str, check: str) -> Dict[str, Dict[str, Any]]:
    """*check*'s quarantined tests that are not marked never, by test id, as `snapshot`s. `{}`
    where quarantine cannot be read: then nothing is excused, the safe side."""
    try:
        async with async_session_factory() as session:
            marked = await _marked(session, project_id, check)
            return {
                row.test_id: snapshot(row)
                for row in await _rows(session, project_id, check)
                if (row.check_name, row.test_id) not in marked
            }
    except Exception:  # noqa: BLE001
        logger.warning("could not read the quarantine of %s", project_id, exc_info=True)
        return {}


# --- judging (the spec's algorithm, steps 1-5) ---------------------------------------------------


def _path_key(path: str) -> str:
    return path.strip().replace("\\", "/")


def apply_excuse(
    result: Dict[str, Any],
    quarantined: Dict[str, Dict[str, Any]],
    changed: Optional[Sequence[str]],
) -> None:
    """Excuse *result*'s quarantined failures, before it is confirmed. Runs nothing.

    Only a failed result that names its failing tests is judged: a timeout, a check that could not
    run, or one whose report names no failing test is judged as without quarantine (step 1). A
    quarantined test is excused unless the report names its file and the work under check changes
    it (*changed*; where those are not known, a named file counts as changed). The rest stay in
    `failed_tests`, to be confirmed and judged as today; where none is left, the result passes and
    `RESULT_KEY`'s `first` keeps what its run recorded."""
    from .project_checks import OUTPUT_TAIL_CHARS, could_not_run, failed

    if not quarantined or not failed(result) or result.get("timed_out") or could_not_run(result):
        return
    failing = [str(t) for t in result.get("failed_tests") or [] if t]
    if not failing:
        return
    files = result.get("test_files") if isinstance(result.get("test_files"), dict) else {}
    changed_keys = None if changed is None else {_path_key(path) for path in changed}
    excused: List[str] = []
    voided: List[str] = []
    for test in failing:
        if test not in quarantined:
            continue
        file = str(files.get(test) or "")
        if file and (changed_keys is None or _path_key(file) in changed_keys):
            voided.append(test)  # the work changes its test: it owns the failure (FR-6)
        else:
            excused.append(test)
    if voided:
        result.setdefault(RESULT_KEY, {})["changed_file"] = voided
    if not excused:
        return
    record = result.setdefault(RESULT_KEY, {})
    record["tests"] = [quarantined[test] for test in excused]
    rest = [test for test in failing if test not in excused]
    if rest:
        result["failed_tests"] = rest
        return
    record["first"] = {
        key: result.get(key)
        for key in ("exit_code", "timed_out", "duration_seconds", "output_tail")
    }
    record["first"]["failed_tests"] = failing
    result["exit_code"], result["timed_out"] = 0, False
    result.pop("failed_tests", None)
    note = (
        f"[quarantined: {', '.join(excused)} failed, and is quarantined, so it does not count "
        "against the work]\n"
    )
    result["output_tail"] = (note + str(result.get("output_tail") or ""))[-OUTPUT_TAIL_CHARS:]


async def excuse(
    project_id: str,
    check: Dict[str, Any],
    result: Dict[str, Any],
    changed: Optional[Sequence[str]],
) -> None:
    """`apply_excuse` with *check*'s quarantine as it is now. Never raises: unread, nothing is
    excused."""
    from .project_checks import failed

    if not failed(result) or not result.get("failed_tests"):
        return
    try:
        apply_excuse(result, await for_check(project_id, str(check["name"])), changed)
    except Exception:  # noqa: BLE001
        logger.warning("could not apply quarantine to check %s", check.get("name"), exc_info=True)


def excused_ids(result: Dict[str, Any]) -> Set[str]:
    """The test ids quarantine excused on *result*."""
    record = result.get(RESULT_KEY) if isinstance(result.get(RESULT_KEY), dict) else {}
    return {
        str(entry.get("test")) for entry in record.get("tests") or [] if isinstance(entry, dict)
    }


def only_excused_fail(again: Dict[str, Any], excused: Iterable[str]) -> bool:
    """Whether a whole-check re-run *again* failed only tests quarantine excused: its failure then
    confirms nothing about the rest (FR-2)."""
    named = {str(t) for t in again.get("failed_tests") or [] if t}
    allowed = set(excused)
    return bool(allowed) and bool(named) and not again.get("timed_out") and named <= allowed


def excused_by_quarantine(result: Any) -> bool:
    """Whether *result* passed only because quarantine excused every failure it had."""
    if not isinstance(result, dict) or not isinstance(result.get(RESULT_KEY), dict):
        return False
    return isinstance(result[RESULT_KEY].get("first"), dict)


# --- entry and exit (the spec's algorithm, step 6) -----------------------------------------------


async def after_recorded(
    *,
    project_id: str,
    check_name: str,
    check_run_id: str,
    rows: Sequence[Tuple[str, str, str]],
) -> List[str]:
    """Read one check run's recorded outcomes of *check_name* (`check_history.rows_for`) into
    quarantine: a flip may admit its test (FR-1); a quarantined test's pass counts toward its exit,
    a failure sets the count to 0, and the exit number reached releases it (FR-7). Returns the ids
    of the tests admitted. Never raises."""
    if not rows:
        return []
    try:
        async with _lock():
            return await _after_recorded(project_id, check_name, check_run_id, rows)
    except Exception:  # noqa: BLE001 -- the run's own record holds what it found
        logger.warning("could not read check run %s into quarantine", check_run_id, exc_info=True)
        return []


async def _after_recorded(
    project_id: str, check_name: str, check_run_id: str, rows: Sequence[Tuple[str, str, str]]
) -> List[str]:
    entering: List[QuarantinedTest] = []
    leaving: List[QuarantinedTest] = []
    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        threshold, exit_passes = settings_of(project)
        quarantined = {row.test_id: row for row in await _rows(session, project_id, check_name)}
        marked = {test for _name, test in await _marked(session, project_id, check_name)}
        for test, _file, outcome in rows:
            row = quarantined.get(test)
            if row is not None:
                if outcome == check_history.PASSED:
                    row.passes = (row.passes or 0) + 1
                    if row.passes >= exit_passes:
                        leaving.append(row)
                else:
                    row.passes = 0
                continue
            if outcome != check_history.FLIPPED or test in marked:
                continue
            # The rate counting this flip: the history was written before this was called.
            figures = await check_history.flake_rates(session, project_id, check_name, test)
            rate = figures[0].get("flake_rate") if figures else None
            if rate is None or float(rate) <= threshold:
                continue
            row = QuarantinedTest(
                id=f"qt-{short_id()}",
                project_id=project_id,
                check_name=check_name,
                test_id=test,
                flake_rate=float(rate),
                flips=int(figures[0].get("window_flips") or 0),
                entered_at=_now(),
                entered_by_run=check_run_id,
                passes=0,
            )
            session.add(row)
            quarantined[test] = row
            entering.append(row)
        for row in leaving:
            await _release(
                session,
                row,
                f"{row.test_id} ({row.check_name}) passed {row.passes} consecutive check runs, so "
                f"it left quarantine (check run {check_run_id}). Its failures count against the "
                "gates again; this task stays open until the flake is fixed.",
            )
        await session.commit()
        for row in entering:
            await _file_fix_task(session, row, check_run_id)
    if entering or leaving:
        await _announce(project_id)
    return [row.test_id for row in entering]


async def _release(session: AsyncSession, row: QuarantinedTest, line: str) -> None:
    """Take *row* out of quarantine in *session*, its fix task gaining *line* and staying open."""
    from .known_failing import _note_on

    await session.delete(row)
    owner = await session.get(Task, row.fix_task_id) if row.fix_task_id else None
    if owner is not None:
        _note_on(owner, line)


async def _recent_flips(
    session: AsyncSession, project_id: str, check: str, test: str
) -> List[CheckTestOutcome]:
    return list(
        (
            await session.execute(
                select(CheckTestOutcome)
                .where(
                    CheckTestOutcome.project_id == project_id,
                    CheckTestOutcome.check_name == check,
                    CheckTestOutcome.test_id == test,
                    CheckTestOutcome.outcome == check_history.FLIPPED,
                )
                .order_by(CheckTestOutcome.id.desc())
                .limit(RECENT_FLIPS)
            )
        )
        .scalars()
        .all()
    )


def fix_task_text(
    row: QuarantinedTest, flips: Sequence[CheckTestOutcome], found_by: Optional[Task]
) -> Tuple[str, str]:
    """The title and description of *row*'s fix task: the check, the test, its flake rate and its
    most recent flips (FR-10)."""
    where = f"task {found_by.display_id}'s check run" if found_by is not None else "a check run"
    lines = [
        f"Check: {row.check_name}",
        f"Test: {row.test_id}",
        f"Flake rate: {row.flake_rate:.4f} ({row.flips} flips in its last "
        f"{check_history.WINDOW_RUNS} recorded runs at most)",
        f"Quarantined by: {where} {row.entered_by_run or ''}",
        "",
        "Its most recent flips (failed, then passed when run again on the same tree):",
    ]
    lines += [
        f"- {_iso(flip.recorded_at)}: check run {flip.check_run_id} ({flip.phase}"
        + (f", commit {flip.commit_sha[:12]}" if flip.commit_sha else "")
        + ")"
        for flip in flips
    ] or ["- (none recorded)"]
    lines += [
        "",
        "The test is quarantined: it still runs and is recorded, but its failures count against no "
        "task's review or landing until it passes the project's number of consecutive runs. This "
        "task stays open after it leaves quarantine.",
        "",
        "A flaky test is made deterministic under load (wait for the event it means, not a fixed "
        "time; a fake clock; no shared-state race). Do not weaken it.",
    ]
    return f"Fix quarantined flaky test {row.test_id}"[:256], "\n".join(lines)[:10000]


async def _file_fix_task(session: AsyncSession, row: QuarantinedTest, check_run_id: str) -> None:
    """*row*'s fix task, unless an open fix task already names its test (FR-10): owned and
    deduplicated as the known-failing list's are, pending, on no loop or build."""
    from . import flaky_tests
    from .api.v1.tasks import create_task_for_actor
    from .known_failing import _open_fix_task_for, owner_of
    from .schemas.tasks import TaskCreate
    from .task_transitions import operator
    from .utils import persist_event

    try:
        existing = await _open_fix_task_for(session, row.project_id, row.test_id, row.check_name)
        if existing is not None:
            row.fix_task_id = existing
            await session.commit()
            return
        run = await session.get(TaskCheckRun, check_run_id)
        found_by = await session.get(Task, run.task_id) if run is not None else None
        flips = await _recent_flips(session, row.project_id, row.check_name, row.test_id)
        title, description = fix_task_text(row, flips, found_by)
        assignee = await owner_of(session, found_by)

        async def recorded(task: Task) -> None:
            task.merges_branch_tip = True
            row.fix_task_id = task.id
            await persist_event(
                session,
                row.project_id,
                flaky_tests.FIX_TASK_EVENT,
                {
                    "task_id": task.id,
                    "tests": [row.test_id],
                    "kinds": {row.test_id: KIND},
                    "checks": [row.check_name],
                    "run_id": check_run_id,
                    "main_sha": None,
                    "found_by": found_by.id if found_by is not None else None,
                    "quarantine_id": row.id,
                },
                commit=False,
            )

        await create_task_for_actor(
            TaskCreate(
                title=title,
                description=description,
                priority="high",
                status="pending",
                assignee=assignee,
            ),
            project_id=row.project_id,
            assigner=None,
            created_by_run_id=None,
            actor=operator(),
            session=session,
            before_commit=recorded,
        )
    except Exception:  # noqa: BLE001 -- the test is quarantined whether or not its task is filed
        logger.warning("could not file the fix task of quarantined %s", row.test_id, exc_info=True)
        await session.rollback()


async def _announce(project_id: str) -> None:
    from .sse import sse_manager

    try:
        await sse_manager.broadcast(project_id, SSE_EVENT, {"project_id": project_id})
    except Exception:  # noqa: BLE001
        logger.debug("quarantine broadcast failed", exc_info=True)


# --- the operator's view and marks (FR-8, FR-11's data) ------------------------------------------


def _task_view(task: Optional[Task], task_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if task is not None:
        return {
            "id": task.id,
            "display_id": task.display_id,
            "title": task.title,
            "status": task.status,
            "assignee": task.assignee,
        }
    return {"id": task_id} if task_id else None


async def view(session: AsyncSession, project_id: str) -> Dict[str, Any]:
    """The project's quarantine as its route serves it: each quarantined test with its check, id,
    rate and flips on entry, entry time, passes toward exit and fix task; the never-quarantine
    marks; and the two settings."""
    project = await session.get(Project, project_id)
    threshold, exit_passes = settings_of(project)
    rows = await _rows(session, project_id)
    ids = sorted({row.fix_task_id for row in rows if row.fix_task_id})
    tasks = (
        {t.id: t for t in (await session.execute(select(Task).where(Task.id.in_(ids)))).scalars()}
        if ids
        else {}
    )
    marks = (
        (
            await session.execute(
                select(NeverQuarantineMark)
                .where(NeverQuarantineMark.project_id == project_id)
                .order_by(NeverQuarantineMark.marked_at.desc(), NeverQuarantineMark.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "threshold": threshold,
        "exit_passes": exit_passes,
        "quarantined": [
            {
                **snapshot(row),
                "passes_to_exit": exit_passes,
                "fix_task": _task_view(tasks.get(row.fix_task_id or ""), row.fix_task_id),
            }
            for row in rows
        ],
        "marks": [
            {
                "id": mark.id,
                "check": mark.check_name,
                "test": mark.test_id,
                "marked_at": _iso(mark.marked_at),
            }
            for mark in marks
        ],
    }


async def set_mark(session: AsyncSession, project_id: str, check: str, test: str) -> bool:
    """Mark *check*'s *test* never to be quarantined (FR-8); a quarantined test leaves at once, its
    fix task gaining a note. Returns whether it was quarantined. The caller commits. Idempotent."""
    async with _lock():
        existing = (
            await session.execute(
                select(NeverQuarantineMark).where(
                    NeverQuarantineMark.project_id == project_id,
                    NeverQuarantineMark.check_name == check,
                    NeverQuarantineMark.test_id == test,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                NeverQuarantineMark(
                    id=f"nqm-{short_id()}",
                    project_id=project_id,
                    check_name=check,
                    test_id=test,
                    marked_at=_now(),
                )
            )
        row = (
            await session.execute(
                select(QuarantinedTest).where(
                    QuarantinedTest.project_id == project_id,
                    QuarantinedTest.check_name == check,
                    QuarantinedTest.test_id == test,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            await _release(
                session,
                row,
                f"{test} ({check}) was marked never to be quarantined, so it left quarantine: its "
                "failures count against the gates again. This task stays open.",
            )
        await session.commit()
    await _announce(project_id)
    return row is not None


async def remove_mark(session: AsyncSession, project_id: str, check: str, test: str) -> bool:
    """Remove *check*'s *test*'s never-quarantine mark: its next flip above the threshold may admit
    it again. Returns whether there was one. Admits nothing by itself."""
    async with _lock():
        existing = (
            await session.execute(
                select(NeverQuarantineMark).where(
                    NeverQuarantineMark.project_id == project_id,
                    NeverQuarantineMark.check_name == check,
                    NeverQuarantineMark.test_id == test,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            await session.delete(existing)
            await session.commit()
    if existing is not None:
        await _announce(project_id)
    return existing is not None
