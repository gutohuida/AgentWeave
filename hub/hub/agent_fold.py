"""Folding one agent (the source) into another of the same project (its profile)
(`fold-duplicate-agents-into-one-profile-with-their-history-kept`, FR-1 to FR-4, FR-6 to FR-8).

A fold is an archival with a destination (design D1): the source is archived through
`agent_lifecycle.archive` and `folded_into` names the profile. In the same transaction (D6) the
source's pool entries join the profile's pool (FR-3) and every open reference to the source is
re-pointed to the profile (FR-7). The profile's own settings are never touched (FR-2); where the
source's differ, `plan_fold` lists them so the operator drops them knowingly.

`plan_fold` is the preview and the fold's own re-check (D5): the route calls it again inside the
fold's transaction, so a preview gone stale cannot fold through a new obstruction. Nothing that
stores history is rewritten (FR-10): runs, conversations, checkpoints, messages, transitions,
evidence, and approved, rejected or finished work keep the name they were done under.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import builds
from .agent_lifecycle import archive as archive_agent_row
from .agent_pool import pool_rows, serialize_pool
from .agent_profiles import folded_map
from .db.models import (
    Agent,
    AgentPoolEntry,
    AIJob,
    Build,
    Charter,
    InboundQueueEntry,
    Loop,
    Run,
    Runner,
    SpecDocument,
    Task,
)
from .task_transition_service import agent_that_completed
from .utils import short_id

#: Task statuses whose references a fold leaves alone: the work is done, and keeps its name.
CLOSED_TASK_STATUSES = frozenset({"approved", "rejected"})

#: Task statuses in which a running build is "actively running work" under its holder (FR-6).
_ACTIVE_IN_BUILD = ("in_progress", "under_review")

#: The settings a preview compares, in the order it lists them (the design's contract).
_GRANTS = ("can_read_checkpoints", "can_recall", "can_accept_evidence", "can_admin_specs")
_PLAIN = (
    "default_permission_mode",
    "reach_grants",
    "permission_timeout_seconds",
    "question_timeout_seconds",
)


@dataclass
class FoldPlan:
    source: Agent
    profile: Agent
    refusals: List[Dict[str, Any]] = field(default_factory=list)
    setting_differences: List[Dict[str, Any]] = field(default_factory=list)
    pool_entries_added: List[Dict[str, Any]] = field(default_factory=list)
    open_work: List[Dict[str, Any]] = field(default_factory=list)
    #: The one profile setting a fold can write: a profile with no pool default takes the first
    #: added entry as its default runner. Listed so the preview shows it before confirming.
    profile_changes: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def can_fold(self) -> bool:
        return not self.refusals

    def preview(self) -> Dict[str, Any]:
        return {
            "source": self.source.name,
            "profile": self.profile.name,
            "can_fold": self.can_fold,
            "refusals": self.refusals,
            "setting_differences": self.setting_differences,
            "pool_entries_added": self.pool_entries_added,
            "open_work": self.open_work,
            "profile_changes": self.profile_changes,
        }

    def refusal_detail(self) -> Dict[str, Any]:
        return {
            "code": self.refusals[0]["code"],
            "message": " ".join(refusal["message"] for refusal in self.refusals),
            "refusals": self.refusals,
        }


def _refusal(code: str, message: str, ids: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"code": code, "message": message, "ids": list(ids or [])}


# --- refusals -------------------------------------------------------------------------------------


async def _identity_refusals(
    session: AsyncSession, source: Agent, profile: Agent
) -> List[Dict[str, Any]]:
    """FR-1: same agent, either side archived or folded, the source already somebody's profile."""
    found: List[Dict[str, Any]] = []
    if source.id == profile.id:
        found.append(
            _refusal(
                "fold_same_agent",
                f"{source.name} cannot be folded into itself; choose another agent as its profile.",
                [source.name],
            )
        )
        return found
    if source.folded_into:
        found.append(
            _refusal(
                "fold_source_folded",
                f"{source.name} was already folded into {source.folded_into}; a fold is one way.",
                [source.name],
            )
        )
    elif source.lifecycle == "archived":
        found.append(
            _refusal(
                "fold_source_archived",
                f"{source.name} is archived; only an open agent can be folded. Unarchive it first.",
                [source.name],
            )
        )
    if profile.folded_into:
        found.append(
            _refusal(
                "fold_profile_folded",
                f"{profile.name} was itself folded into {profile.folded_into}; fold straight into "
                f"{profile.folded_into} instead.",
                [profile.name],
            )
        )
    elif profile.lifecycle == "archived":
        found.append(
            _refusal(
                "fold_profile_archived",
                f"{profile.name} is archived; a profile must be an open agent.",
                [profile.name],
            )
        )
    folded_into_source = sorted(
        (
            await session.execute(
                select(Agent.name).where(
                    Agent.project_id == source.project_id, Agent.folded_into == source.name
                )
            )
        )
        .scalars()
        .all()
    )
    if folded_into_source:
        found.append(
            _refusal(
                "fold_source_is_profile",
                f"{source.name} is the profile {', '.join(folded_into_source)} "
                f"{'was' if len(folded_into_source) == 1 else 'were'} folded into, so it cannot "
                "be folded itself: a fold is one level only.",
                folded_into_source,
            )
        )
    return found


