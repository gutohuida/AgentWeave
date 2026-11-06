"""The project's known-failing list (`failures-already-known-are-on-a-list-not-re-argued`, task
`list`).

One list per project (`KnownFailingTest`, FR-1): each entry names a check, a test id from that
check's report or the whole check (`test == ""`), its kind -- `fails on main` or `flaky` -- when it
was first and last seen failing, the run that added it, and its owner fix task.

**What adds an entry.** A failing test whose confirmation re-run passes, in any run, is added as
flaky (FR-2). A test that fails in a run on main's tree is added as failing on main (FR-3). The
runs on main's tree are a landed batch's own run (`landing_queue._record_landed` calls
`record_run` with the landed commit), a full run of the project's checks made once on each main
commit the Hub did not land (`main_watch.observe` calls `schedule_main_run`), and one test re-run
alone on main after it failed, confirmed, for two different tasks in a row with no pass of it in
between (`judge_unlisted`, FR-13). Those last two are `MainCheckRun` rows.

**What the gates ask of it** (FR-7): `judge` marks a task's or a batch's failed, confirmed result
against the list -- a listed failure is not the work's, an unlisted one is -- and neither gate runs
anything on a checkout of main to decide it, apart from the twice rule's one test. The entries a
result went past stay on it (`listed`), which is what a landing names (FR-10, `went_past`).

**What removes one.** Only a run that ran the test counts (FR-4): every run is told which tests
are listed (`watching`), and the check's report says whether each one passed (`watched_passed`).
A failing-on-main entry is removed when its test passes in a run on main's tree; a flaky entry when
it passes in a run on main's tree after its fix task was approved, or after 20 consecutive runs
that ran it and passed it. The removed entry's fix task stays open and gains a note naming the main
commit (FR-14).

**Its owner** (FR-5, FR-6): one fix task per entry, unless an open fix task already names the test,
created `pending` (never `assigned`, which `assigned_task_start` would start), on no loop, flow or
build, assigned to the developer of the build or loop the finding task belongs to, else that
task's builder, else its assignee; an entry found by a run on main has an unassigned fix task. The
filing is also written as `flaky_tests.FIX_TASK_EVENT`.

Every entry point here is called after a run has ended, from its own session, and never raises:
the run's own record already holds what it found.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.engine import async_session_factory
from .db.models import (
    AIJob,
    Build,
    KnownFailingTest,
    Loop,
    MainCheckRun,
    Project,
    Task,
    TaskCheckRun,
    UnlistedTestFailure,
)
from .utils import short_id

logger = logging.getLogger(__name__)

FAILS_ON_MAIN = "fails on main"
FLAKY = "flaky"
KINDS = (FAILS_ON_MAIN, FLAKY)
#: The `test` of an entry for a whole check, one that names no failing test.
WHOLE_CHECK = ""
#: A flaky entry comes off after this many consecutive runs that ran its test and passed it.
FLAKY_PASSES_TO_CLEAR = 20
#: `MainCheckRun.reason`.
OUTSIDE_COMMIT = "outside_commit"
SINGLE_TEST = "single_test"
#: What the dashboard listens for: the list changed.
SSE_EVENT = "known_failing_changed"
#: A fix task in one of these is closed.
_CLOSED = ("approved", "rejected")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _iso(value: Optional[datetime]) -> Optional[str]:
    value = _aware(value)
    return value.isoformat() if value is not None else None


_locks: Dict[int, asyncio.Lock] = {}


def _lock() -> asyncio.Lock:
    """One change to the list at a time per event loop, so two runs ending together add one entry
    and file one fix task."""
    loop_id = id(asyncio.get_running_loop())
    if loop_id not in _locks:
        _locks[loop_id] = asyncio.Lock()
    return _locks[loop_id]


# --- reading -------------------------------------------------------------------------------------


async def entries(session: AsyncSession, project_id: str) -> List[KnownFailingTest]:
    """The project's list, most recently seen first."""
    return list(
        (
            await session.execute(
                select(KnownFailingTest)
                .where(KnownFailingTest.project_id == project_id)
                .order_by(KnownFailingTest.last_seen.desc(), KnownFailingTest.id.asc())
            )
        )
        .scalars()
        .all()
    )


