"""The landing queue: the one writer that moves a project's main branch (`approved-work-merges-in-
batches`, slice E).

Approval records the verdict at once and queues the task's work here, its merge targets frozen at
that moment (`stage`); retrying an integration, landing a mend resolution and integrating approved
work whose evidence was accepted later queue a landing the same way. Nothing else merges into main.

**Without checks** a landing runs right after the commit that queued it, through the merge approval
always made (`task_integration.integrate`, one `merge --no-ff` per target), and the request that
queued it waits for it (`settle`), so it still answers with the integration outcome.

**With checks** queued landings land in batches, at most one batch at a time per project. Once the
oldest has waited `BATCH_GATHER_SECONDS`, up to `MAX_BATCH` are taken in queue order, prerequisites
first; their targets are merged onto main's tip with plumbing (`build_chain`), one prefix commit per
task, and the project's checks run once on the last prefix (`run_batch_checks`). On a pass main is
fast-forwarded to exactly that commit, so what lands is what was checked; a main that moved under the
batch refuses the fast-forward and the batch is built again on the new tip. A failure of the batch's
own is narrowed over the prefixes to the first task that breaks it, re-running only the failed tests,
and that task alone goes back to its author; failures main shares follow slice M's rule for the
whole batch (the Hub's override where allowed, else the operator's one reason).

**No database write transaction is open while git or a check runs.** Each state change is its own
short transaction, committed before the git that follows it, so a restart can tell what happened
(`reconcile_at_startup`): a batch left checking is queued again in order, and one that had moved
main is recorded landed from main's history, never merged twice.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from . import blocking, project_checks, task_integration
from .db.engine import async_session_factory
from .db.models import LandingBatch, Project, Task, TaskCheckRun, TaskLanding
from .utils import short_id

logger = logging.getLogger(__name__)

#: How long the oldest queued landing waits for others to join its batch: a queued approval waits at
#: most this long, against an 8-18 minute check run.
BATCH_GATHER_SECONDS = 60.0
#: At most this many tasks in one batch, which bounds narrowing at three narrowed runs.
MAX_BATCH = 8

QUEUED = "queued"
CHECKING = "checking"
LANDING = "landing"
HELD = "held"
LANDED = "landed"
NOT_LANDED = "not_landed"
SENT_BACK = "sent_back"
#: Landing states that still wait for the queue.
OPEN = (QUEUED, CHECKING, LANDING, HELD)

#: Who overrode a batch's checks (as `task_transition_service.OVERRIDE_BY_*`).
OVERRIDE_BY_HUB = "hub"
OVERRIDE_BY_OPERATOR = "operator"

SSE_EVENT = "task_landing_changed"


# --- targets -------------------------------------------------------------------------------------


def _target_dicts(targets: Optional[Iterable[Any]]) -> Optional[List[Dict[str, Any]]]:
    if targets is None:
        return None
    return [dataclasses.asdict(target) for target in targets]


def targets_of(landing: TaskLanding) -> Optional[List[task_integration.Target]]:
    if landing.targets is None:
        return None
    return [task_integration.Target(**entry) for entry in landing.targets]


def target_shas(landing: TaskLanding) -> List[str]:
    return [entry["commit_sha"] for entry in landing.targets or [] if entry.get("commit_sha")]


async def resolve_targets(
    session: AsyncSession, task: Task
) -> Optional[List[task_integration.Target]]:
    """What landing *task* would merge now, asked of git before the caller writes anything; `None`
    where the question cannot be asked (no main branch, no repository), so the landing records why
    nothing merged."""
    from . import project_workspace

    project = await session.get(Project, task.project_id)
    if project is None or not project.main_branch:
        return None
    try:
        root = (await project_workspace.resolve_project_workspace(session, task.project_id)).root
    except Exception:  # noqa: BLE001 -- the landing records the unavailable workspace
        return None
    if await blocking.run(task_integration.repository_fault, root) is not None:
        return None
    return await task_integration.merge_targets(session, task, root)


# --- staging -------------------------------------------------------------------------------------

_KICK_KEY = "landing_queue_kicks"
_RELEASE_KEY = "landing_queue_releases"


def stage(
    session: AsyncSession,
    task: Task,
    *,
    actor_kind: str,
    actor: str,
    kind: str,
    targets: Optional[Iterable[Any]],
    unchecked: bool = False,
    override_reason: Optional[str] = None,
    override_by: Optional[str] = None,
) -> TaskLanding:
    """Queue *task*'s work for landing in the caller's transaction; it is landed once that commits
    (never if it rolls back). *targets* are frozen on the row (`task_integration.Target`s)."""
    landing = TaskLanding(
        id=f"land-{short_id()}",
        project_id=task.project_id,
        task_id=task.id,
        state=QUEUED,
        kind=kind,
        targets=_target_dicts(targets),
        # The operator's override over a failed check lands ahead of the queue (D2).
        order_key=0.0 if unchecked else time.time(),
        unchecked=unchecked,
        override_reason=override_reason,
        override_by=override_by,
        actor_kind=actor_kind,
        actor=actor,
    )
    session.add(landing)
    session.sync_session.info.setdefault(_KICK_KEY, set()).add(task.project_id)
    return landing


def release_after_commit(session: AsyncSession, task: Task) -> None:
    """Remove a finished task's checkout once the caller's transaction commits: its git runs with no
    transaction open (D3). The merge targets are frozen, so release may run before the landing."""
    session.sync_session.info.setdefault(_RELEASE_KEY, []).append((task.project_id, task.id))


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    if session.in_nested_transaction():
        return
    kicks = session.info.pop(_KICK_KEY, set())
    releases = session.info.pop(_RELEASE_KEY, [])
    if not kicks and not releases:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return  # the startup reconcile and the next kick pick it up
    for project_id, task_id in releases:
        _start(project_id, _release(task_id), f"release the checkout of {task_id}")
    for project_id in kicks:
        _start(project_id, _process(project_id), f"land the queue of {project_id}")


@event.listens_for(Session, "after_transaction_end")
def _after_transaction_end(session: Session, transaction) -> None:
    if transaction.parent is None:
        session.info.pop(_KICK_KEY, None)
        session.info.pop(_RELEASE_KEY, None)


# --- background jobs -----------------------------------------------------------------------------

_jobs: Dict[str, Set["asyncio.Task[Any]"]] = {}
_timers: Dict[str, "asyncio.Task[Any]"] = {}
_locks: Dict[Tuple[int, str], asyncio.Lock] = {}


def _start(project_id: str, coro: Any, what: str) -> None:
    try:
        job = asyncio.get_running_loop().create_task(_logged(coro, what))
    except Exception:  # noqa: BLE001
        coro.close()
        logger.warning("could not %s", what, exc_info=True)
        return
    jobs = _jobs.setdefault(project_id, set())
    jobs.add(job)
    job.add_done_callback(jobs.discard)


async def _logged(coro: Any, what: str) -> None:
    try:
        await coro
    except Exception:  # noqa: BLE001 -- the queue is durable; the next kick or restart resumes it
        logger.warning("could not %s", what, exc_info=True)


def _lock(project_id: str) -> asyncio.Lock:
    key = (id(asyncio.get_running_loop()), project_id)
    lock = _locks.get(key)
    if lock is None:
        lock = _locks[key] = asyncio.Lock()
    return lock


def kick(project_id: str) -> None:
    """Look at *project_id*'s queue now (fire-and-forget; never raises)."""
    _start(project_id, _process(project_id), f"land the queue of {project_id}")


async def settle(project_id: str) -> None:
    """Wait for what a commit just started for *project_id*: its releases, and without checks its
    landings, so the request that queued them answers with their outcome. With checks this returns
    once the queue has looked (a batch waits for its gather window)."""
    for _ in range(1000):
        jobs = [job for job in _jobs.get(project_id, ()) if not job.done()]
        if not jobs:
            return
        await asyncio.gather(*jobs, return_exceptions=True)