async def _busy_refusals(session: AsyncSession, source: Agent) -> List[Dict[str, Any]]:
    """FR-6: a live run, queued messages, or a running build's active task held by the source."""
    found: List[Dict[str, Any]] = []
    project_id = source.project_id
    runs = list(
        (
            await session.execute(
                select(Run.id).where(
                    Run.project_id == project_id,
                    Run.agent == source.name,
                    Run.status == "running",
                )
            )
        ).scalars()
    )
    if runs:
        found.append(
            _refusal(
                "fold_live_run",
                f"{source.name} has a run in progress ({', '.join(runs)}). Wait for it to "
                "finish, or stop it, then fold.",
                runs,
            )
        )
    queued = list(
        (
            await session.execute(
                select(InboundQueueEntry.id).where(
                    InboundQueueEntry.project_id == project_id,
                    InboundQueueEntry.agent == source.name,
                    InboundQueueEntry.state == "queued",
                )
            )
        ).scalars()
    )
    if queued:
        plural = "s" if len(queued) != 1 else ""
        found.append(
            _refusal(
                "fold_queued_messages",
                f"{source.name} has {len(queued)} queued message{plural}, and nothing delivers to "
                "a folded agent. Let them be delivered or discard them, then fold.",
                queued,
            )
        )
    active = (
        await session.execute(
            select(Task.id, Task.readable_id, Task.status, Build.id)
            .join(Build, Build.id == Task.build_id)
            .where(
                Task.project_id == project_id,
                Task.assignee == source.name,
                Task.status.in_(_ACTIVE_IN_BUILD),
                Build.state == builds.RUNNING,
            )
            .order_by(Task.created_at, Task.id)
        )
    ).all()
    if active:
        named = "; ".join(
            f"task {readable or task_id} ({status}) in build {build_id}"
            for task_id, readable, status, build_id in active
        )
        ids = sorted({build_id for *_, build_id in active}) + [row[0] for row in active]
        found.append(
            _refusal(
                "fold_build_running",
                f"A running build has work in progress under {source.name}: {named}. Let it "
                "finish or stop the build, then fold.",
                ids,
            )
        )
    return found