def entry_view(entry: KnownFailingTest, fix_task: Optional[Task]) -> Dict[str, Any]:
    return {
        "id": entry.id,
        "check": entry.check_name,
        "test": entry.test or None,
        "whole_check": not entry.test,
        "kind": entry.kind,
        "first_seen": _iso(entry.first_seen),
        "last_seen": _iso(entry.last_seen),
        "added_by_run": entry.added_by_run,
        "passes": entry.passes,
        "fix_task": (
            {
                "id": fix_task.id,
                "display_id": fix_task.display_id,
                "title": fix_task.title,
                "status": fix_task.status,
                "assignee": fix_task.assignee,
            }
            if fix_task is not None
            else ({"id": entry.fix_task_id} if entry.fix_task_id else None)
        ),
    }


async def view(session: AsyncSession, project_id: str) -> Dict[str, Any]:
    """The list as its route serves it (FR-1, `ac-entry`)."""
    rows = await entries(session, project_id)
    ids = sorted({row.fix_task_id for row in rows if row.fix_task_id})
    tasks = (
        {t.id: t for t in (await session.execute(select(Task).where(Task.id.in_(ids)))).scalars()}
        if ids
        else {}
    )
    return {"entries": [entry_view(row, tasks.get(row.fix_task_id or "")) for row in rows]}