async def drain(project_id: Optional[str] = None) -> None:
    """Land everything queued now, ignoring the gather window, and wait for it (tests, and an
    operator's "land now")."""
    for _ in range(1000):
        projects = [project_id] if project_id else list(_jobs)
        for pid in projects:
            await settle(pid)
        async with async_session_factory() as session:
            query = select(TaskLanding.project_id).where(TaskLanding.state == QUEUED)
            if project_id:
                query = query.where(TaskLanding.project_id == project_id)
            waiting = sorted(set((await session.execute(query)).scalars().all()))
        if not waiting:
            if all(not [j for j in _jobs.get(pid, ()) if not j.done()] for pid in projects):
                return
            continue
        for pid in waiting:
            await _process(pid, ignore_window=True)


def cancel_timers() -> None:
    for timer in list(_timers.values()):
        timer.cancel()
    _timers.clear()


def _arm_timer(project_id: str, seconds: float) -> None:
    current = _timers.get(project_id)
    if current is not None and not current.done():
        return

    async def _wake() -> None:
        await asyncio.sleep(max(0.0, seconds))
        _timers.pop(project_id, None)
        await _process(project_id)

    with contextlib.suppress(RuntimeError):
        _timers[project_id] = asyncio.get_running_loop().create_task(
            _logged(_wake(), f"land the queue of {project_id}")
        )


# --- the loop ------------------------------------------------------------------------------------


async def _process(project_id: str, *, ignore_window: bool = False) -> None:
    """Land what *project_id*'s queue holds, one landing or one batch at a time."""
    async with _lock(project_id):
        for _ in range(10_000):
            await _release_holds(project_id)
            async with async_session_factory() as session:
                project = await session.get(Project, project_id)
                if project is None:
                    return
                checks = project_checks.configured_checks(project)
                queued = list(
                    (
                        await session.execute(
                            select(TaskLanding)
                            .where(
                                TaskLanding.project_id == project_id,
                                TaskLanding.state == QUEUED,
                            )
                            .order_by(TaskLanding.order_key, TaskLanding.id)
                        )
                    ).scalars()
                )
            if not queued:
                return
            first = queued[0]
            if first.unchecked or not checks or not first.targets:
                # Unchecked by the operator's override, a project without checks, or nothing a
                # check could run on: the merge approval always made, one landing at a time.
                await land_by_merge(first.id)
                continue
            waited = time.time() - min(landing.order_key for landing in queued)
            if not ignore_window and waited < BATCH_GATHER_SECONDS:
                _arm_timer(project_id, BATCH_GATHER_SECONDS - waited)
                return
            if not await _run_one_batch(project_id, checks, queued):
                return


async def _release_holds(project_id: str) -> None:
    """A landing held on a prerequisite goes back to the queue once that prerequisite landed or is
    queued again (it then lands first)."""
    async with async_session_factory() as session:
        held = list(
            (
                await session.execute(
                    select(TaskLanding).where(
                        TaskLanding.project_id == project_id,
                        TaskLanding.state == HELD,
                        TaskLanding.waits_on.is_not(None),
                    )
                )
            ).scalars()
        )
        changed = False
        for landing in held:
            latest = await latest_landing(session, landing.waits_on or "")
            if latest is not None and latest.state in (QUEUED, CHECKING, LANDING, LANDED):
                landing.state, landing.waits_on, landing.reason = QUEUED, None, ""
                changed = True
        if changed:
            await session.commit()