async def _self_check_refusals(
    session: AsyncSession, source: Agent, profile: Agent
) -> List[Dict[str, Any]]:
    """FR-8: re-pointing would leave an open task with the profile as builder and checker.

    Names resolve through the project's existing folds as well as this one, so a task whose builder
    was folded into the profile earlier and whose checker is the source is caught too. Only a case
    the fold itself creates is refused: the source must be one of the two before the fold.
    """
    project_id = source.project_id
    resolved = dict(await folded_map(session, project_id))
    resolved[source.name] = profile.name

    def as_profile(name: Optional[str]) -> Optional[str]:
        return resolved.get(name, name) if name else None

    tasks = (
        (
            await session.execute(
                select(Task)
                .where(
                    Task.project_id == project_id,
                    Task.status.not_in(CLOSED_TASK_STATUSES),
                )
                .order_by(Task.created_at, Task.id)
            )
        )
        .scalars()
        .all()
    )
    build_cache: Dict[str, Optional[Build]] = {}
    clashes: List[Task] = []
    for task in tasks:
        build: Optional[Build] = None
        if task.build_id:
            if task.build_id not in build_cache:
                build_cache[task.build_id] = await session.get(Build, task.build_id)
            build = build_cache[task.build_id]
        chosen = builds.checker_of(build, task)
        checker = (chosen[0] if chosen is not None else None) or task.checker
        if as_profile(checker) != profile.name:
            continue
        builders_named: Set[str] = set()
        if task.builder:
            builders_named.add(task.builder)
        if build is not None and isinstance(build.people, dict):
            key = task.spec_task_key or task.id
            own = ((build.people.get("tasks") or {}).get(key) or {}).get("builder")
            default = build.people.get("builder")
            if own or default:
                builders_named.add(own or default)
        # Who is recorded completing it, not the assignee: under review the assignee is the
        # reviewer, and a pending task has built nothing yet.
        completed_by = await agent_that_completed(session, task.id)
        if completed_by:
            builders_named.add(completed_by)
        if profile.name not in {as_profile(name) for name in builders_named}:
            continue
        if source.name in builders_named or checker == source.name:
            clashes.append(task)
    if not clashes:
        return []
    named = ", ".join(task.readable_id or task.id for task in clashes)
    return [
        _refusal(
            "fold_self_check",
            f"Folding {source.name} into {profile.name} would leave {profile.name} both building "
            f"and checking {named}. Give {'that task' if len(clashes) == 1 else 'those tasks'} "
            "another checker first.",
            [task.id for task in clashes],
        )
    ]


# --- what the preview shows ----------------------------------------------------------------------


async def _runner_view(session: AsyncSession, agent: Agent) -> Optional[Dict[str, Any]]:
    if not agent.runner_id:
        return None
    runner = await session.get(Runner, agent.runner_id)
    if runner is None:
        return {"runner_id": agent.runner_id, "name": None, "cli": None, "model": None}
    return {"runner_id": runner.id, "name": runner.name, "cli": runner.cli, "model": runner.model}


async def _charter_view(session: AsyncSession, agent: Agent) -> Optional[Dict[str, Any]]:
    if not agent.charter_id:
        return None
    charter = await session.get(Charter, agent.charter_id)
    return {"charter_id": agent.charter_id, "name": charter.name if charter else None}


def _checkpoint_view(agent: Agent) -> Dict[str, Any]:
    return {
        "checkpoint_mode": agent.checkpoint_mode,
        "checkpoint_threshold_mode": agent.checkpoint_threshold_mode,
        "checkpoint_threshold_value": agent.checkpoint_threshold_value,
        "checkpoint_notes_value": agent.checkpoint_notes_value,
    }


async def _setting_differences(
    session: AsyncSession, source: Agent, profile: Agent
) -> List[Dict[str, Any]]:
    """FR-2: every setting where the source differs from the profile; the profile's wins."""
    found: List[Dict[str, Any]] = []

    def differ(setting: str, mine: Any, theirs: Any) -> None:
        if mine != theirs:
            found.append({"setting": setting, "source": mine, "profile": theirs})

    differ("runner", await _runner_view(session, source), await _runner_view(session, profile))
    differ("charter", await _charter_view(session, source), await _charter_view(session, profile))
    for grant in _GRANTS:
        differ(grant, bool(getattr(source, grant)), bool(getattr(profile, grant)))
    differ(
        "default_permission_mode", source.default_permission_mode, profile.default_permission_mode
    )
    differ("reach_grants", source.reach_grants, profile.reach_grants)
    differ("checkpoint_policy", _checkpoint_view(source), _checkpoint_view(profile))
    for setting in ("permission_timeout_seconds", "question_timeout_seconds"):
        differ(setting, getattr(source, setting), getattr(profile, setting))
    return found