async def watching(project_id: str, checks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """*checks*, each carrying `watch_tests`: the test ids on the list, or last failed by a task
    while unlisted, for that check. A run's report then says whether each one passed
    (`project_checks._judge_by_report`, `watched_passed`), which is how a run that did not run a
    test is told from one that passed it (FR-4). Never raises; *checks* unchanged on a failure."""
    try:
        async with async_session_factory() as session:
            watched: Dict[str, Set[str]] = {}
            for name, test in (
                await session.execute(
                    select(KnownFailingTest.check_name, KnownFailingTest.test).where(
                        KnownFailingTest.project_id == project_id
                    )
                )
            ).all():
                if test:
                    watched.setdefault(name, set()).add(test)
            for name, test in (
                await session.execute(
                    select(UnlistedTestFailure.check_name, UnlistedTestFailure.test).where(
                        UnlistedTestFailure.project_id == project_id
                    )
                )
            ).all():
                watched.setdefault(name, set()).add(test)
    except Exception:  # noqa: BLE001 -- a run that watches nothing counts no pass
        logger.warning("could not read the known-failing list of %s", project_id, exc_info=True)
        return list(checks)
    return [
        (
            {**check, "watch_tests": sorted(watched[check["name"]])}
            if check["name"] in watched
            else check
        )
        for check in checks
    ]


# --- what one result says ------------------------------------------------------------------------


@dataclass
class Observed:
    """What one check's result says about tests: which flaked (failed, then passed when re-run),
    which failed and stood their re-run, whether the whole check failed naming no test, and which
    watched tests (or the whole check) ran and passed."""

    flaky: List[str] = field(default_factory=list)
    failing: List[str] = field(default_factory=list)
    whole_check_failed: bool = False
    passed: Set[str] = field(default_factory=set)
    whole_check_passed: bool = False


def _failed(result: Dict[str, Any]) -> bool:
    from .project_checks import failed

    return failed(result)


def observe(result: Dict[str, Any]) -> Observed:
    """*result* read for the list. A skipped result ran nothing, so says nothing; a reused pass says
    what the run it was reused from found on the same tree (`record_run` counts it once, by that
    run). A test in a file the task's work changes is the task's (`touched_tests`), never listed
    as flaky."""
    seen = Observed()
    if not isinstance(result, dict) or result.get("skipped"):
        return seen
    touched = set(result.get("touched_tests") or [])
    flaky = result.get("flaky") if isinstance(result.get("flaky"), dict) else None
    if flaky is not None:
        if flaky.get("how") == "tests":
            tests = result.get("flaky_tests") or flaky.get("tests") or []
            seen.flaky = [str(t) for t in tests if t and t not in touched]
    elif _failed(result):
        named = [str(t) for t in result.get("failed_tests") or [] if t]
        flaked = [str(t) for t in result.get("flaky_tests") or [] if t]
        seen.flaky = [t for t in flaked if t not in touched]
        if result.get("confirmed"):
            seen.failing = [t for t in named if t not in flaked]
            from .project_checks import unjudged_timeout

            if not named and not unjudged_timeout(result):
                seen.whole_check_failed = True
    seen.passed = {str(t) for t in result.get("watched_passed") or []} - set(seen.failing)
    seen.passed -= set(result.get("failed_tests") or [])
    # A run of named tests alone (`narrowed`) passing says nothing of the rest of the check.
    seen.whole_check_passed = not _failed(result) and flaky is None and not result.get("narrowed")
    return seen


# --- owner fix tasks (FR-5, FR-6) ----------------------------------------------------------------


async def owner_of(session: AsyncSession, task: Optional[Task]) -> Optional[str]:
    """Who a fix task for an entry *task*'s run found goes to (FR-5): the developer of the build,
    else of the loop, *task* belongs to; else its builder; else its assignee -- the first of those
    that is an open agent of the project, since a task cannot be held by a name that is not one.
    `None` for an entry a run on main found (*task* `None`), or where none of them is an agent."""
    from .builds import open_agents

    if task is None:
        return None
    candidates: List[Optional[str]] = []
    if task.build_id:
        build = await session.get(Build, task.build_id)
        if build is not None:
            people = build.people if isinstance(build.people, dict) else {}
            candidates.append(people.get("builder"))
            candidates += [str(b) for b in build.builders or []][:1]
    if task.loop_id:
        loop = await session.get(Loop, task.loop_id)
        job = await session.get(AIJob, loop.job_id) if loop is not None else None
        candidates.append(job.agent if job is not None else None)
    candidates += [task.builder, task.assignee]
    agents = await open_agents(session, task.project_id)
    return next((str(name) for name in candidates if name and name in agents), None)


def fix_task_text(
    entry: KnownFailingTest, *, run: Any, found_by: Optional[Task]
) -> Tuple[str, str]:
    """The title and description of *entry*'s fix task: the check, the test, its kind and the run
    that found it (FR-5), what that run printed about it, and when it is done."""
    test = entry.test or f"the whole check {entry.check_name}"
    main = str(getattr(run, "main_sha", "") or "")[:12]
    if entry.kind == FLAKY:
        title = f"Fix flaky test {test}"
        what = "failed and then passed when it was run again on the same tree: it is flaky"
    else:
        title = f"Fix {test}: it fails on main"
        what = f"fails on main's tree (main {main})"
    where = f"task {found_by.display_id}'s check run" if found_by is not None else "a run on main"
    lines = [
        f"Check: {entry.check_name}",
        f"Test: {entry.test or '(the whole check: its report names no failing test)'}",
        f"Kind: {entry.kind}",
        f"Found by: {where} {getattr(run, 'id', '')}, on main {main}",
        "",
        f"The test {what}. It is on the project's known-failing list, so the checks do not hold it "
        "against anyone else's work while this task is open.",
    ]
    for result in getattr(run, "results", None) or []:
        if not isinstance(result, dict) or result.get("name") != entry.check_name:
            continue
        first = (result.get("flaky") or {}).get("first") or {}
        text = str(
            result.get("failure_excerpt")
            or (result.get("output_tail") if not result.get("flaky") else "")
            or first.get("output_tail")
            or ""
        ).strip()
        if text:
            lines += ["", "What the run printed:", "", text[-2000:]]
        break
    lines += ["", f"Done when {test} passes on main."]
    if entry.kind == FLAKY:
        lines.append(
            "A flaky test is made deterministic under load (wait for the event it means, not a "
            "fixed time; a fake clock; no shared-state race). Do not quarantine or weaken it."
        )
    return title[:256], "\n".join(lines)[:10000]


async def _open_fix_task_for(
    session: AsyncSession, project_id: str, test: str, check: str
) -> Optional[str]:
    """An open fix task that already names *test* (FR-5's deduplication): one owning another entry
    for it, or one the Hub filed before the list existed."""
    from . import flaky_tests

    query = select(KnownFailingTest.fix_task_id).where(
        KnownFailingTest.project_id == project_id,
        KnownFailingTest.test == test,
        KnownFailingTest.fix_task_id.is_not(None),
    )
    if not test:
        # A whole check is named by its check alone.
        query = query.where(KnownFailingTest.check_name == check)
    for task_id in (await session.execute(query)).scalars().all():
        task = await session.get(Task, task_id)
        if task is not None and task.status not in _CLOSED:
            return task.id
    if test:
        filed = await flaky_tests.fix_tasks_by_test(session, project_id, open_only=True)
        return filed.get(flaky_tests.normalised_test(test))
    return None


async def _file_fix_task(
    session: AsyncSession, entry: KnownFailingTest, *, run: Any, found_by: Optional[Task]
) -> str:
    """Create *entry*'s fix task in *session* and commit it with the entry (FR-5, FR-6): pending,
    on no loop or build, never started."""
    from . import flaky_tests
    from .api.v1.tasks import create_task_for_actor
    from .schemas.tasks import TaskCreate
    from .task_transitions import operator
    from .utils import persist_event

    title, description = fix_task_text(entry, run=run, found_by=found_by)
    assignee = await owner_of(session, found_by)

    async def recorded(task: Task) -> None:
        # In the task's own commit: a fix task without an entry pointing at it never exists. No
        # requirement and no evidence, so approving it merges its branch tip.
        task.merges_branch_tip = True
        entry.fix_task_id = task.id
        await persist_event(
            session,
            entry.project_id,
            flaky_tests.FIX_TASK_EVENT,
            {
                "task_id": task.id,
                "tests": [entry.test] if entry.test else [],
                "kinds": {entry.test: entry.kind} if entry.test else {},
                "checks": [entry.check_name],
                "run_id": getattr(run, "id", None),
                "main_sha": getattr(run, "main_sha", None),
                "found_by": found_by.id if found_by is not None else None,
                "entry_id": entry.id,
            },
            commit=False,
        )

    created = await create_task_for_actor(
        # `pending`, not `assigned`: a task created assigned outside a flow is started for its
        # assignee at once (`assigned_task_start`), and these wait for the operator (FR-6).
        TaskCreate(
            title=title,
            description=description,
            priority="high",
            status="pending",
            assignee=assignee,
        ),
        project_id=entry.project_id,
        assigner=None,
        created_by_run_id=None,
        actor=operator(),
        session=session,
        before_commit=recorded,
    )
    return created.id


def _note_on(task: Task, line: str) -> None:
    """Add *line* to *task*'s notes, keeping what they held."""
    notes = task.notes
    if notes is None or notes == "":
        task.notes = line
    elif isinstance(notes, str):
        task.notes = f"{notes}\n\n{line}"
    elif isinstance(notes, list):
        task.notes = [*notes, line]
    else:
        task.notes = f"{notes}\n\n{line}"


# --- recording a run -----------------------------------------------------------------------------


@dataclass
class _Added:
    entry: KnownFailingTest
    run: Any
    found_by: Optional[Task]


async def record_run(run_id: str, *, on_main: Optional[str] = None) -> List[str]:
    """Read one ended run into the list. *run_id* is a `TaskCheckRun` or a `MainCheckRun`; *on_main*
    is the main commit whose tree it ran on, where it was a run on main's tree (a `MainCheckRun`
    always is). Returns the ids of the entries it added. Never raises.

    Idempotent per run: reading the same run twice (a landing batch's run is read when the batch
    is decided and again once it lands) counts each pass once and adds nothing twice."""
    try:
        async with _lock():
            return await _record_run(run_id, on_main=on_main)
    except Exception:  # noqa: BLE001 -- the run's own record holds what it found
        logger.warning(
            "could not read check run %s into the known-failing list", run_id, exc_info=True
        )
        return []


async def _record_run(run_id: str, *, on_main: Optional[str]) -> List[str]:
    added: List[_Added] = []
    removed: List[Tuple[KnownFailingTest, str]] = []
    async with async_session_factory() as session:
        run: Any = await session.get(TaskCheckRun, run_id)
        found_by: Optional[Task] = None
        if run is None:
            run = await session.get(MainCheckRun, run_id)
            if run is None:
                return []
            on_main = on_main or run.main_sha
        else:
            found_by = await session.get(Task, run.task_id) if on_main is None else None
        project_id = run.project_id
        listed = {(e.check_name, e.test): e for e in await entries(session, project_id)}
        sightings = {
            (s.check_name, s.test): s
            for s in (
                await session.execute(
                    select(UnlistedTestFailure).where(UnlistedTestFailure.project_id == project_id)
                )
            ).scalars()
        }
        now = _now()
        for result in run.results or []:
            if not isinstance(result, dict):
                continue
            check = str(result.get("name") or "check")
            seen = observe(result)
            # The run that executed it: a pass reused from another run is that run's, counted once.
            counted = str(result.get("reused_from") or run.id)
            # Passes and failures of what is listed (FR-4).
            for (name, test), entry in list(listed.items()):
                if name != check:
                    continue
                failed_now = (
                    (seen.whole_check_failed or bool(seen.failing) or bool(seen.flaky))
                    if not test
                    else (test in seen.failing or test in seen.flaky)
                )
                passed_now = seen.whole_check_passed if not test else test in seen.passed
                if failed_now:
                    entry.passes, entry.counted_runs, entry.last_seen = 0, [], now
                    continue
                if not passed_now:
                    continue  # the run did not run it: it does not count
                if counted not in (entry.counted_runs or []):
                    entry.passes += 1
                    entry.counted_runs = [*(entry.counted_runs or []), counted]
                commit = on_main or str(getattr(run, "main_sha", "") or "")
                if entry.kind == FAILS_ON_MAIN and on_main:
                    removed.append((entry, commit))
                elif entry.kind == FLAKY:
                    owner = (
                        await session.get(Task, entry.fix_task_id) if entry.fix_task_id else None
                    )
                    if (on_main and owner is not None and owner.status == "approved") or (
                        entry.passes >= FLAKY_PASSES_TO_CLEAR
                    ):
                        removed.append((entry, commit))
            # A pass of a test last failed while unlisted ends its streak of failures (FR-13).
            for (name, test), sighting in list(sightings.items()):
                if name == check and test in seen.passed:
                    await session.delete(sighting)
                    sightings.pop((name, test))
            # Additions: flakes from any run (FR-2); failures only from a run on main's tree (FR-3).
            new: List[Tuple[str, str]] = [(t, FLAKY) for t in seen.flaky]
            if on_main:
                new += [(t, FAILS_ON_MAIN) for t in seen.failing]
                if seen.whole_check_failed:
                    new.append((WHOLE_CHECK, FAILS_ON_MAIN))
            for test, kind in new:
                key = (check, test)
                if key in listed:
                    listed[key].last_seen = now
                    continue
                entry = KnownFailingTest(
                    id=f"kf-{short_id()}",
                    project_id=project_id,
                    check_name=check,
                    test=test,
                    kind=kind,
                    first_seen=now,
                    last_seen=now,
                    added_by_run=run.id,
                    passes=0,
                    counted_runs=[],
                )
                session.add(entry)
                listed[key] = entry
                added.append(_Added(entry=entry, run=run, found_by=found_by))
                if key in sightings:
                    await session.delete(sightings.pop(key))
        for entry, commit in removed:
            await session.delete(entry)
            owner = await session.get(Task, entry.fix_task_id) if entry.fix_task_id else None
            if owner is not None:
                # Left open: closing it is the operator's (FR-14).
                which = entry.test or f"the whole check {entry.check_name}"
                _note_on(
                    owner,
                    f"{which} ({entry.check_name}) passed on main at {commit[:12] or '?'} "
                    f"(check run {run.id}), so it came off the known-failing list.",
                )
        await session.commit()
        for item in added:
            entry = item.entry
            existing = await _open_fix_task_for(session, project_id, entry.test, entry.check_name)
            if existing is not None and existing != entry.fix_task_id:
                entry.fix_task_id = existing
                await session.commit()
                continue
            await _file_fix_task(session, entry, run=item.run, found_by=item.found_by)
    if added or removed:
        await _announce(project_id)
    return [item.entry.id for item in added]


async def _announce(project_id: str) -> None:
    from .sse import sse_manager

    try:
        await sse_manager.broadcast(project_id, SSE_EVENT, {"project_id": project_id})
    except Exception:  # noqa: BLE001
        logger.debug("known-failing broadcast failed", exc_info=True)


# --- runs on main's tree -------------------------------------------------------------------------

#: Main commits a full run is being made on now, by project: one run per commit (FR-3).
_running_on: Set[Tuple[str, str]] = set()
_pending: Set["asyncio.Task[Any]"] = set()


def schedule_main_run(project_id: str, sha: str) -> None:
    """Fire-and-forget `run_on_main`, for the main watch once it raised a move the Hub did not
    make. Never raises."""
    try:
        job = asyncio.get_running_loop().create_task(run_on_main(project_id, sha))
    except Exception:  # noqa: BLE001
        logger.warning("could not schedule the checks of main %s", sha[:12], exc_info=True)
        return
    _pending.add(job)
    job.add_done_callback(_pending.discard)


async def drain() -> None:
    """Wait for every main run scheduled (tests, and a clean shutdown)."""
    while _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)


