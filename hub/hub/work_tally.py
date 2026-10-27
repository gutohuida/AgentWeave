"""The work tally: every figure about where a project's work went, from one function
(`project-stats-come-from-the-same-records`, slice G of "Flows that do not stall").

`tally` reads the records the Hub already keeps -- runs and their usage, task transitions, check runs,
evidence reviews, stalls, and slice D's builds and levels -- and answers every surface from them: the
spec page's build card, the project view (`GET /projects/{id}/stats`) and the Activity tab's spend
lanes. Nothing else sums a cost, a duration or a count over those rows (a test scans for it).

Every figure is a *row*: the same shape for a build, a spec, an agent, a model and a level. A fact
(a run, a check run, a send-back, a piece of evidence, a build's wall time) is booked once into each
dimension it has, so a spec row is the sum of its builds' rows and the four groupings' totals are equal
by construction. Role and spec are **derived** from existing records (no migration), so runs recorded
before this module existed are covered.

Money is in micros of an API-equivalent US dollar, as `turn_usage` records it. A figure no record
reports is `None`, never 0 (`usage_accounting._plus`'s rule): a run without a priced cost is counted
in `unpriced`, and Copilot's credits are summed in their own unit.
"""

from __future__ import annotations

import bisect
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import (
    Agent,
    Build,
    InboundQueueEntry,
    Loop,
    RequirementEvidence,
    Run,
    SpecDocument,
    SpecRequirement,
    Stall,
    Task,
    TaskCheckRun,
    TaskTransition,
    TurnUsage,
    WorkerInvocation,
)
from .usage_accounting import _worker_lines

MICROS = 1_000_000

#: What a run was for, first match wins (`_role`).
ROLES = ("building", "reviewing", "leading", "mending", "other")
#: Where a build's wall time went, in the order an instant is given to the first that applies.
WALL_PARTS = ("building", "reviewing", "checks", "held", "review", "waiting")
PIECE_STATES = ("accepted", "rejected", "held", "awaiting")

#: The Hub's mender (`stalls.HUB_ROLE`), restated so this module imports no scheduler code.
_MENDER_ROLE = "mender"
_AWAITING_VERDICT = ("completed", "under_review")
_SEND_BACKS = ("revision_needed", "rejected")


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class _Acc:
    """One row being summed. A key nobody reported stays absent, so it reads back as unknown."""

    __slots__ = ("v",)

    def __init__(self) -> None:
        self.v: Dict[str, Any] = {}

    def add(self, key: str, value: Any) -> None:
        if value is not None:
            self.v[key] = self.v.get(key, 0) + value

    def add_all(self, values: Dict[str, Any]) -> None:
        for key, value in values.items():
            self.add(key, value)

    def merge(self, other: "_Acc") -> "_Acc":
        self.add_all(other.v)
        return self

    def row(self) -> Dict[str, Any]:
        g = self.v.get
        roles = (*ROLES, "total")
        return {
            "runs": {r: g(f"runs.{r}", 0) for r in roles},
            "cost_micros": {r: g(f"cost.{r}") for r in roles},
            "run_seconds": {r: g(f"seconds.{r}", 0) for r in roles},
            "unpriced": g("unpriced", 0),
            "turns": g("turns", 0),
            "tokens": g("tokens"),
            "ai_nano_aiu": g("aiu"),
            "premium_requests": g("premium"),
            "wall": {p: g(f"wall.{p}", 0) for p in (*WALL_PARTS, "total")},
            "checks": {
                "runs": g("checks.runs", 0),
                "passed": g("checks.passed", 0),
                "failed": g("checks.failed", 0),
                "seconds": g("checks.seconds", 0),
            },
            "send_backs": {"made": g("sendbacks.made", 0), "received": g("sendbacks.received", 0)},
            "pieces": {s: g(f"pieces.{s}", 0) for s in PIECE_STATES},
            "beside_failing": {
                "count": g("beside.count", 0),
                "cost_micros": g("beside.cost"),
                "run_seconds": g("beside.seconds", 0),
            },
        }