async def _pool_additions(
    session: AsyncSession, source: Agent, profile: Agent
) -> tuple[List[AgentPoolEntry], Dict[str, Runner]]:
    """FR-3: the source's entries the profile's pool does not hold yet, in the source's order.

    An entry whose runner is gone is left out, as `serialize_pool` leaves it out of every read.
    """
    held = {(entry.runner_id, entry.effort) for entry in await pool_rows(session, profile.id)}
    runners: Dict[str, Runner] = {}
    added: List[AgentPoolEntry] = []
    for entry in await pool_rows(session, source.id):
        key = (entry.runner_id, entry.effort)
        if key in held:
            continue
        runner = runners.get(entry.runner_id) or await session.get(Runner, entry.runner_id)
        if runner is None or runner.project_id != source.project_id:
            continue
        runners[runner.id] = runner
        held.add(key)
        added.append(entry)
    return added, runners


# --- open work (FR-7) ----------------------------------------------------------------------------


def _swap(names: Any, source: str, profile: str) -> Any:
    """*names* (a list of agent names) with *source* replaced by *profile*, each name once."""
    if not isinstance(names, list):
        return names
    out: List[Any] = []
    for name in names:
        value = profile if name == source else name
        if value not in out:
            out.append(value)
    return out


async def _open_work(
    session: AsyncSession, source: Agent, profile: Agent, *, apply: bool
) -> List[Dict[str, Any]]:
    """Every open reference to the source, re-pointed to the profile when *apply* is true.

    Open: a task not approved or rejected; a build not finished; a job (and the loop or flow it
    drives) that is enabled and not archived. Each item names its kind, id and the field that
    moves, as the preview lists and the fold's response and event repeat.
    """
    old, new = source.name, profile.name
    project_id = source.project_id
    items: List[Dict[str, Any]] = []

    tasks = (
        (
            await session.execute(
                select(Task)
                .where(
                    Task.project_id == project_id,
                    Task.status.not_in(CLOSED_TASK_STATUSES),
                    or_(Task.assignee == old, Task.builder == old, Task.checker == old),
                )
                .order_by(Task.created_at, Task.id)
            )
        )
        .scalars()
        .all()
    )
    for task in tasks:
        title = task.title
        for column in ("assignee", "builder", "checker"):
            if getattr(task, column) != old:
                continue
            items.append({"kind": "task", "id": task.id, "field": column, "title": title})
            if apply:
                setattr(task, column, new)
        if apply:
            # The pool entry a task's runs launch with is fixed per agent (`launch_entry`); the
            # source's entries are now the profile's, so the fixed entry is kept, re-pointed.
            for column in ("builder_entry", "checker_entry"):
                kept = getattr(task, column)
                if isinstance(kept, dict) and kept.get("agent") == old:
                    setattr(task, column, {**kept, "agent": new})

    build_rows = (
        (
            await session.execute(
                select(Build)
                .where(Build.project_id == project_id, Build.state != builds.FINISHED)
                .order_by(Build.created_at, Build.id)
            )
        )
        .scalars()
        .all()
    )
    for build in build_rows:
        document = await session.get(SpecDocument, build.document_id)
        title = f"Build of {document.title}" if document is not None else f"Build {build.id}"
        moved: List[str] = []
        for column in ("builders", "reviewers"):
            names = getattr(build, column)
            if isinstance(names, list) and old in names:
                moved.append(column)
                if apply:
                    setattr(build, column, _swap(names, old, new))
        if build.lead == old:
            moved.append("lead")
            if apply:
                build.lead = new
        people = build.people if isinstance(build.people, dict) else None
        if people is not None:
            updated = copy.deepcopy(people)
            for role in ("builder", "checker"):
                if updated.get(role) == old:
                    moved.append(f"people.{role}")
                    updated[role] = new
            for key, entry in (updated.get("tasks") or {}).items():
                if not isinstance(entry, dict):
                    continue
                for role in ("builder", "checker"):
                    if entry.get(role) == old:
                        moved.append(f"people.tasks.{key}.{role}")
                        entry[role] = new
            if apply and updated != people:
                build.people = updated
        for column in moved:
            items.append({"kind": "build", "id": build.id, "field": column, "title": title})

    jobs = (
        (
            await session.execute(
                select(AIJob)
                .where(
                    AIJob.project_id == project_id,
                    AIJob.agent == old,
                    AIJob.enabled.is_(True),
                    AIJob.archived_at.is_(None),
                )
                .order_by(AIJob.created_at, AIJob.id)
            )
        )
        .scalars()
        .all()
    )
    for job in jobs:
        loop = (
            (await session.execute(select(Loop).where(Loop.job_id == job.id).limit(1)))
            .scalars()
            .first()
        )
        if loop is None:
            items.append({"kind": "job", "id": job.id, "field": "agent", "title": job.name})
        else:
            kind = "flow" if loop.spec_document_id else "loop"
            items.append({"kind": kind, "id": loop.id, "field": "agent", "title": job.name})
        if apply:
            job.agent = new

    # A staged agent edit (`Loop.pending_agent`) applies at the loop's next firing; left naming
    # the source, it would hand the loop back to a folded name.
    staged = (
        (
            await session.execute(
                select(Loop, AIJob)
                .join(AIJob, AIJob.id == Loop.job_id)
                .where(
                    Loop.project_id == project_id,
                    Loop.pending_agent == old,
                    Loop.archived_at.is_(None),
                )
                .order_by(Loop.created_at, Loop.id)
            )
        )
        .tuples()
        .all()
    )
    for loop, job in staged:
        kind = "flow" if loop.spec_document_id else "loop"
        items.append({"kind": kind, "id": loop.id, "field": "pending_agent", "title": job.name})
        if apply:
            loop.pending_agent = new
    return items