async def _start_main_run(
    project_id: str, sha: str, reason: str, tests: Sequence[str] = ()
) -> Optional[str]:
    async with async_session_factory() as session:
        if reason == OUTSIDE_COMMIT:
            done = (
                await session.execute(
                    select(MainCheckRun.id).where(
                        MainCheckRun.project_id == project_id,
                        MainCheckRun.main_sha == sha,
                        MainCheckRun.reason == OUTSIDE_COMMIT,
                    )
                )
            ).first()
            if done is not None:
                return None
        run = MainCheckRun(
            id=f"mchk-{short_id()}",
            project_id=project_id,
            main_sha=sha,
            reason=reason,
            tests=list(tests),
            state="running",
            results=[],
            error="",
            started_at=_now(),
        )
        session.add(run)
        await session.commit()
        return run.id


async def _end_main_run(run_id: str, results: List[Dict[str, Any]], state: str, error="") -> None:
    async with async_session_factory() as session:
        run = await session.get(MainCheckRun, run_id)
        if run is None:
            return
        run.results, run.state, run.error, run.ended_at = list(results), state, error, _now()
        await session.commit()


async def run_on_main(project_id: str, sha: str) -> Optional[str]:
    """The full run of the project's checks on main commit *sha*, made once per commit (FR-3): each
    failure confirmed on the same tree, then the run read into the list as a run on main's tree.
    The run's id, or `None` where none was made (no checks, no workspace, or *sha* already run).
    Never raises."""
    from . import project_checks
    from .project_workspace import ProjectWorkspaceError, resolve_project_workspace

    key = (project_id, sha)
    if key in _running_on:
        return None
    _running_on.add(key)
    run_id: Optional[str] = None
    try:
        async with async_session_factory() as session:
            project = await session.get(Project, project_id)
            checks = project_checks.configured_checks(project)
            if not checks or project is None or not project.main_branch:
                return None
            try:
                root = (await resolve_project_workspace(session, project_id)).root
            except ProjectWorkspaceError:
                return None
        run_id = await _start_main_run(project_id, sha, OUTSIDE_COMMIT)
        if run_id is None:
            return None
        checks = await watching(project_id, checks)
        owner = f"main-{sha[:12]}"
        results: List[Dict[str, Any]] = []
        path: Optional[Path] = None
        state, error = "passed", ""
        try:
            async with project_checks._semaphore():
                path = await asyncio.to_thread(project_checks._checkout, root, owner, sha)
                tree = await asyncio.to_thread(project_checks.tree_of, root, sha)
                for check in checks:
                    result = await asyncio.to_thread(project_checks.run_one, check, path, owner)
                    if project_checks.failed(result) and not project_checks.unjudged_timeout(
                        result
                    ):
                        # No task's work is here: nothing is "touched" (`changed=[]`).
                        await asyncio.to_thread(
                            project_checks.confirm_failure, check, path, result, owner, []
                        )
                    result.update(tree=tree, check_digest=project_checks.check_digest(check))
                    results.append(result)
                    await _end_main_run(run_id, results, "running")
        except Exception as exc:  # noqa: BLE001 -- a run ends recorded
            logger.warning("the checks of main %s failed to complete", sha[:12], exc_info=True)
            state, error = "error", f"{type(exc).__name__}: {exc}"
        finally:
            if path is not None:
                await asyncio.to_thread(project_checks._remove_checkout, root, path)
        if state != "error":
            state = "failed" if any(project_checks.failed(r) for r in results) else "passed"
        await _end_main_run(run_id, results, state, error)
        if state != "error":
            await record_run(run_id, on_main=sha)
        return run_id
    except Exception:  # noqa: BLE001
        logger.warning("could not run the checks of main %s", sha[:12], exc_info=True)
        return run_id
    finally:
        _running_on.discard(key)