class _Book:
    """Where a fact is booked: the total, its spec entry and its agent, model and level entries."""

    def __init__(self, builds: Iterable[Build]) -> None:
        self.total = _Acc()
        self.builds: Dict[str, _Acc] = {b.id: _Acc() for b in builds}
        self.before: Dict[str, _Acc] = {}
        self.nospec = _Acc()
        self.agents: Dict[Optional[str], _Acc] = {}
        self.models: Dict[Optional[str], _Acc] = {}
        self.levels: Dict[Optional[str], _Acc] = {}
        self.by_day: Dict[str, _Acc] = {}
        self.by_task: Dict[str, _Acc] = {}

    def book(
        self,
        values: Dict[str, Any],
        scope: Tuple[Optional[str], Optional[str], Optional[str]],
        agent: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        doc, build_id, level = scope
        self.total.add_all(values)
        if doc is None:
            spec = self.nospec
        elif build_id is None or build_id not in self.builds:
            spec = self.before.setdefault(doc, _Acc())
        else:
            spec = self.builds[build_id]
        spec.add_all(values)
        self.agents.setdefault(agent, _Acc()).add_all(values)
        self.models.setdefault(model, _Acc()).add_all(values)
        self.levels.setdefault(level, _Acc()).add_all(values)


_NO_SCOPE: Tuple[Optional[str], Optional[str], Optional[str]] = (None, None, None)


class _History:
    """One task's transitions in order, answering "its status at t" and "who completed it by t"."""

    def __init__(self, rows: List[Any]) -> None:
        self.rows = rows
        self.times = [_aware(r.created_at) for r in rows]

    def status_at(self, when: datetime) -> Optional[str]:
        if not self.rows:
            return None
        i = bisect.bisect_right(self.times, when)
        return self.rows[i - 1].to_status if i else self.rows[0].from_status

    def completer_before(self, sequence: Optional[int] = None, when: Optional[datetime] = None):
        """The latest move into `completed` before `sequence` (or at/before `when`), or None."""
        found = None
        for r in self.rows:
            if r.to_status != "completed":
                continue
            if sequence is not None and r.sequence >= sequence:
                break
            if when is not None and _aware(r.created_at) > when:
                break
            found = r
        return found


def _seconds(start: Optional[datetime], end: Optional[datetime]) -> int:
    if start is None or end is None or end <= start:
        return 0
    return int(round((end - start).total_seconds()))


async def tally(
    session: AsyncSession,
    project_id: str,
    *,
    since: Optional[datetime] = None,
    now: Optional[datetime] = None,
    build_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Every figure about where the project's work went, at every level, from `since` on.

    With `build_id` the same code reads only what that build can own: its tasks (and their
    transitions, check runs and evidence), the runs bound to them, and the conversations of the
    stalls and the lead that name it. `builds[build_id]` is then identical to the whole-project
    tally's; the groupings and the worker line are not computed (they would be partial).
    """
    now = _aware(now) or datetime.now(timezone.utc)
    since = _aware(since)

    async def load(*columns: Any, where: Any) -> List[Any]:
        return list((await session.execute(select(*columns).where(where))).all())

    focus = await session.get(Build, build_id) if build_id else None
    if build_id and (focus is None or focus.project_id != project_id):
        raise LookupError(f"no build {build_id!r} in project {project_id!r}")
    # The document's builds stay in view when scoped: a flow's stall is placed among them by time.
    build_where = Build.project_id == project_id
    if focus is not None:
        build_where = build_where & (Build.document_id == focus.document_id)
    builds = (
        (await session.execute(select(Build).where(build_where).order_by(Build.created_at)))
        .scalars()
        .all()
    )
    builds_by_id = {b.id: b for b in builds}
    task_where = Task.project_id == project_id
    if focus is not None:
        task_where = task_where & (Task.build_id == focus.id)
    tasks = {
        t.id: t for t in (await session.execute(select(Task).where(task_where))).scalars().all()
    }
    scoped_ids = list(tasks) if focus is not None else None
    doc_where = SpecDocument.project_id == project_id
    if focus is not None:
        doc_where = doc_where & (SpecDocument.id == focus.document_id)
    docs = {
        d.id: d
        for d in (await session.execute(select(SpecDocument).where(doc_where))).scalars().all()
    }
    menders = {
        a.name
        for a in (await session.execute(select(Agent).where(Agent.project_id == project_id)))
        .scalars()
        .all()
        if (a.config or {}).get("hub_role") == _MENDER_ROLE
    }
    loop_where = Loop.project_id == project_id
    if focus is not None:
        loop_where = loop_where & (Loop.spec_document_id == focus.document_id)
    loops = {
        row.id: row.spec_document_id
        for row in await load(Loop.id, Loop.spec_document_id, where=loop_where)
    }
    stall_where = (Stall.project_id == project_id) & Stall.conversation_id.is_not(None)
    if focus is not None:
        stall_where = stall_where & (
            Stall.task_id.in_(scoped_ids)
            | (Stall.task_id.is_(None) & Stall.loop_id.in_(list(loops)))
        )
    stalls = (
        (
            await session.execute(
                select(Stall).where(stall_where).order_by(Stall.first_seen_at, Stall.id)
            )
        )
        .scalars()
        .all()
    )
    stall_of: Dict[str, Stall] = {}
    for stall in stalls:
        stall_of.setdefault(stall.conversation_id, stall)
    lead_builds = {b.lead_conversation_id: b for b in builds if b.lead_conversation_id}
    review_where = (
        (InboundQueueEntry.project_id == project_id)
        & InboundQueueEntry.review_task_id.is_not(None)
        & InboundQueueEntry.delivered_in_run_id.is_not(None)
    )
    if focus is not None:
        review_where = review_where & InboundQueueEntry.review_task_id.in_(scoped_ids)
    review_runs = {
        row[0] for row in await load(InboundQueueEntry.delivered_in_run_id, where=review_where)
    }

    transition_where = TaskTransition.project_id == project_id
    check_where = TaskCheckRun.project_id == project_id
    if focus is not None:
        transition_where = transition_where & TaskTransition.task_id.in_(scoped_ids)
        check_where = check_where & TaskCheckRun.task_id.in_(scoped_ids)
    transitions = (
        (
            await session.execute(
                select(TaskTransition).where(transition_where).order_by(TaskTransition.sequence)
            )
        )
        .scalars()
        .all()
    )
    by_task_rows: Dict[str, List[Any]] = {}
    for tr in transitions:
        by_task_rows.setdefault(tr.task_id, []).append(tr)
    history = {tid: _History(rows) for tid, rows in by_task_rows.items()}
    checks = (
        (
            await session.execute(
                select(TaskCheckRun).where(check_where).order_by(TaskCheckRun.started_at)
            )
        )
        .scalars()
        .all()
    )
    checks_by_task: Dict[str, List[TaskCheckRun]] = {}
    for check in checks:
        checks_by_task.setdefault(check.task_id, []).append(check)

    run_where = Run.project_id == project_id
    if focus is not None:
        conversations = {s.conversation_id for s in stalls}
        if focus.lead_conversation_id:
            conversations.add(focus.lead_conversation_id)
        run_where = run_where & (
            Run.task_id.in_(scoped_ids) | Run.conversation_id.in_(list(conversations))
        )
    runs = {
        r.id: r
        for r in await load(
            Run.id,
            Run.agent,
            Run.conversation_id,
            Run.task_id,
            Run.status,
            Run.started_at,
            Run.ended_at,
            where=run_where,
        )
    }
    usage_where = TurnUsage.project_id == project_id
    if focus is not None:
        usage_where = usage_where & TurnUsage.run_id.in_(list(runs))
    usages = {
        u.run_id: u
        for u in (await session.execute(select(TurnUsage).where(usage_where))).scalars().all()
    }

    # ------------------------------------------------------------------------------------------
    # Where a piece of work belongs
    # ------------------------------------------------------------------------------------------
    def task_scope(task_id: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        task = tasks.get(task_id) if task_id else None
        if task is None:
            return _NO_SCOPE
        build = builds_by_id.get(task.build_id) if task.build_id else None
        doc = task.spec_document_id or (build.document_id if build else None)
        if doc is None:
            return _NO_SCOPE
        return doc, (build.id if build else None), (task.level or (build.level if build else None))

    def stall_scope(stall: Stall, at: datetime):
        scope = task_scope(stall.task_id)
        if scope[0] is not None:
            return scope
        doc = loops.get(stall.loop_id) if stall.loop_id else None
        if doc is None:
            return _NO_SCOPE
        mine = [b for b in builds if b.document_id == doc]
        build = next((b for b in mine if b.loop_id == stall.loop_id), None)
        if build is None:
            build = next(
                (
                    b
                    for b in reversed(mine)
                    if _aware(b.created_at) <= at
                    and (b.stopped_at is None or at <= _aware(b.stopped_at))
                ),
                None,
            )
        return doc, (build.id if build else None), (build.level if build else None)

    def run_scope(run: Any):
        scope = task_scope(run.task_id)
        if scope[0] is not None:
            return scope
        stall = stall_of.get(run.conversation_id) if run.conversation_id else None
        if stall is not None:
            scope = stall_scope(stall, _aware(run.started_at))
            if scope[0] is not None:
                return scope
        lead = lead_builds.get(run.conversation_id) if run.conversation_id else None
        if lead is not None:
            return lead.document_id, lead.id, lead.level
        return _NO_SCOPE

    def run_role(run: Any) -> str:
        if run.agent in menders:
            return "mending"
        if run.conversation_id and run.conversation_id in lead_builds:
            return "leading"
        if run.id in review_runs:
            return "reviewing"
        if run.task_id:
            hist = history.get(run.task_id)
            started = _aware(run.started_at)
            if hist is not None and hist.status_at(started) in _AWAITING_VERDICT:
                done = hist.completer_before(when=started)
                if run.agent != (done.actor_agent if done else None):
                    return "reviewing"
            return "building"
        return "other"

    def run_seconds(run: Any) -> int:
        if run.ended_at is not None:
            return _seconds(_aware(run.started_at), _aware(run.ended_at))
        if run.status == "running":
            return _seconds(_aware(run.started_at), now)
        return 0

    book = _Book(builds)

    # ------------------------------------------------------------------------------------------
    # Runs: cost, time and count by role
    # ------------------------------------------------------------------------------------------
    role_of: Dict[str, str] = {}
    for run_id, usage in usages.items():  # a usage row whose run row is gone still counts
        if run_id not in runs:
            runs[run_id] = _Orphan(run_id, usage)
    run_intervals: Dict[str, List[Tuple[datetime, Optional[datetime], str]]] = {}
    for run in runs.values():
        started = _aware(run.started_at)
        if since is not None and (started is None or started < since):
            continue
        role = run_role(run)
        role_of[run.id] = role
        scope = run_scope(run)
        secs = run_seconds(run)
        usage = usages.get(run.id)
        values: Dict[str, Any] = {
            "runs.total": 1,
            f"runs.{role}": 1,
            "seconds.total": secs,
            f"seconds.{role}": secs,
        }
        model = usage.model if usage else None
        if usage is not None:
            values["turns"] = 1
            cost = usage.api_equivalent_usd_micros
            if cost is None:
                # A run that reported Copilot credits is priced in that unit, not unpriced.
                if usage.ai_nano_aiu is None and usage.premium_requests is None:
                    values["unpriced"] = 1
            else:
                values["cost.total"] = cost
                values[f"cost.{role}"] = cost
            if usage.status == "measured":
                values["tokens"] = usage.total_tokens
            values["aiu"] = usage.ai_nano_aiu
            values["premium"] = usage.premium_requests
        book.book(values, scope, run.agent, model)
        if usage is not None:
            day = usage.observed_at.date().isoformat() if usage.observed_at else "unknown"
            spend = {"usd": usage.api_equivalent_usd_micros, "tokens": usage.total_tokens}
            _spend(book.by_day, day, spend)
            if run.task_id:
                _spend(book.by_task, run.task_id, spend, turn=True)
        if scope[1] is not None and role in ("building", "reviewing"):
            run_intervals.setdefault(scope[1], []).append(
                (
                    started,
                    (
                        _aware(run.ended_at)
                        if run.ended_at
                        else (None if run.status == "running" else started)
                    ),
                    role,
                )
            )

    def model_of(run_id: Optional[str]) -> Optional[str]:
        usage = usages.get(run_id) if run_id else None
        return usage.model if usage else None

    # ------------------------------------------------------------------------------------------
    # Check runs, on their own line
    # ------------------------------------------------------------------------------------------
    for check in checks:
        started = _aware(check.started_at)
        if since is not None and started < since:
            continue
        ended = _aware(check.ended_at)
        secs = _seconds(started, ended or (now if check.state == "running" else started))
        book.book(
            {
                "checks.runs": 1,
                "checks.seconds": secs,
                "checks.passed": 1 if check.state == "passed" else 0,
                "checks.failed": 1 if check.state == "failed" else 0,
            },
            task_scope(check.task_id),
        )

    # ------------------------------------------------------------------------------------------
    # Send-backs, once each; the reviews that sent work back beside a failing check
    # ------------------------------------------------------------------------------------------
    counted_reviews: set = set()
    for tr in transitions:
        if tr.from_status != "under_review" or tr.to_status not in _SEND_BACKS:
            continue
        when = _aware(tr.created_at)
        if since is not None and when < since:
            continue
        scope = task_scope(tr.task_id)
        scope = (scope[0], scope[1], tr.level or scope[2])
        reviewer_run = runs.get(tr.run_id) if tr.run_id else None
        reviewer = tr.actor_agent or (reviewer_run.agent if reviewer_run else None)
        book.book({"sendbacks.made": 1}, scope, reviewer, model_of(tr.run_id))
        done = history[tr.task_id].completer_before(sequence=tr.sequence)
        builder_run = done.run_id if done else None
        book.book(
            {"sendbacks.received": 1},
            scope,
            done.actor_agent if done else None,
            model_of(builder_run),
        )
        if reviewer_run is None or tr.run_id in counted_reviews:
            continue
        review_end = _aware(reviewer_run.ended_at) or when
        earlier = [
            c for c in checks_by_task.get(tr.task_id, []) if _aware(c.started_at) < review_end
        ]
        if earlier and earlier[-1].state == "failed":
            counted_reviews.add(tr.run_id)
            usage = usages.get(tr.run_id)
            book.book(
                {
                    "beside.count": 1,
                    "beside.cost": usage.api_equivalent_usd_micros if usage else None,
                    "beside.seconds": run_seconds(reviewer_run),
                },
                scope,
                reviewer_run.agent,
                model_of(tr.run_id),
            )

    # ------------------------------------------------------------------------------------------
    # Pieces of evidence, each by its own outcome
    # ------------------------------------------------------------------------------------------
    requirement_doc = (
        {}
        if focus is not None
        else {
            row.id: row.document_id
            for row in await load(
                SpecRequirement.id,
                SpecRequirement.document_id,
                where=SpecRequirement.project_id == project_id,
            )
        }
    )
    evidence_where = RequirementEvidence.project_id == project_id
    if focus is not None:
        evidence_where = evidence_where & RequirementEvidence.task_id.in_(scoped_ids)
    for piece in await load(
        RequirementEvidence.requirement_id,
        RequirementEvidence.task_id,
        RequirementEvidence.run_id,
        RequirementEvidence.actor,
        RequirementEvidence.review_state,
        RequirementEvidence.produced_at,
        where=evidence_where,
    ):
        if since is not None and _aware(piece.produced_at) < since:
            continue
        if piece.review_state not in PIECE_STATES:
            continue
        scope = task_scope(piece.task_id)
        if scope[0] is None and requirement_doc.get(piece.requirement_id):
            scope = (requirement_doc[piece.requirement_id], None, None)
        recorder = runs.get(piece.run_id) if piece.run_id else None
        book.book(
            {f"pieces.{piece.review_state}": 1},
            scope,
            recorder.agent if recorder else (piece.actor or None),
            model_of(piece.run_id),
        )

    # ------------------------------------------------------------------------------------------
    # Each build's wall time, partitioned
    # ------------------------------------------------------------------------------------------
    for build in builds:
        parts = _partition(
            build,
            [t for t in tasks.values() if t.build_id == build.id],
            history,
            checks_by_task,
            run_intervals.get(build.id, []),
            now,
            since,
        )
        if parts:
            values = {f"wall.{p}": parts[p] for p in WALL_PARTS}
            values["wall.total"] = sum(parts.values())
            book.book(values, (build.document_id, build.id, build.level))

    # ------------------------------------------------------------------------------------------
    # The Hub's own worker calls
    # ------------------------------------------------------------------------------------------
    workers_acc = _Acc()
    worker_lines = (
        [] if focus is not None else await _worker_lines(session, project_id, since=since)
    )
    for line in worker_lines:
        workers_acc.add_all(
            {
                "cost.total": line["api_equivalent_usd_micros"],
                "tokens": line["total_tokens"],
                "aiu": line["ai_nano_aiu"],
                "premium": line["premium_requests"],
            }
        )
    worker_rows = (
        []
        if focus is not None
        else (
            await session.execute(
                select(
                    WorkerInvocation.created_at,
                    WorkerInvocation.cost_usd_micros,
                    WorkerInvocation.total_tokens,
                ).where(WorkerInvocation.project_id == project_id)
            )
        ).all()
    )
    for created_at, cost, tokens in worker_rows:
        if since is not None and (created_at is None or _aware(created_at) < since):
            continue
        day = created_at.date().isoformat() if created_at else "unknown"
        _spend(book.by_day, day, {"usd": cost, "tokens": tokens}, worker_usd=cost)
    project = _Acc().merge(book.total).merge(workers_acc)

    # ------------------------------------------------------------------------------------------
    # The result
    # ------------------------------------------------------------------------------------------
    def title_of(doc_id: str) -> Tuple[str, Optional[str]]:
        doc = docs.get(doc_id)
        return ((doc.title or doc.path), doc.path) if doc else (doc_id, None)

    spec_entries = []
    for doc_id in sorted(
        {b.document_id for b in builds} | set(book.before),
        key=lambda d: (title_of(d)[0].lower(), d),
    ):
        mine = [b for b in builds if b.document_id == doc_id]
        merged = _Acc()
        for b in mine:
            merged.merge(book.builds[b.id])
        if doc_id in book.before:
            merged.merge(book.before[doc_id])
        label, path = title_of(doc_id)
        spec_entries.append(
            {
                "key": doc_id,
                "label": label,
                "path": path,
                "row": merged.row(),
                "builds": [
                    {
                        "id": b.id,
                        "state": b.state,
                        "level": b.level,
                        "driver": b.driver,
                        "created_at": _aware(b.created_at).isoformat() if b.created_at else None,
                        "row": book.builds[b.id].row(),
                    }
                    for b in mine
                ],
                "before_builds": book.before[doc_id].row() if doc_id in book.before else None,
            }
        )
    spec_entries.append(
        {
            "key": None,
            "label": "not from a spec",
            "path": None,
            "row": book.nospec.row(),
            "builds": [],
            "before_builds": None,
        }
    )

    def group(accs: Dict[Optional[str], _Acc], none_label: str) -> List[Dict[str, Any]]:
        entries = [
            {"key": key, "label": key if key is not None else none_label, "row": acc.row()}
            for key, acc in accs.items()
        ]
        return sorted(
            entries,
            key=lambda e: (
                e["key"] is None,
                -(e["row"]["cost_micros"]["total"] or 0),
                str(e["key"]),
            ),
        )

    spend = {
        "by_day": {day: acc.v for day, acc in sorted(book.by_day.items())},
        "by_task": {tid: acc.v for tid, acc in book.by_task.items()},
    }
    return {
        "since": since.isoformat() if since else None,
        "total": book.total.row(),
        "workers": workers_acc.row(),
        "project": project.row(),
        "builds": {bid: acc.row() for bid, acc in book.builds.items()},
        "groups": {
            "spec": spec_entries,
            "agent": group(book.agents, "checks and wall time"),
            "model": group(book.models, "no model recorded"),
            "level": group(book.levels, "no level recorded"),
        },
        "spend": spend,
    }


class _Orphan:
    """A usage row whose run row is gone: counted as an unbound run of its agent."""

    def __init__(self, run_id: str, usage: TurnUsage) -> None:
        self.id = run_id
        self.agent = usage.agent
        self.conversation_id = None
        self.task_id = None
        self.status = "completed"
        self.started_at = usage.observed_at
        self.ended_at = usage.observed_at


def _spend(
    into: Dict[str, "_Acc"],
    key: str,
    figures: Dict[str, Any],
    *,
    turn: bool = False,
    worker_usd: Optional[int] = None,
) -> None:
    acc = into.setdefault(key, _Acc())
    acc.add("usd", figures.get("usd"))
    acc.add("tokens", figures.get("tokens"))
    acc.add("worker_usd", worker_usd)
    if turn:
        acc.add("turns", 1)


def _partition(
    build: Build,
    build_tasks: List[Task],
    history: Dict[str, _History],
    checks_by_task: Dict[str, List[TaskCheckRun]],
    runs: List[Tuple[datetime, Optional[datetime], str]],
    now: datetime,
    since: Optional[datetime],
) -> Dict[str, int]:
    """The build's wall time split by what it was doing, by the precedence of `WALL_PARTS`.

    The span runs from the first task leaving pending to the last one's approval, or to now (to when
    the build stopped) while any task is open, and every instant of it goes to exactly one part, so
    the parts sum to the span.
    """
    ids = [t.id for t in build_tasks]
    left = [
        _aware(tr.created_at)
        for tid in ids
        for tr in (history[tid].rows if tid in history else [])
        if tr.from_status == "pending"
    ]
    if not left:
        return {}
    start = min(left)
    if all(t.status == "approved" for t in build_tasks):
        end = max(
            (
                _aware(tr.created_at)
                for tid in ids
                for tr in (history[tid].rows if tid in history else [])
                if tr.to_status == "approved"
            ),
            default=start,
        )
    else:
        end = _aware(build.stopped_at) or now
    lo = max(start, since) if since is not None else start
    if end <= lo:
        return {}

    def clip(value: Optional[datetime]) -> datetime:
        return end if value is None else min(max(value, lo), end)

    building = [(s, e) for s, e, role in runs if role == "building"]
    reviewing = [(s, e) for s, e, role in runs if role == "reviewing"]
    checking: List[Tuple[datetime, Optional[datetime]]] = []
    finished: Dict[str, List[Tuple[datetime, str]]] = {}
    for tid in ids:
        for check in checks_by_task.get(tid, []):
            began = _aware(check.started_at)
            stop = _aware(check.ended_at)
            checking.append(
                (began, stop if stop else (None if check.state == "running" else began))
            )
            if stop:
                finished.setdefault(tid, []).append((stop, check.state))
        finished.get(tid, []).sort()
    points = {lo, end}
    for tid in ids:
        points.update(
            clip(_aware(tr.created_at)) for tr in (history[tid].rows if tid in history else [])
        )
    for interval in (*building, *reviewing, *checking):
        points.update(clip(x) for x in interval if x is not None)
    for stamps in finished.values():
        points.update(clip(stop) for stop, _ in stamps)
    ordered = sorted(points)

    def running(intervals: List[Tuple[datetime, Optional[datetime]]], at: datetime) -> bool:
        return any(s <= at and (e is None or at < e) for s, e in intervals)

    seconds = dict.fromkeys(WALL_PARTS, 0.0)
    for a, b in zip(ordered, ordered[1:], strict=False):
        if b <= a:
            continue
        part = "waiting"
        if running(building, a):
            part = "building"
        elif running(reviewing, a):
            part = "reviewing"
        elif running(checking, a):
            part = "checks"
        else:
            awaiting = [
                tid
                for tid in ids
                if tid in history and history[tid].status_at(a) in _AWAITING_VERDICT
            ]
            if awaiting:
                part = "review"
                for tid in awaiting:
                    done = [x for x in finished.get(tid, []) if x[0] <= a]
                    if done and done[-1][1] == "failed":
                        part = "held"
                        break
        seconds[part] += (b - a).total_seconds()
    return {p: int(round(v)) for p, v in seconds.items()}


# ----------------------------------------------------------------------------------------------
# Shapes the surfaces draw
# ----------------------------------------------------------------------------------------------


def build_figures(whole: Dict[str, Any], build: Build) -> Dict[str, Any]:
    """The spec page's build card: `{id, runs, time, cost, ...}` from the tally's row for *build*."""
    row = whole["builds"][build.id]

    def dollars(role: str) -> Optional[float]:
        if not row["runs"][role]:
            return 0.0
        micros = row["cost_micros"][role]
        return None if micros is None else round(micros / MICROS, 2)

    return {
        "id": build.id,
        "runs": row["runs"]["total"],
        "time": {part: row["wall"][part] for part in WALL_PARTS},
        "cost": {
            "build": dollars("building"),
            "review": dollars("reviewing"),
            "lead": dollars("leading"),
            "mend": dollars("mending"),
        },
        "unpriced": row["unpriced"],
        "checks": row["checks"],
    }


def spend_by_day(whole: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The ledger's spend-by-day lane, oldest first."""
    return [
        {
            "day": day,
            "usd": _usd(figures.get("usd")),
            "worker_usd": _usd(figures.get("worker_usd")) or 0.0,
            "tokens": figures.get("tokens", 0),
        }
        for day, figures in whole["spend"]["by_day"].items()
    ]


def _usd(micros: Optional[int]) -> Optional[float]:
    return None if micros is None else round(micros / MICROS, 4)


async def running_progress(session: AsyncSession, project_id: str) -> Dict[str, Dict[str, Any]]:
    """For each document with a running build: `{id, done, total}`, the tasks of that build that are
    approved of those it covers. Keyed by document id; a document with none has no entry."""
    running = (
        (
            await session.execute(
                select(Build).where(Build.project_id == project_id, Build.state == "running")
            )
        )
        .scalars()
        .all()
    )
    progress: Dict[str, Dict[str, Any]] = {}
    for build in running:
        counts = dict(
            (
                await session.execute(
                    select(Task.status, func.count(Task.id))
                    .where(Task.build_id == build.id)
                    .group_by(Task.status)
                )
            ).all()
        )
        progress[build.document_id] = {
            "id": build.id,
            "done": int(counts.get("approved", 0)),
            "total": int(sum(counts.values())),
        }
    return progress