# --- the two entry points ------------------------------------------------------------------------


async def plan_fold(session: AsyncSession, source: Agent, profile: Agent) -> FoldPlan:
    """What folding *source* into *profile* would do, and every reason it cannot (read-only)."""
    plan = FoldPlan(source=source, profile=profile)
    plan.refusals = await _identity_refusals(session, source, profile)
    if source.id == profile.id:
        return plan
    plan.refusals += await _busy_refusals(session, source)
    plan.refusals += await _self_check_refusals(session, source, profile)
    plan.setting_differences = await _setting_differences(session, source, profile)
    added, runners = await _pool_additions(session, source, profile)
    plan.pool_entries_added = serialize_pool(added, runners)
    has_default = any(entry.is_default for entry in await pool_rows(session, profile.id))
    if added and not has_default and profile.runner_id != added[0].runner_id:
        plan.profile_changes = [
            {"setting": "runner_id", "profile": profile.runner_id, "after": added[0].runner_id}
        ]
    plan.open_work = await _open_work(session, source, profile, apply=False)
    return plan


async def apply_fold(session: AsyncSession, plan: FoldPlan) -> List[Dict[str, Any]]:
    """Fold, staged on *session* for the caller's one commit (D6). Returns what was re-pointed.

    The caller has just planned and found no refusal. The profile's settings are not written; its
    pool only gains entries, its default unchanged. A profile with an empty pool (no runner) takes
    the first added entry as its default, because a pool that is not empty has exactly one.
    """
    if plan.refusals:
        raise ValueError("apply_fold called on a plan with refusals")
    source, profile = plan.source, plan.profile

    added, _ = await _pool_additions(session, source, profile)
    existing = await pool_rows(session, profile.id)
    position = max((entry.position for entry in existing), default=-1) + 1
    has_default = any(entry.is_default for entry in existing)
    for entry in added:
        row = AgentPoolEntry(
            id=f"pool-{short_id()}",
            project_id=profile.project_id,
            agent_id=profile.id,
            runner_id=entry.runner_id,
            effort=entry.effort,
            is_default=not has_default,
            position=position,
        )
        if not has_default:
            profile.runner_id = entry.runner_id
            has_default = True
        position += 1
        session.add(row)

    repointed = await _open_work(session, source, profile, apply=True)
    archive_agent_row(source)
    source.folded_into = profile.name
    return repointed