async def judge_unlisted(
    *,
    project_id: str,
    task_id: str,
    run_id: str,
    root: Path,
    main_sha: str,
    check: Dict[str, Any],
    result: Dict[str, Any],
) -> None:
    """A task's confirmed failure, read against the list's twice rule (FR-13). Each failing test
    not on the list is noted as this task's; one another task's run failed last, with no pass of it
    since, is re-run alone on main's tree (*main_sha*) once. Failing there, it is listed as failing
    on main, so `judge` then finds it on the list and does not hold it against this task; passing,
    both failures stand as the tasks' own. Never raises."""
    from . import project_checks

    try:
        seen = observe(result)
        if not seen.failing:
            return
        name = check["name"]
        twice: List[str] = []
        #: The runs of the other tasks that failed these tests last.
        earlier: Set[str] = set()
        async with _lock(), async_session_factory() as session:
            listed = {
                test
                for (test,) in (
                    await session.execute(
                        select(KnownFailingTest.test).where(
                            KnownFailingTest.project_id == project_id,
                            KnownFailingTest.check_name == name,
                        )
                    )
                ).all()
            }
            for test in seen.failing:
                if test in listed:
                    continue
                sighting = (
                    (
                        await session.execute(
                            select(UnlistedTestFailure).where(
                                UnlistedTestFailure.project_id == project_id,
                                UnlistedTestFailure.check_name == name,
                                UnlistedTestFailure.test == test,
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                if sighting is not None and sighting.task_id != task_id:
                    twice.append(test)
                    earlier.add(sighting.run_id)
                if sighting is None:
                    sighting = UnlistedTestFailure(
                        id=f"utf-{short_id()}",
                        project_id=project_id,
                        check_name=name,
                        test=test,
                        task_id=task_id,
                        run_id=run_id,
                    )
                    session.add(sighting)
                sighting.task_id, sighting.run_id, sighting.at = task_id, run_id, _now()
            await session.commit()
        if not twice:
            return
        narrowed = project_checks.rerun_check(check, twice)
        if narrowed is None:
            return  # it cannot be run alone: the failures stand as the task's
        main_run = await _start_main_run(project_id, main_sha, SINGLE_TEST, twice)
        if main_run is None:
            return
        owner = f"{task_id}.single"
        path: Optional[Path] = None
        try:
            path = await asyncio.to_thread(project_checks._checkout, root, owner, main_sha)
            on_main = await asyncio.to_thread(project_checks.run_one, narrowed, path, owner)
        except Exception as exc:  # noqa: BLE001
            await _end_main_run(main_run, [], "error", f"{type(exc).__name__}: {exc}")
            raise
        finally:
            if path is not None:
                await asyncio.to_thread(project_checks._remove_checkout, root, path)
        recorded = {**on_main, "name": name, "narrowed": True}
        if project_checks.reproduces_a_test_failure(on_main):
            # These ids failed for two tasks and now on main's tree: that is their confirmation,
            # and the list reads it as a confirmed failure on main (FR-3).
            recorded["confirmed"] = {"how": "tests", "tests": twice}
        await _end_main_run(
            main_run, [recorded], "failed" if project_checks.failed(on_main) else "passed"
        )
        await record_run(main_run, on_main=main_sha)
        await _judge_again(project_id, sorted(earlier))
    except Exception:  # noqa: BLE001 -- the task's own result stands without it
        logger.warning("could not apply the twice rule to %s's check run", task_id, exc_info=True)


async def _judge_again(project_id: str, run_ids: Sequence[str]) -> None:
    """The other task's run the twice rule compared with, judged again now that the list holds what
    main fails: its record then says the failure is not that task's, so a re-check or a later
    approval does not hold it against it (FR-13). Where the failure already sent that task back
    (it was the task's when its run ended, FR-7), the task is left where it is and gains a note
    that the failure is now on the list, so its author can complete it again unchanged."""
    from .project_checks import own_failure

    if not run_ids:
        return
    async with async_session_factory() as session:
        listed: Dict[str, List[Dict[str, Any]]] = {}
        for row in await entries(session, project_id):
            listed.setdefault(row.check_name, []).append(snapshot(row))
        for run_id in run_ids:
            run = await session.get(TaskCheckRun, run_id)
            if run is None:
                continue
            results = [dict(r) if isinstance(r, dict) else r for r in run.results or []]
            for result in results:
                if isinstance(result, dict):
                    judge_result(result, listed.get(str(result.get("name") or ""), []))
            run.results = results
            task = await session.get(Task, run.task_id)
            if task is not None and task.status == "revision_needed" and not own_failure(results):
                _note_on(
                    task,
                    f"The failure check run {run.id} sent this task back for is now on the "
                    "project's known-failing list as failing on main, so it is not this task's: "
                    "completing it again does not hold it against the work.",
                )
        await session.commit()


# --- the gates' question: is this failure the work's? (FR-7) -------------------------------------


def snapshot(entry: KnownFailingTest) -> Dict[str, Any]:
    """An entry as a result records it: what it was when a gate went past it, kept after the entry
    itself comes off the list (FR-10)."""
    return {
        "id": entry.id,
        "check": entry.check_name,
        "test": entry.test or None,
        "kind": entry.kind,
        "fix_task_id": entry.fix_task_id,
    }


async def listed_for(project_id: str, check: str) -> List[Dict[str, Any]]:
    """The entries on *project_id*'s list for *check*, as `snapshot`s. `[]` where the list cannot be
    read: then nothing is excused, and a failure stands as the work's, the safe side."""
    try:
        async with async_session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(KnownFailingTest).where(
                            KnownFailingTest.project_id == project_id,
                            KnownFailingTest.check_name == check,
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [snapshot(row) for row in rows]
    except Exception:  # noqa: BLE001
        logger.warning("could not read the known-failing list of %s", project_id, exc_info=True)
        return []


def judge_result(result: Dict[str, Any], listed: Sequence[Dict[str, Any]]) -> None:
    """Mark a failed check *result* against *listed*, its check's entries (FR-7). Runs nothing.

    Where the result names its failing tests (those that stood their confirmation re-run, and any
    in a file the work changes: `compared_tests`; else the report's `failed_tests`), each one on the
    list is not the work's and each one off it is. Where it names none -- a check that writes no
    report, or a report naming no failure -- an entry for the whole check decides it.

    Records `listed` (the entries it went past, as `snapshot`s), `shared_tests` (the listed ids),
    `own_tests` (the rest) and `preexisting`: true where every failure is on the list, which is what
    `project_checks.preexisting` and every gate reading it ask."""
    from .project_checks import failed

    if not failed(result):
        return
    named = [str(t) for t in result.get("compared_tests") or result.get("failed_tests") or [] if t]
    by_test = {str(e["test"]): e for e in listed if e.get("test")}
    if named:
        hit = [by_test[t] for t in named if t in by_test]
        own = [t for t in named if t not in by_test]
        result["listed"] = hit
        result["shared_tests"] = [str(e["test"]) for e in hit]
        result["own_tests"] = own
        result["preexisting"] = bool(hit) and not own
        return
    whole = next((e for e in listed if not e.get("test")), None)
    result["listed"] = [whole] if whole is not None else []
    result["preexisting"] = whole is not None


async def judge(
    *,
    project_id: str,
    task_id: Optional[str],
    run_id: str,
    root: Path,
    main_sha: str,
    check: Dict[str, Any],
    result: Dict[str, Any],
) -> None:
    """Whether a failed, confirmed check *result* is the work's, decided against the list (FR-7):
    for the completion gate (a task's run, *task_id*) and the landing gate (a batch's, `None`). A
    task's run first applies the twice rule (`judge_unlisted`, FR-13) -- the one run on main's tree
    either gate may make -- so a test it lists is then found on the list. Never raises."""
    if task_id is not None:
        await judge_unlisted(
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            root=root,
            main_sha=main_sha,
            check=check,
            result=result,
        )
    try:
        judge_result(result, await listed_for(project_id, str(check["name"])))
    except Exception:  # noqa: BLE001 -- unjudged: the failure stands as the work's
        logger.warning("could not judge %s against the known-failing list", run_id, exc_info=True)


def went_past(results: Optional[Sequence[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """The entries a run's *results* went past: each listed failure, once (FR-10)."""
    from .project_checks import failed

    seen: Dict[Tuple[Any, Any], Dict[str, Any]] = {}
    for result in results or []:
        if not isinstance(result, dict) or not failed(result):
            continue
        for entry in result.get("listed") or []:
            if isinstance(entry, dict):
                seen.setdefault((entry.get("check"), entry.get("test")), entry)
    return list(seen.values())