async def latest_landing(session: AsyncSession, task_id: str) -> Optional[TaskLanding]:
    return (
        (
            await session.execute(
                select(TaskLanding)
                .where(TaskLanding.task_id == task_id)
                .order_by(TaskLanding.created_at.desc(), TaskLanding.id.desc())
                .limit(1)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .first()
    )


async def _claim(landing_ids: Sequence[str], to_state: str, batch_id: Optional[str]) -> List[str]:
    """Move each still-queued landing to *to_state* (compare-and-set) and commit; the ids moved."""
    moved: List[str] = []
    async with async_session_factory() as session:
        for landing_id in landing_ids:
            result = await session.execute(
                update(TaskLanding)
                .where(TaskLanding.id == landing_id, TaskLanding.state == QUEUED)
                .values(state=to_state, batch_id=batch_id, updated_at=_now())
                .execution_options(synchronize_session=False)
            )
            if result.rowcount:
                moved.append(landing_id)
        await session.commit()
    return moved


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- landing by merge (no checks, an unchecked override, nothing to check) -----------------------


async def land_by_merge(landing_id: str) -> List[task_integration.IntegrationResult]:
    """Land one landing with the merge approval always made, and record what happened. The git runs
    with no transaction open; the records are written once it returns."""
    from . import project_workspace
    from .builds import LANDING_NOWHERE, LANDS_NOWHERE
    from .db.models import Build

    if not await _claim([landing_id], LANDING, None):
        return []
    ti = task_integration
    async with async_session_factory() as session:
        landing = await session.get(TaskLanding, landing_id)
        task = await session.get(Task, landing.task_id) if landing is not None else None
        project = await session.get(Project, landing.project_id) if landing is not None else None
        if landing is None or task is None or project is None:
            return []
        resolution = landing.kind == "resolution"
        results: List[task_integration.IntegrationResult] = []
        root: Optional[Path] = None
        build = await session.get(Build, task.build_id) if task.build_id else None
        if build is not None and build.landing == LANDING_NOWHERE and not resolution:
            results = [ti.IntegrationResult(outcome=ti.SKIPPED, reason=LANDS_NOWHERE)]
        elif not project.main_branch:
            results = [ti.IntegrationResult(outcome=ti.SKIPPED, reason=ti.NO_MAIN_BRANCH)]
        else:
            try:
                root = (
                    await project_workspace.resolve_project_workspace(session, task.project_id)
                ).root
            except Exception as exc:  # noqa: BLE001 -- any workspace failure is a skip
                results = [
                    ti.IntegrationResult(
                        outcome=ti.SKIPPED,
                        reason=ti.WORKSPACE_UNAVAILABLE.format(error=exc),
                        target_branch=project.main_branch,
                    )
                ]
            # Whatever resolving the workspace wrote is committed before any git below.
            await session.commit()
        main_branch = project.main_branch
        if root is not None and not results:
            fault = await blocking.run(ti.repository_fault, root)
            if fault is not None:
                if await ti.repository_proof(session, task, root):
                    results = [
                        ti.IntegrationResult(
                            outcome=ti.FAILED,
                            reason=ti.GIT_UNREADABLE.format(error=fault),
                            target_branch=main_branch,
                        )
                    ]
                else:
                    results = [
                        ti.IntegrationResult(
                            outcome=ti.SKIPPED,
                            reason=ti.NOT_A_REPOSITORY,
                            target_branch=main_branch,
                        )
                    ]
        if root is not None and not results:
            targets = targets_of(landing)
            if targets is None:
                targets = await ti.merge_targets(session, task, root)
            if not targets:
                results = [
                    ti.IntegrationResult(
                        outcome=ti.SKIPPED,
                        reason=(
                            ti.NOTHING_TO_MERGE
                            if await ti.evidence_governs(session, task)
                            else ti.NO_TASK_BRANCH
                        ),
                        target_branch=main_branch,
                    )
                ]
            else:
                hub_written = await _hub_written(session, task.project_id)
                await session.commit()  # nothing staged: no transaction across the merge below
                merge_root, branch = root, main_branch
                results = await blocking.run_serialized(
                    lambda: [
                        ti.integrate(merge_root, target, branch, hub_written=hub_written)
                        for target in targets
                    ]
                )
        await _record_merge(session, landing_id, results, root)
    return results


async def _hub_written(session: AsyncSession, project_id: str) -> Set[str]:
    """The documents whose file holds only the Hub's write (F515): not an operator's edit."""
    from . import project_workspace
    from .task_transition_service import hub_written_documents

    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
    except Exception:  # noqa: BLE001 -- nothing is exempt
        return set()
    return set(await hub_written_documents(session, workspace, project_id))


async def _record_merge(
    session: AsyncSession,
    landing_id: str,
    results: List[task_integration.IntegrationResult],
    root: Optional[Path],
) -> None:
    """Write a merge landing's integration records and its state in one short transaction."""
    from .task_transition_service import _redrain_after_commit

    ti = task_integration
    landing = await session.get(TaskLanding, landing_id)
    task = await session.get(Task, landing.task_id)
    newest = await ti.newest_per_target(session, task.id)
    for result in results:
        previous = newest.get((result.commit_sha, result.target_branch))
        already = ti.ALREADY_INTEGRATED.format(
            commit=(result.commit_sha or "")[:12], target=result.target_branch
        )
        if (
            result.outcome == ti.SKIPPED
            and result.reason == already
            and previous is not None
            and (previous.outcome, previous.reason) == (ti.SKIPPED, already)
        ):
            continue  # F715: the newest record already says so
        _record(session, task, result, landing)
    landed = all(
        result.outcome == ti.MERGED
        or (
            result.outcome == ti.SKIPPED
            and result.reason
            == ti.ALREADY_INTEGRATED.format(
                commit=(result.commit_sha or "")[:12], target=result.target_branch
            )
        )
        for result in results
    )
    landing.state = LANDED if landed else NOT_LANDED
    landing.reason = "" if landed else next((r.reason for r in results if r.reason), "")
    landing.landed_sha = next((r.commit_sha for r in results if r.outcome == ti.MERGED), None)
    landing.ended_at = _now()
    merged = any(result.outcome == ti.MERGED for result in results)
    project_id = task.project_id
    if merged:
        _redrain_after_commit(session, project_id)
    await session.commit()
    await _announce(session, [landing_id])
    if merged and root is not None:
        await _refresh_reachability(project_id, root)


def _record(
    session: AsyncSession,
    task: Task,
    result: task_integration.IntegrationResult,
    landing: TaskLanding,
    *,
    batch_id: Optional[str] = None,
    override_reason: Optional[str] = None,
) -> None:
    """One integration record, and the stall it opens or ends (`stalls.py`)."""
    from . import stalls
    from .builds import LANDS_NOWHERE

    ti = task_integration
    by = landing.actor or ("operator" if landing.actor_kind == "operator" else "")
    row = ti.record(session, task, result, actor_kind=landing.actor_kind, actor=by)
    row.batch_id = batch_id
    row.override_reason = override_reason
    if result.outcome == ti.MERGED:
        stalls.resolve_task_after_commit(session, task.project_id, task.id, by=by)
    elif (
        result.outcome in (ti.SKIPPED, ti.FAILED)
        and result.reason
        != ti.ALREADY_INTEGRATED.format(
            commit=(result.commit_sha or "")[:12], target=result.target_branch
        )
        and result.reason != LANDS_NOWHERE
    ):
        cause = "integration_failed" if result.outcome == ti.FAILED else "integration_skipped"
        stalls.report_after_commit(
            session,
            task.project_id,
            cause=cause,
            subject=task.id,
            text=(
                f"{task.id} ({task.title!r}) was approved, but its merge into "
                f"{result.target_branch or 'the main branch'} {result.outcome}: "
                f"{(result.reason or '').strip()[:1500]}"
            ),
            task_id=task.id,
        )


async def _refresh_reachability(project_id: str, root: Path) -> None:
    from . import requirement_evidence

    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        await requirement_evidence.refresh_reachability(
            session, project_id, root, main_branch=project.main_branch if project else None
        )
        await session.commit()


async def _announce(session: AsyncSession, landing_ids: Sequence[str]) -> None:
    """Tell the operator's app each landing's new state (`task_landing_changed`), and record the
    ones they are notified of. Never raises."""
    from .sse import sse_manager
    from .utils import persist_event

    try:
        for landing_id in landing_ids:
            landing = await session.get(TaskLanding, landing_id)
            if landing is None:
                continue
            task = await session.get(Task, landing.task_id)
            payload = {
                "task_id": landing.task_id,
                "task_title": task.title if task is not None else landing.task_id,
                "landing_id": landing.id,
                "state": landing.state,
                "batch_id": landing.batch_id,
                "reason": (landing.reason or "")[:500],
            }
            await sse_manager.broadcast(landing.project_id, SSE_EVENT, payload)
            if landing.state in (LANDED, SENT_BACK, HELD):
                await persist_event(
                    session,
                    landing.project_id,
                    SSE_EVENT,
                    payload,
                    severity="info" if landing.state == LANDED else "warn",
                )
    except Exception:  # noqa: BLE001
        logger.debug("landing broadcast failed", exc_info=True)


# --- releasing a finished task's checkout --------------------------------------------------------


async def _release(task_id: str) -> None:
    from .task_transition_service import TERMINAL_STATUSES, release_task_workspace

    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        if task is None or task.status not in TERMINAL_STATUSES:
            return  # the move that asked for it did not stand
        await release_task_workspace(session, task)
        await session.commit()


# --- batches -------------------------------------------------------------------------------------


@dataclass
class Chain:
    """`build_chain`'s answer: one prefix commit per task merged, in order, and the tasks taken out
    because their work does not merge onto the ones before them."""

    tasks: List[str] = field(default_factory=list)
    prefixes: List[str] = field(default_factory=list)
    #: `(task_id, conflicting paths, the earlier batch tasks that touched them)`.
    conflicts: List[Tuple[str, List[str], List[str]]] = field(default_factory=list)
    #: Per task, its targets already in the base (recorded as already integrated).
    already: Dict[str, List[str]] = field(default_factory=dict)
    error: str = ""

    @property
    def conflict(self) -> Optional[Tuple[str, List[str], List[str]]]:
        return self.conflicts[0] if self.conflicts else None


def build_chain(root: Path, base: str, work: Sequence[Tuple[str, Sequence[str]]]) -> Chain:
    """Merge each task's targets onto *base* in order with plumbing only (`merge-tree`,
    `commit-tree`; no checkout or branch moves). Blocking; the caller runs it off the loop."""
    git = project_checks._git
    chain = Chain()
    tip = base
    touched: List[Tuple[str, Set[str]]] = []
    for task_id, shas in work:
        start = tip
        failed: Optional[List[str]] = None
        for sha in shas:
            if git(root, "merge-base", "--is-ancestor", sha, tip).returncode == 0:
                chain.already.setdefault(task_id, []).append(sha)
                continue
            merged = git(root, "merge-tree", "--write-tree", "--name-only", tip, sha)
            lines = merged.stdout.splitlines()
            if merged.returncode != 0 or not lines:
                paths = []
                for line in lines[1:]:
                    if not line.strip():
                        break
                    paths.append(line.strip())
                failed = paths or ["(unknown path)"]
                break
            commit = git(
                root,
                "commit-tree",
                lines[0].strip(),
                "-p",
                tip,
                "-p",
                sha,
                "-m",
                f"Integrate approved work {sha[:12]}",
            )
            if commit.returncode != 0:
                chain.error = f"git commit-tree failed: {commit.stderr.strip()[:300]}"
                return chain
            tip = commit.stdout.strip()
        if failed is not None:
            tip = start
            earlier = [other for other, paths in touched if paths & set(failed)]
            chain.conflicts.append((task_id, failed, earlier))
            continue
        changed = set(project_checks.changed_paths(root, start, tip) or [])
        touched.append((task_id, changed))
        chain.tasks.append(task_id)
        chain.prefixes.append(tip)
    return chain


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    return (
        ancestor != descendant
        and project_checks._git(
            root, "merge-base", "--is-ancestor", ancestor, descendant
        ).returncode
        == 0
    )


def order_with_prerequisites(
    root: Path, tip: str, landings: Sequence[TaskLanding]
) -> List[TaskLanding]:
    """*landings* in queue order with each prerequisite moved ahead of the tasks built on it (a task
    whose merge targets contain another's commit). Blocking."""
    shas = {
        landing.id: [s for s in target_shas(landing) if not _is_ancestor(root, s, tip) and s != tip]
        for landing in landings
    }
    needs: Dict[str, Set[str]] = {landing.id: set() for landing in landings}
    for b in landings:
        for a in landings:
            if a.id == b.id or a.task_id == b.task_id:
                continue
            if any(_is_ancestor(root, x, y) for x in shas[a.id] for y in shas[b.id]):
                needs[b.id].add(a.id)
    ordered: List[TaskLanding] = []
    placed: Set[str] = set()

    def place(landing: TaskLanding, seen: Set[str]) -> None:
        if landing.id in placed or landing.id in seen:
            return
        seen.add(landing.id)
        for other in landings:
            if other.id in needs[landing.id]:
                place(other, seen)
        placed.add(landing.id)
        ordered.append(landing)

    for landing in landings:
        place(landing, set())
    return ordered


def _sent_back_prerequisite(
    root: Path, tip: str, landing: TaskLanding, sent_back: Sequence[TaskLanding]
) -> Optional[str]:
    """The task, among those whose latest landing was sent back, whose work *landing* builds on."""
    mine = [s for s in target_shas(landing) if not _is_ancestor(root, s, tip) and s != tip]
    for other in sent_back:
        if other.task_id == landing.task_id:
            continue
        theirs = [s for s in target_shas(other) if not _is_ancestor(root, s, tip) and s != tip]
        if any(_is_ancestor(root, x, y) or x == y for x in theirs for y in mine):
            return other.task_id
    return None


async def _run_one_batch(
    project_id: str, checks: List[Dict[str, Any]], queued: List[TaskLanding]
) -> bool:
    """Build, check and land (or narrow) one batch. `False` where nothing more can be done now."""
    from . import project_workspace

    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        try:
            root = (await project_workspace.resolve_project_workspace(session, project_id)).root
        except Exception:  # noqa: BLE001 -- the merge path records the unavailable workspace
            root = None
        await session.commit()
        main_branch = project.main_branch if project is not None else None
        sent_back = []
        for landing in (
            await session.execute(
                select(TaskLanding).where(
                    TaskLanding.project_id == project_id, TaskLanding.state == SENT_BACK
                )
            )
        ).scalars():
            latest = await latest_landing(session, landing.task_id)
            if latest is not None and latest.id == landing.id:
                sent_back.append(landing)
    if root is None or not main_branch:
        for landing in queued:
            await land_by_merge(landing.id)
        return True
    tip = await blocking.run(project_checks.main_tip, root, main_branch)
    if tip is None:
        for landing in queued:
            await land_by_merge(landing.id)
        return True

    ordered = await blocking.run(order_with_prerequisites, root, tip, queued)
    waits: Dict[str, str] = {}
    for landing in ordered:
        prerequisite = await blocking.run(_sent_back_prerequisite, root, tip, landing, sent_back)
        if prerequisite is not None:
            waits[landing.id] = prerequisite
    if waits:
        await _hold_on(waits)
    chosen = [landing for landing in ordered if landing.id not in waits][:MAX_BATCH]
    if not chosen:
        return bool(waits)

    batch_id = f"lbat-{short_id()}"
    async with async_session_factory() as session:
        session.add(
            LandingBatch(
                id=batch_id,
                project_id=project_id,
                base_sha=tip,
                state="checking",
                task_ids=[landing.task_id for landing in chosen],
                prefixes=[],
                results=[],
                narrowing=[],
            )
        )
        await session.commit()
    claimed = set(await _claim([landing.id for landing in chosen], CHECKING, batch_id))
    chosen = [landing for landing in chosen if landing.id in claimed]
    async with async_session_factory() as session:
        batch = await session.get(LandingBatch, batch_id)
        batch.task_ids = [landing.task_id for landing in chosen]
        await session.commit()
        await _announce(session, [landing.id for landing in chosen])
    if not chosen:
        await _end_batch(batch_id, "failed", error="nothing left to land")
        return True

    chain = await blocking.run(
        build_chain, root, tip, [(landing.task_id, target_shas(landing)) for landing in chosen]
    )
    by_task = {landing.task_id: landing for landing in chosen}
    if chain.error:
        await _requeue([landing.id for landing in chosen])
        await _end_batch(batch_id, "failed", error=chain.error)
        return False
    for task_id, paths, earlier in chain.conflicts:
        await _send_back(
            by_task[task_id].id,
            batch_id,
            _conflict_report(task_id, paths, earlier, batch_id),
        )
    # A task built on one taken out does not land without it.
    removed = {task_id for task_id, _, _ in chain.conflicts}
    kept_tasks: List[str] = []
    kept_prefixes: List[str] = []
    for task_id, prefix in zip(chain.tasks, chain.prefixes, strict=True):
        kept_tasks.append(task_id)
        kept_prefixes.append(prefix)
    if removed:
        dependents = await blocking.run(
            _dependents_of,
            root,
            tip,
            [by_task[t] for t in removed],
            [by_task[t] for t in kept_tasks],
        )
        if dependents:
            # Built on work taken out: they wait for it, and the batch is built again without them.
            await _hold_on({by_task[t].id: waits_on for t, waits_on in dependents.items()})
            await _requeue([by_task[t].id for t in kept_tasks if t not in dependents])
            await _end_batch(batch_id, "failed", error="rebuilt without the work taken out")
            return True
    if not kept_tasks:
        await _end_batch(batch_id, "failed", error="every task in the batch was taken out")
        return True

    async with async_session_factory() as session:
        batch = await session.get(LandingBatch, batch_id)
        batch.task_ids = kept_tasks
        batch.prefixes = kept_prefixes
        batch.merged_sha = kept_prefixes[-1]
        await session.commit()

    landings = [by_task[t] for t in kept_tasks]
    outcome = await run_batch_checks(
        root, project_id, batch_id, tip, kept_prefixes[-1], checks, landings
    )
    return await _decide(
        root,
        main_branch,
        project_id,
        batch_id,
        tip,
        kept_tasks,
        kept_prefixes,
        landings,
        checks,
        outcome,
        chain,
    )


def _dependents_of(
    root: Path, tip: str, removed: Sequence[TaskLanding], kept: Sequence[TaskLanding]
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for landing in kept:
        prerequisite = _sent_back_prerequisite(root, tip, landing, removed)
        if prerequisite is not None:
            out[landing.task_id] = prerequisite
    return out


def _conflict_report(task_id: str, paths: List[str], earlier: List[str], batch_id: str) -> str:
    against = (
        "the work of " + ", ".join(earlier) + ", landed ahead of it in the same batch"
        if earlier
        else "the main branch"
    )
    return (
        f"Task {task_id}'s work does not merge cleanly onto {against} (landing batch {batch_id}): "
        f"{', '.join(paths[:10])}. Merge that work into the task's branch, resolve the conflict, "
        "and complete the task again."
    )


async def _hold_on(waits: Dict[str, str]) -> None:
    async with async_session_factory() as session:
        for landing_id, prerequisite in waits.items():
            landing = await session.get(TaskLanding, landing_id)
            if landing is None or landing.state not in (QUEUED, CHECKING):
                continue
            landing.state, landing.batch_id, landing.waits_on = HELD, None, prerequisite
            landing.reason = (
                f"its work is built on {prerequisite}'s, which has not landed: it lands after it"
            )
        await session.commit()
        await _announce(session, list(waits))


async def _requeue(landing_ids: Sequence[str]) -> None:
    """Put landings back in the queue, keeping their place (`order_key` is unchanged)."""
    if not landing_ids:
        return
    async with async_session_factory() as session:
        for landing_id in landing_ids:
            landing = await session.get(TaskLanding, landing_id)
            if landing is not None and landing.state in (CHECKING, LANDING, HELD):
                landing.state, landing.batch_id = QUEUED, None
        await session.commit()
        await _announce(session, list(landing_ids))


async def _end_batch(batch_id: str, state: str, **fields: Any) -> None:
    async with async_session_factory() as session:
        batch = await session.get(LandingBatch, batch_id)
        if batch is None:
            return
        batch.state = state
        for name, value in fields.items():
            setattr(batch, name, value)
        if state not in ("checking", "held", "landing"):
            batch.ended_at = _now()
        await session.commit()


@dataclass
class BatchChecks:
    """What one batch's check run found."""

    state: str  # passed, failed or error
    results: List[Dict[str, Any]] = field(default_factory=list)
    run_id: Optional[str] = None
    error: str = ""


async def run_batch_checks(
    root: Path,
    project_id: str,
    batch_id: str,
    base: str,
    merged: str,
    checks: List[Dict[str, Any]],
    landings: Sequence[TaskLanding],
) -> BatchChecks:
    """The project's checks, once, on *merged* (main's tip *base* with the batch's work), through
    `project_checks`' runner, semaphore, confirmation and main baseline. Recorded as a
    `TaskCheckRun` on the batch's first task, so a pass of this tree is reused like any other."""
    owner = f"batch-{batch_id}"
    run_id = f"chk-{short_id()}"
    tree = await blocking.run(project_checks.tree_of, root, merged)
    changed = await blocking.run(project_checks.changed_paths, root, base, merged)
    async with async_session_factory() as session:
        passes = await project_checks.passes_on_tree(session, project_id, tree) if tree else {}
        session.add(
            TaskCheckRun(
                id=run_id,
                project_id=project_id,
                task_id=landings[0].task_id,
                main_sha=base,
                target_shas=[sha for landing in landings for sha in target_shas(landing)],
                merged_sha=merged,
                state="running",
                results=[],
                error="",
            )
        )
        await session.commit()
    async with async_session_factory() as session:
        batch = await session.get(LandingBatch, batch_id)
        batch.check_run_id = run_id
        await session.commit()
    planned = project_checks.planned_results(checks, changed, tree, passes)
    results: List[Dict[str, Any]] = []
    path: Optional[Path] = None
    baseline = project_checks._MainBaseline(root, owner, base)
    state, error = "passed", ""
    try:
        async with project_checks._semaphore():
            for check, already in zip(checks, planned, strict=True):
                result = already or project_checks.skipped(check, changed)
                if result is None:
                    if path is None:
                        path = await asyncio.to_thread(
                            project_checks._checkout, root, owner, merged
                        )
                    result = await asyncio.to_thread(project_checks.run_one, check, path, owner)
                    if project_checks.failed(result):
                        await asyncio.to_thread(
                            project_checks.confirm_failure, check, path, result, owner, changed
                        )
                        if result.get("flaky"):
                            await _record_run(run_id, results + [result])
                            from . import flaky_tests

                            await flaky_tests.record_flake(run_id, result)
                    if project_checks.failed(result):
                        await baseline.record(check, result)
                    result.update(tree=tree, check_digest=project_checks.check_digest(check))
                results.append(result)
                await _record_run(run_id, results)
                if project_checks.failed(result) and not project_checks.preexisting(result):
                    break  # the batch's own failure decides it
    except Exception as exc:  # noqa: BLE001 -- a run ends recorded, never `running` forever
        logger.warning("the checks of batch %s failed to complete", batch_id, exc_info=True)
        state, error = "error", f"{type(exc).__name__}: {exc}"
    finally:
        if path is not None:
            await asyncio.to_thread(project_checks._remove_checkout, root, path)
        await baseline.close()
    if state != "error":
        state = "failed" if any(project_checks.failed(r) for r in results) else "passed"
    await _record_run(run_id, results, state=state, error=error)
    async with async_session_factory() as session:
        batch = await session.get(LandingBatch, batch_id)
        batch.results = results
        await session.commit()
    return BatchChecks(state=state, results=results, run_id=run_id, error=error)


async def _record_run(
    run_id: str, results: List[Dict[str, Any]], *, state: Optional[str] = None, error: str = ""
) -> None:
    async with async_session_factory() as session:
        run = await session.get(TaskCheckRun, run_id)
        if run is None:
            return
        run.results = list(results)
        if state is not None:
            run.state, run.error, run.ended_at = state, error, _now()
        await session.commit()


async def _decide(
    root: Path,
    main_branch: str,
    project_id: str,
    batch_id: str,
    base: str,
    tasks: List[str],
    prefixes: List[str],
    landings: List[TaskLanding],
    checks: List[Dict[str, Any]],
    outcome: BatchChecks,
    chain: Chain,
) -> bool:
    if outcome.state == "error":
        await _requeue([landing.id for landing in landings])
        await _end_batch(batch_id, "failed", error=outcome.error)
        return False  # the Hub could not produce a result: tried again at the next kick
    if outcome.state == "passed":
        override = await _flake_override(project_id, landings, outcome)
        return await _land_batch(
            root, main_branch, batch_id, base, landings, prefixes, len(prefixes), chain, override
        )
    own = [
        r for r in outcome.results if project_checks.failed(r) and not project_checks.preexisting(r)
    ]
    if not own:
        return await _main_shares_the_failure(
            root, main_branch, project_id, batch_id, base, landings, prefixes, chain, outcome
        )
    return await _narrow(
        root,
        main_branch,
        project_id,
        batch_id,
        base,
        tasks,
        prefixes,
        landings,
        checks,
        outcome,
        own[0],
        chain,
    )


async def _flake_override(
    project_id: str, landings: Sequence[TaskLanding], outcome: BatchChecks
) -> Optional[Tuple[str, str]]:
    """A pass that held a flake of a named test lands as before, with the Hub's override naming it
    and the flaky test's fix task filed (slice M)."""
    found = project_checks.not_the_tasks(outcome.results, excluded=await _filed_for(landings))
    if not found or not await _override_allowed(landings):
        return None
    from . import flaky_tests

    await flaky_tests.file_fix_task(outcome.run_id or "")
    return await _hub_override_reason(project_id, outcome, found), OVERRIDE_BY_HUB


async def _filed_for(landings: Sequence[TaskLanding]) -> List[str]:
    """The test ids any task in the batch was filed by the Hub to fix: never overridden on a batch
    that carries that fix task (slice M, FR-4)."""
    from . import flaky_tests

    tests: List[str] = []
    async with async_session_factory() as session:
        for landing in landings:
            task = await session.get(Task, landing.task_id)
            if task is not None:
                tests += await flaky_tests.filed_for(session, task)
    return tests


async def _override_allowed(landings: Sequence[TaskLanding]) -> bool:
    from . import requirement_gate

    async with async_session_factory() as session:
        for landing in landings:
            task = await session.get(Task, landing.task_id)
            if task is None or not await requirement_gate.automatic_override_allowed(session, task):
                return False
    return True


async def _hub_override_reason(
    project_id: str, outcome: BatchChecks, found: List[Dict[str, str]]
) -> str:
    from . import flaky_tests, requirement_gate

    async with async_session_factory() as session:
        run = await session.get(TaskCheckRun, outcome.run_id) if outcome.run_id else None
        by_test = await flaky_tests.fix_tasks_by_test(session, project_id, open_only=False)
    return requirement_gate.override_reason_for(
        {
            "run_id": outcome.run_id,
            "main_sha": run.main_sha if run is not None else None,
            "failures": found,
            "fix_tasks": {
                entry["test"]: by_test[flaky_tests._key(entry["test"])]
                for entry in found
                if flaky_tests._key(entry["test"]) in by_test
            },
        }
    )


async def _main_shares_the_failure(
    root: Path,
    main_branch: str,
    project_id: str,
    batch_id: str,
    base: str,
    landings: List[TaskLanding],
    prefixes: List[str],
    chain: Chain,
    outcome: BatchChecks,
) -> bool:
    """Every confirmed failure fails on main too: slice M's decision, once for the batch. No
    narrowing: the failure is not any task's."""
    found = project_checks.not_the_tasks(outcome.results, excluded=await _filed_for(landings))
    if found and await _override_allowed(landings):
        from . import flaky_tests

        await flaky_tests.file_fix_task(outcome.run_id or "")
        reason = await _hub_override_reason(project_id, outcome, found)
        return await _land_batch(
            root,
            main_branch,
            batch_id,
            base,
            landings,
            prefixes,
            len(prefixes),
            chain,
            (reason, OVERRIDE_BY_HUB),
        )
    why = (
        "the batch's checks fail, and they fail on main too, so the failure is not this work's; "
        "land the batch with one reason, or fix main first"
    )
    await _end_batch(batch_id, "held", error=why)
    async with async_session_factory() as session:
        for landing in landings:
            row = await session.get(TaskLanding, landing.id)
            if row is not None and row.state == CHECKING:
                row.state, row.reason = HELD, why
        await session.commit()
        await _announce(session, [landing.id for landing in landings])
    return True


async def land_held_batch(batch_id: str, reason: str) -> bool:
    """The operator lands a batch held over failures main shares, with one reason for all of it.
    `False` where the batch is not held or main moved (its tasks are queued again)."""
    async with async_session_factory() as session:
        batch = await session.get(LandingBatch, batch_id)
        if batch is None or batch.state != "held" or not batch.prefixes:
            return False
        landings = list(
            (
                await session.execute(
                    select(TaskLanding).where(
                        TaskLanding.batch_id == batch_id, TaskLanding.state == HELD
                    )
                )
            ).scalars()
        )
        project = await session.get(Project, batch.project_id)
        from . import project_workspace

        root = (await project_workspace.resolve_project_workspace(session, batch.project_id)).root
        await session.commit()
        project_id, base, prefixes = batch.project_id, batch.base_sha, list(batch.prefixes)
        main_branch = project.main_branch if project is not None else None
        order = {task_id: n for n, task_id in enumerate(batch.task_ids or [])}
        landings.sort(key=lambda landing: order.get(landing.task_id, 0))
    if not main_branch or not landings:
        return False
    async with async_session_factory() as session:
        for landing in landings:
            row = await session.get(TaskLanding, landing.id)
            row.state = CHECKING
        await session.commit()
    async with _lock(project_id):
        return await _land_batch(
            root,
            main_branch,
            batch_id,
            base,
            landings,
            prefixes,
            len(prefixes),
            Chain(),
            (reason, OVERRIDE_BY_OPERATOR),
        )


async def _land_batch(
    root: Path,
    main_branch: str,
    batch_id: str,
    base: str,
    landings: Sequence[TaskLanding],
    prefixes: Sequence[str],
    upto: int,
    chain: Chain,
    override: Optional[Tuple[str, str]],
) -> bool:
    """Fast-forward main from *base* to `prefixes[upto - 1]` -- the checked commit -- and record
    the first *upto* landings landed. Main no longer at *base*: the batch is superseded and its
    tasks queued again, to be built on the new tip."""
    ti = task_integration

    landing_set = list(landings)[:upto]
    target = prefixes[upto - 1]
    async with async_session_factory() as session:
        project_id = (await session.get(LandingBatch, batch_id)).project_id
        hub_written = await _hub_written(session, project_id)
        await session.commit()

    def _obstacle_or_tip() -> Tuple[Optional[str], Optional[str]]:
        return (
            ti.checkout_obstacle(root, main_branch, hub_written),
            project_checks.main_tip(root, main_branch),
        )

    obstacle, tip = await blocking.run(_obstacle_or_tip)
    if tip != base:
        await _requeue([landing.id for landing in landings])
        await _end_batch(
            batch_id,
            "superseded",
            error=f"the main branch moved from {base[:12]} to {(tip or '?')[:12]} before it landed",
        )
        return True
    if obstacle is not None:
        await _not_landed(batch_id, landing_set, main_branch, obstacle)
        await _requeue([landing.id for landing in list(landings)[upto:]])
        return True
    # Recorded as landing before main moves, so a restart in between finds it (`reconcile`).
    async with async_session_factory() as session:
        batch = await session.get(LandingBatch, batch_id)
        batch.state, batch.merged_sha = "landing", target
        batch.prefixes = list(prefixes)[:upto]
        if override is not None:
            batch.override_reason, batch.override_by = override
        for landing in landing_set:
            row = await session.get(TaskLanding, landing.id)
            row.state = LANDING
        await session.commit()

    def _fast_forward():
        moved = project_checks._git(root, "merge", "--ff-only", "-q", target)
        return moved

    result = await blocking.run_serialized(_fast_forward)
    if result.returncode != 0:
        why = (result.stderr or result.stdout).strip()[:2000] or "the fast-forward failed"
        now = await blocking.run(project_checks.main_tip, root, main_branch)
        if now != base:
            await _requeue([landing.id for landing in landings])
            await _end_batch(batch_id, "superseded", error=why)
            return True
        await _not_landed(batch_id, landing_set, main_branch, why, outcome=ti.FAILED)
        await _requeue([landing.id for landing in list(landings)[upto:]])
        return True
    await _record_landed(root, main_branch, batch_id, base, list(prefixes)[:upto], landing_set)
    await _requeue([landing.id for landing in list(landings)[upto:]])
    return True


async def _record_landed(
    root: Path,
    main_branch: str,
    batch_id: str,
    base: str,
    prefixes: Sequence[str],
    landings: Sequence[TaskLanding],
) -> None:
    """One short transaction: the batch landed, and one merged integration record per target for
    each landed task, with the commits that rode along."""
    ti = task_integration
    from .task_transition_service import _redrain_after_commit

    previous = [base, *prefixes[:-1]]

    def _riding() -> Dict[str, Tuple[List[str], bool]]:
        out: Dict[str, Tuple[List[str], bool]] = {}
        for landing, before in zip(landings, previous, strict=True):
            for sha in target_shas(landing):
                listed = project_checks._git(root, "rev-list", "--reverse", f"{before}..{sha}")
                commits = [line for line in listed.stdout.split() if line and line != sha]
                already = (
                    project_checks._git(root, "merge-base", "--is-ancestor", sha, before).returncode
                    == 0
                )
                out[f"{landing.id}:{sha}"] = (commits, already)
        return out

    riding = await blocking.run(_riding)
    async with async_session_factory() as session:
        batch = await session.get(LandingBatch, batch_id)
        override = batch.override_reason
        project_id = batch.project_id
        for landing, prefix in zip(landings, prefixes, strict=True):
            row = await session.get(TaskLanding, landing.id)
            task = await session.get(Task, landing.task_id)
            if row is None or task is None or row.state == LANDED:
                continue
            for entry in row.targets or []:
                sha = entry.get("commit_sha")
                commits, already = riding.get(f"{row.id}:{sha}", ([], False))
                result = ti.IntegrationResult(
                    outcome=ti.SKIPPED if already else ti.MERGED,
                    reason=(
                        ti.ALREADY_INTEGRATED.format(commit=(sha or "")[:12], target=main_branch)
                        if already
                        else ""
                    ),
                    commit_sha=sha,
                    source_branch=entry.get("branch"),
                    target_branch=main_branch,
                    rode_along=[] if already else commits,
                )
                _record(session, task, result, row, batch_id=batch_id, override_reason=override)
            row.state, row.landed_sha, row.ended_at, row.reason = LANDED, prefix, _now(), ""
            row.override_reason = row.override_reason or override
            row.override_by = row.override_by or batch.override_by
        batch.state, batch.ended_at = "landed", _now()
        _redrain_after_commit(session, project_id)
        await session.commit()
        await _announce(session, [landing.id for landing in landings])
    await _refresh_reachability(project_id, root)


async def _not_landed(
    batch_id: str,
    landings: Sequence[TaskLanding],
    main_branch: str,
    reason: str,
    *,
    outcome: str = task_integration.SKIPPED,
) -> None:
    """The batch could not move main (a dirty checkout, one parked elsewhere, a failed merge): each
    task records why, as an integration skip, and a retry queues it again."""
    async with async_session_factory() as session:
        batch = await session.get(LandingBatch, batch_id)
        for landing in landings:
            row = await session.get(TaskLanding, landing.id)
            task = await session.get(Task, landing.task_id)
            if row is None or task is None:
                continue
            for entry in row.targets or []:
                _record(
                    session,
                    task,
                    task_integration.IntegrationResult(
                        outcome=outcome,
                        reason=reason,
                        commit_sha=entry.get("commit_sha"),
                        source_branch=entry.get("branch"),
                        target_branch=main_branch,
                    ),
                    row,
                    batch_id=batch_id,
                )
            row.state, row.reason, row.ended_at = NOT_LANDED, reason, _now()
        if batch is not None:
            batch.state, batch.error, batch.ended_at = "failed", reason, _now()
        await session.commit()
        await _announce(session, [landing.id for landing in landings])


# --- narrowing a failing batch -------------------------------------------------------------------


def _failing_ids(result: Dict[str, Any]) -> List[str]:
    """The test ids a batch's own failure names: those that do not fail on main, else every
    confirmed one."""
    own = list(result.get("own_tests") or [])
    if own:
        return own
    return list(result.get("compared_tests") or result.get("failed_tests") or [])


async def _narrow(
    root: Path,
    main_branch: str,
    project_id: str,
    batch_id: str,
    base: str,
    tasks: List[str],
    prefixes: List[str],
    landings: List[TaskLanding],
    checks: List[Dict[str, Any]],
    outcome: BatchChecks,
    failing: Dict[str, Any],
    chain: Chain,
) -> bool:
    """Find the first task whose work, on the ones before it, makes the failing tests fail: binary
    search over the prefixes, running only the failed node ids (or the failing check where it cannot
    be narrowed). That task goes back to its author; the ones before it land if they already passed
    on exactly their prefix, else they and the ones after it are queued again at the head."""
    check = next(c for c in checks if c["name"] == failing.get("name"))
    ids = _failing_ids(failing)
    narrowed = project_checks.narrowed_command(check["command"], ids) if ids else None
    probe = {**check, "command": narrowed} if narrowed else check
    owner = f"batch-{batch_id}.narrow"
    log: List[Dict[str, Any]] = []

    async def fails_at(k: int) -> bool:
        path = await asyncio.to_thread(project_checks._checkout, root, owner, prefixes[k - 1])
        try:
            async with project_checks._semaphore():
                result = await asyncio.to_thread(project_checks.run_one, probe, path, owner)
        finally:
            await asyncio.to_thread(project_checks._remove_checkout, root, path)
        if narrowed:
            failing_here = project_checks.reproduces_a_test_failure(result) or (
                project_checks.failed(result)
                and not project_checks.proves_the_tests_pass(result, ids)
            )
        else:
            failing_here = project_checks.failed(result)
        log.append(
            {
                "prefix": k,
                "task": tasks[k - 1],
                "commit": prefixes[k - 1],
                "command": probe["command"],
                "tests": ids if narrowed else [],
                "exit_code": result.get("exit_code"),
                "failed": failing_here,
            }
        )
        return failing_here

    lo, hi = 1, len(prefixes)
    while lo < hi:
        mid = (lo + hi) // 2
        if await fails_at(mid):
            hi = mid
        else:
            lo = mid + 1
    culprit = lo
    async with async_session_factory() as session:
        batch = await session.get(LandingBatch, batch_id)
        batch.narrowing = log
        await session.commit()
    before = tasks[: culprit - 1]
    report = _failure_report(batch_id, outcome, failing, tasks[culprit - 1], before)
    await _send_back(landings[culprit - 1].id, batch_id, report)
    after = landings[culprit:]
    # A task after the culprit built on its work waits for it.
    dependents = await blocking.run(
        _dependents_of, root, base, [landings[culprit - 1]], list(after)
    )
    if dependents:
        by_task = {landing.task_id: landing.id for landing in after}
        await _hold_on({by_task[t]: w for t, w in dependents.items()})
    rest = [landing.id for landing in after if landing.task_id not in dependents]
    if culprit > 1 and await _passed_on(project_id, root, prefixes[culprit - 2], checks):
        await _end_batch(batch_id, "failed", error=f"{tasks[culprit - 1]} broke its checks")
        landed = await _land_batch(
            root,
            main_branch,
            batch_id,
            base,
            landings[: culprit - 1],
            prefixes,
            culprit - 1,
            chain,
            None,
        )
        await _requeue(rest)
        return landed
    await _requeue([landing.id for landing in landings[: culprit - 1]] + rest)
    await _end_batch(batch_id, "failed", error=f"{tasks[culprit - 1]} broke its checks")
    return True


async def _passed_on(
    project_id: str, root: Path, commit: str, checks: List[Dict[str, Any]]
) -> bool:
    """Whether every configured check already passed on exactly *commit*'s tree."""
    tree = await blocking.run(project_checks.tree_of, root, commit)
    if not tree:
        return False
    async with async_session_factory() as session:
        passes = await project_checks.passes_on_tree(session, project_id, tree)
    return all(project_checks.check_digest(check) in passes for check in checks)


def _failure_report(
    batch_id: str,
    outcome: BatchChecks,
    failing: Dict[str, Any],
    culprit: str,
    before: Sequence[str],
) -> str:
    ids = _failing_ids(failing)
    on = (
        "landed on " + ", ".join(before) + " in the same batch"
        if before
        else "on the main branch alone"
    )
    output = str(failing.get("failure_excerpt") or failing.get("output_tail") or "").strip()
    return (
        f"Landing batch {batch_id} found that task {culprit}'s work, {on}, makes the project's "
        f"check `{failing.get('name')}` fail"
        + (f" ({', '.join(ids)})" if ids else "")
        + f" (check run {outcome.run_id}). It goes back to its author; the rest of the batch lands "
        "without it.\n\n" + output[-project_checks.OUTPUT_TAIL_CHARS :]
    )


async def _send_back(landing_id: str, batch_id: str, report: str) -> bool:
    """The task goes back to its author (approved -> revision_needed, the operator's edge, origin
    `checks`, as slice L returns failed work), its landing recorded sent back with *report*."""
    from .run_task_binding import withdraw_review_entries_for
    from .sse import sse_manager
    from .task_transition_service import ORIGIN_CHECKS, TransitionRefusedError, apply_transition
    from .task_transitions import operator

    async with async_session_factory() as session:
        landing = await session.get(TaskLanding, landing_id)
        if landing is None:
            return False
        landing.state, landing.reason, landing.ended_at = SENT_BACK, report, _now()
        landing.batch_id = batch_id
        claimed = await session.execute(
            update(Task)
            .where(Task.id == landing.task_id, Task.status == "approved")
            .values(updated=_now())
            .execution_options(synchronize_session=False)
        )
        task = await session.get(Task, landing.task_id)
        moved = False
        if claimed.rowcount and task is not None:
            await session.refresh(task)
            try:
                await apply_transition(
                    session,
                    task,
                    "revision_needed",
                    operator(),
                    origin=ORIGIN_CHECKS,
                    verdict_reason=report,
                    note=f"landing batch {batch_id} sent it back",
                )
                task.notes = report
                await withdraw_review_entries_for(session, task)
                moved = True
            except TransitionRefusedError:
                logger.warning("could not send %s back", landing.task_id, exc_info=True)
        await session.commit()
        if moved and task is not None:
            await sse_manager.broadcast(
                task.project_id, "task_updated", {"id": task.id, "status": task.status}
            )
        await _announce(session, [landing_id])
    return moved


# --- what a task's drawer shows ------------------------------------------------------------------


async def view(session: AsyncSession, task_id: str) -> Optional[Dict[str, Any]]:
    """The task's latest landing as the drawer reads it: its state, its position in the queue, its
    batch (how long it has run, how long the previous one took), what it is held on, the commit it
    landed at, or why it was sent back."""
    landing = await latest_landing(session, task_id)
    if landing is None:
        return None
    out: Dict[str, Any] = {
        "id": landing.id,
        "state": landing.state,
        "kind": landing.kind,
        "reason": landing.reason,
        "waits_on": landing.waits_on,
        "landed_sha": landing.landed_sha,
        "override_reason": landing.override_reason,
        "batch": None,
        "position": None,
        "queued_at": landing.created_at.isoformat() if landing.created_at else None,
    }
    if landing.state == QUEUED:
        ahead = (
            await session.execute(
                select(TaskLanding.id).where(
                    TaskLanding.project_id == landing.project_id,
                    TaskLanding.state == QUEUED,
                    TaskLanding.order_key < landing.order_key,
                )
            )
        ).all()
        out["position"] = len(ahead) + 1
    if landing.batch_id:
        batch = await session.get(LandingBatch, landing.batch_id, populate_existing=True)
        if batch is not None:
            previous = (
                (
                    await session.execute(
                        select(LandingBatch)
                        .where(
                            LandingBatch.project_id == batch.project_id,
                            LandingBatch.ended_at.is_not(None),
                            LandingBatch.id != batch.id,
                            LandingBatch.state.in_(("landed", "failed")),
                        )
                        .order_by(LandingBatch.created_at.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            started = _aware(batch.created_at)
            ended = _aware(batch.ended_at) if batch.ended_at else _now()
            out["batch"] = {
                "id": batch.id,
                "state": batch.state,
                "task_ids": list(batch.task_ids or []),
                "base_sha": batch.base_sha,
                "merged_sha": batch.merged_sha,
                "check_run_id": batch.check_run_id,
                "seconds": round((ended - started).total_seconds(), 1),
                "previous_seconds": (
                    round(
                        (_aware(previous.ended_at) - _aware(previous.created_at)).total_seconds(),
                        1,
                    )
                    if previous is not None and previous.ended_at is not None
                    else None
                ),
                "override_reason": batch.override_reason,
                "override_by": batch.override_by,
                "error": batch.error,
            }
    return out


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


# --- the startup reconcile -----------------------------------------------------------------------


async def reconcile_at_startup() -> Dict[str, int]:
    """After a restart, lose and repeat nothing (FR a-restart-loses-and-repeats-nothing).

    A batch left `checking` is recorded `interrupted` and its tasks are queued again in their
    original order. A batch left `landing` -- main may or may not have moved -- is recorded landed
    if its checked commit is in main's history (with its integration records, and no second merge),
    else interrupted and queued again. A merge landing left `landing` is recorded landed where all
    its targets are in main, else queued again. Then every project with queued work is looked at."""
    from . import project_workspace

    counts = {"interrupted": 0, "landed": 0, "requeued": 0}
    async with async_session_factory() as session:
        open_batches = list(
            (
                await session.execute(
                    select(LandingBatch).where(LandingBatch.state.in_(("checking", "landing")))
                )
            ).scalars()
        )
        stray = list(
            (
                await session.execute(
                    select(TaskLanding).where(TaskLanding.state.in_((CHECKING, LANDING)))
                )
            ).scalars()
        )
        roots: Dict[str, Tuple[Optional[Path], Optional[str]]] = {}
        for project_id in {b.project_id for b in open_batches} | {s.project_id for s in stray}:
            project = await session.get(Project, project_id)
            try:
                root = (await project_workspace.resolve_project_workspace(session, project_id)).root
            except Exception:  # noqa: BLE001
                root = None
            roots[project_id] = (root, project.main_branch if project is not None else None)
        await session.commit()
    for batch in open_batches:
        root, main_branch = roots.get(batch.project_id, (None, None))
        async with async_session_factory() as session:
            landings = list(
                (
                    await session.execute(
                        select(TaskLanding).where(
                            TaskLanding.batch_id == batch.id,
                            TaskLanding.state.in_((CHECKING, LANDING)),
                        )
                    )
                ).scalars()
            )
        order = {task_id: n for n, task_id in enumerate(batch.task_ids or [])}
        landings.sort(key=lambda landing: order.get(landing.task_id, 0))
        reached = False
        if batch.state == "landing" and batch.merged_sha and root and main_branch:
            tip = await blocking.run(project_checks.main_tip, root, main_branch)
            reached = bool(tip) and (
                tip == batch.merged_sha
                or await blocking.run(_is_ancestor, root, batch.merged_sha, tip)
            )
        if reached and root and main_branch:
            await _record_landed(
                root, main_branch, batch.id, batch.base_sha, list(batch.prefixes), landings
            )
            counts["landed"] += 1
        else:
            await _requeue([landing.id for landing in landings])
            await _end_batch(
                batch.id, "interrupted", error="the Hub stopped while this batch was in progress"
            )
            counts["interrupted"] += 1
    for landing in stray:
        if landing.batch_id and landing.batch_id in {b.id for b in open_batches}:
            continue
        root, main_branch = roots.get(landing.project_id, (None, None))
        shas = target_shas(landing)
        landed = False
        if landing.state == LANDING and root and main_branch and shas:
            from . import requirement_evidence

            landed = all(
                [
                    await blocking.run(
                        requirement_evidence.is_reachable_from, root, sha, main_branch
                    )
                    is True
                    for sha in shas
                ]
            )
        if landed:
            results = [
                task_integration.IntegrationResult(
                    outcome=task_integration.MERGED,
                    commit_sha=entry.get("commit_sha"),
                    source_branch=entry.get("branch"),
                    target_branch=main_branch,
                )
                for entry in landing.targets or []
            ]
            async with async_session_factory() as session:
                row = await session.get(TaskLanding, landing.id)
                row.state = LANDING
                await _record_merge(session, landing.id, results, root)
            counts["landed"] += 1
        else:
            async with async_session_factory() as session:
                row = await session.get(TaskLanding, landing.id)
                row.state, row.batch_id = QUEUED, None
                await session.commit()
            counts["requeued"] += 1
    async with async_session_factory() as session:
        waiting = sorted(
            set(
                (
                    await session.execute(
                        select(TaskLanding.project_id).where(TaskLanding.state == QUEUED)
                    )
                )
                .scalars()
                .all()
            )
        )
    for project_id in waiting:
        kick(project_id)
    return counts
