"""The project's thread (slice thread-from-records of the red-thread roadmap).

One read of everything the Hub already records about a project, as a tree of *knots* that opens one
level at a time. The surface holds each specification document as one knot and everything outside any
document as knots of its own; a document holds its phase changes, tasks and firings; a task holds its
status changes, runs, evidence, verdicts and merges; a run holds its questions, permission decisions,
messages and evidence; a conversation holds its runs and messages.

Every item sits beneath exactly one parent (the first of its possible parents that exists), so a walk
of every knot reaches each stored record once. A knot is placed by the earliest recorded time beneath
it and its siblings are ordered by that time, then by key, so the order is the records' own and never
the reverse. Runs of four or more consecutive routine knots fold into one knot that opens to them;
consecutive items outside any document fold into one surface knot naming their span.

Nothing here writes. The tree is built from column-only reads on each call, which is what keeps a
10,000-item project inside the one-second budget (`GET /thread` pages the level it returns).
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import (
    AIJob,
    Conversation,
    EvidenceReview,
    JobRun,
    Loop,
    Message,
    PermissionRequest,
    Question,
    RequirementEvidence,
    Run,
    SpecDocument,
    SpecDocumentEvent,
    SpecDocumentMerge,
    SpecRequirement,
    Task,
    TaskIntegration,
    TaskTransition,
)

SURFACE = "surface"

#: Consecutive knots of one of these kinds fold once there are this many in a row.
FOLD_AT = 4
ROUTINE = ("run", "status-change", "message", "firing", "edit")
PLURAL = {
    "run": "runs",
    "status-change": "status changes",
    "message": "messages",
    "firing": "firings",
    "edit": "edits",
}
#: Consecutive items outside any document fold into one surface knot from this many.
GROUP_AT = 2

#: How many record names a knot lists before it says how many more there are.
RECORDS_SHOWN = 5

WORDS = {
    "document": "Document",
    "phase-change": "Phase change",
    "edit": "Edit",
    "task": "Task",
    "status-change": "Status change",
    "run": "Run",
    "evidence": "Evidence",
    "verdict": "Verdict",
    "merge": "Merge",
    "question": "Question",
    "permission": "Permission",
    "message": "Message",
    "firing": "Firing",
    "conversation": "Conversation",
    "vault-entry": "Vault entry",
    "fold": "Folded",
}

_OPERATOR = {"user", "operator"}
_ID_LIKE = re.compile(
    r"\b(?:tsk|task|run|spdoc|fct|spev|spreq|conv|perm|msg|tin|ev|jr|job|loop)-[A-Za-z0-9]{6,}\b"
)

_DOC_EVENT_TITLES = {
    "created": ("phase-change", "Document created"),
    "adopted": ("phase-change", "Document adopted"),
    "merged": ("phase-change", "Change merged into its capability"),
    "roadmap_link": ("phase-change", "Linked to a roadmap"),
    "renamed": ("edit", "Document renamed"),
    "content": ("edit", "Content edited"),
    "rerendered": ("edit", "Document redrawn"),
    "journey": ("edit", "Step of the journey recorded"),
    "system": ("edit", "System note"),
}


def human(value: Optional[str]) -> str:
    """A stored word as plain language: `under_review` becomes `under review`."""
    return re.sub(r"[_\s]+", " ", (value or "").strip())


def plain(text: Optional[str], limit: int = 140) -> str:
    """Text for a knot's face: one line, no identifiers."""
    line = _ID_LIKE.sub("an item", " ".join((text or "").split()))
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _actor(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    return "Operator" if name in _OPERATOR else name


@dataclass
class Knot:
    key: str
    kind: str
    title: str
    start: datetime
    end: datetime
    actors: List[str] = field(default_factory=list)
    link: Optional[Dict[str, Any]] = None
    records: List[str] = field(default_factory=list)
    children: List["Knot"] = field(default_factory=list)
    # Folded knots only: what they hold, and what sort of fold they are.
    members: List["Knot"] = field(default_factory=list)
    fold_of: Optional[str] = None
    record_count: int = 0
    descendants: int = 0
    parent: Optional[str] = None

    @property
    def sort_key(self) -> Tuple[datetime, str]:
        return (self.start, self.key)


def _make(
    key: str,
    kind: str,
    title: str,
    at: Optional[datetime],
    end: Optional[datetime] = None,
    *,
    actors: Iterable[Optional[str]] = (),
    link: Optional[Dict[str, Any]] = None,
    record: Optional[str] = None,
) -> Knot:
    start = aware(at) or datetime.min.replace(tzinfo=timezone.utc)
    seen: List[str] = []
    for name in actors:
        name = _actor(name)
        if name and name not in seen:
            seen.append(name)
    return Knot(
        key=key,
        kind=kind,
        title=title,
        start=start,
        end=max(start, aware(end) or start),
        actors=seen,
        link=link,
        records=[record or key],
        record_count=1,
    )


class Thread:
    """The built tree for one project: the surface's knots and a lookup by key."""

    def __init__(self) -> None:
        self.knots: Dict[str, Knot] = {}
        self.top: List[Knot] = []

    def add(self, knot: Knot) -> Knot:
        self.knots[knot.key] = knot
        return knot

    def attach(self, knot: Knot, parent_key: Optional[str]) -> None:
        parent = self.knots.get(parent_key) if parent_key else None
        if parent is None:
            self.top.append(knot)
        else:
            parent.children.append(knot)
            knot.parent = parent.key

    def settle(self) -> None:
        """Order every level, and let each knot span and count what is beneath it."""

        def walk(knot: Knot) -> None:
            for child in knot.children:
                walk(child)
            if knot.children:
                knot.start = min([knot.start] + [c.start for c in knot.children])
                knot.end = max([knot.end] + [c.end for c in knot.children])
                knot.children.sort(key=lambda c: c.sort_key)
            knot.descendants = sum(c.descendants + 1 for c in knot.children)

        for knot in self.top:
            walk(knot)
        self.top.sort(key=lambda k: k.sort_key)

    # -- levels ---------------------------------------------------------------------------

    def level(self, key: Optional[str]) -> Optional[List[Knot]]:
        """The knots one level down from `key` (the surface when None), folded; None if unknown."""
        if key is None or key == SURFACE:
            return group_surface(self.top)
        if key.startswith("fold:"):
            fold = self.find(key)
            if fold is None:
                return None
            return fold_routine(fold.members, fold.key) if fold.fold_of == "group" else fold.members
        knot = self.knots.get(key)
        return None if knot is None else fold_routine(knot.children, knot.key)

    def find(self, key: str) -> Optional[Knot]:
        """Any knot by key, including a fold (found by looking at its parent's level)."""
        if key in self.knots:
            return self.knots[key]
        if not key.startswith("fold:") or "|" not in key:
            return None
        parent_key = key[len("fold:") :].split("|", 1)[0]
        parent = None if parent_key == SURFACE else self.find(parent_key)
        if parent_key != SURFACE and parent is None:
            return None
        siblings = self.level(None if parent_key == SURFACE else parent_key) or []
        return next((k for k in siblings if k.key == key), None)

    def ancestors(self, key: str) -> Optional[List[str]]:
        """The keys to open, outermost first, to reach `key`; None if there is no such knot."""
        chain: List[str] = []
        knot = self.find(key)
        if knot is None:
            return None
        while True:
            parent = self._parent_of(knot)
            if parent is None:
                return chain[::-1]
            chain.append(parent)
            knot = self.find(parent)  # type: ignore[assignment]

    def _parent_of(self, knot: Knot) -> Optional[str]:
        if knot.kind == "fold":
            head = knot.key[len("fold:") :].split("|", 1)[0]
            return None if head == SURFACE else head
        if knot.parent is None:
            # A surface knot: beneath a surface group when one holds it.
            for sibling in group_surface(self.top):
                if (
                    sibling.kind == "fold"
                    and sibling.fold_of == "group"
                    and any(m.key == knot.key for m in sibling.members)
                ):
                    return sibling.key
            return None
        # A knot inside a routine fold is reached through the fold.
        for sibling in fold_routine(self.knots[knot.parent].children, knot.parent):
            if sibling.kind == "fold" and any(m.key == knot.key for m in sibling.members):
                return sibling.key
        return knot.parent


def _fold_node(parent_key: str, members: Sequence[Knot], fold_of: str, title: str) -> Knot:
    actors: List[str] = []
    for member in members:
        for name in member.actors:
            if name not in actors:
                actors.append(name)
    records: List[str] = []
    count = 0
    for member in members:
        count += member.record_count
        if len(records) < RECORDS_SHOWN:
            records.extend(member.records[: RECORDS_SHOWN - len(records)])
    return Knot(
        key=f"fold:{parent_key}|{members[0].key}",
        kind="fold",
        title=title,
        start=members[0].start,
        end=max(m.end for m in members),
        actors=actors,
        records=records,
        members=list(members),
        fold_of=fold_of,
        record_count=count,
        descendants=sum(m.descendants + 1 for m in members),
    )


def fold_routine(knots: Sequence[Knot], parent_key: str) -> List[Knot]:
    """Four or more consecutive knots of one routine kind become one knot naming the kind."""
    out: List[Knot] = []
    i = 0
    while i < len(knots):
        kind = knots[i].kind
        j = i
        while j < len(knots) and knots[j].kind == kind:
            j += 1
        if kind in ROUTINE and j - i >= FOLD_AT:
            run = knots[i:j]
            out.append(_fold_node(parent_key, run, kind, f"{len(run)} {PLURAL[kind]}"))
        else:
            out.extend(knots[i:j])
        i = j
    return out


def group_surface(top: Sequence[Knot]) -> List[Knot]:
    """Consecutive surface knots that are not documents fold into one knot naming how many."""
    out: List[Knot] = []
    i = 0
    while i < len(top):
        j = i
        if top[i].kind != "document":
            while j < len(top) and top[j].kind != "document":
                j += 1
        if j - i >= GROUP_AT:
            run = top[i:j]
            out.append(_fold_node(SURFACE, run, "group", f"{len(run)} items outside any document"))
            i = j
        else:
            out.append(top[i])
            i += 1
    return out


# -- building -------------------------------------------------------------------------------


async def build(
    session: AsyncSession, project_id: str, vault_entries: Sequence[Dict[str, Any]] = ()
) -> Thread:
    thread = Thread()

    async def rows(*columns: Any, where: Any = None):
        statement = select(*columns)
        if where is not None:
            statement = statement.where(where)
        return (await session.execute(statement)).all()

    docs = await rows(
        SpecDocument.id,
        SpecDocument.title,
        SpecDocument.path,
        SpecDocument.created_at,
        where=SpecDocument.project_id == project_id,
    )
    tasks = await rows(
        Task.id,
        Task.title,
        Task.assignee,
        Task.assigner,
        Task.created_at,
        Task.spec_document_id,
        where=Task.project_id == project_id,
    )
    runs = await rows(
        Run.id,
        Run.agent,
        Run.status,
        Run.task_id,
        Run.conversation_id,
        Run.started_at,
        Run.ended_at,
        where=Run.project_id == project_id,
    )
    conversations = await rows(
        Conversation.id,
        Conversation.agent,
        Conversation.title,
        Conversation.task_id,
        Conversation.created_at,
        where=Conversation.project_id == project_id,
    )
    job_names = {
        row.id: row.name
        for row in await rows(AIJob.id, AIJob.name, where=AIJob.project_id == project_id)
    }
    loop_docs = {
        row.job_id: row.spec_document_id
        for row in await rows(
            Loop.job_id, Loop.spec_document_id, where=Loop.project_id == project_id
        )
        if row.spec_document_id
    }
    requirement_docs = {
        row.id: (row.identifier, row.document_id)
        for row in await rows(
            SpecRequirement.id,
            SpecRequirement.identifier,
            SpecRequirement.document_id,
            where=SpecRequirement.project_id == project_id,
        )
    }

    doc_ids = {row.id for row in docs}
    task_ids = {row.id for row in tasks}
    run_ids = {row.id for row in runs}
    conversation_ids = {row.id for row in conversations}

    for row in docs:
        thread.add(
            _make(
                f"document:{row.id}",
                "document",
                plain(row.title) or "Untitled document",
                row.created_at,
                link={"object": "document", "id": row.id, "path": row.path},
                record=f"spec_documents:{row.id}",
            )
        )
    for row in tasks:
        thread.add(
            _make(
                f"task:{row.id}",
                "task",
                plain(row.title) or "Untitled task",
                row.created_at,
                actors=[row.assigner, row.assignee],
                link={"object": "task", "id": row.id},
                record=f"tasks:{row.id}",
            )
        )
    for row in conversations:
        thread.add(
            _make(
                f"conversation:{row.id}",
                "conversation",
                plain(row.title) or f"Conversation with {row.agent}",
                row.created_at,
                actors=["operator", row.agent],
                link={"object": "conversation", "id": row.id, "agent": row.agent},
                record=f"conversations:{row.id}",
            )
        )
    for row in runs:
        thread.add(
            _make(
                f"run:{row.id}",
                "run",
                f"{row.agent} worked ({human(row.status)})",
                row.started_at,
                row.ended_at,
                actors=[row.agent],
                link={"object": "run", "id": row.id, "agent": row.agent},
                record=f"runs:{row.id}",
            )
        )

    def doc_parent(document_id: Optional[str]) -> Optional[str]:
        return f"document:{document_id}" if document_id in doc_ids else None

    def task_parent(task_id: Optional[str]) -> Optional[str]:
        return f"task:{task_id}" if task_id in task_ids else None

    def run_parent(run_id: Optional[str]) -> Optional[str]:
        return f"run:{run_id}" if run_id in run_ids else None

    def conversation_parent(conversation_id: Optional[str]) -> Optional[str]:
        return f"conversation:{conversation_id}" if conversation_id in conversation_ids else None

    def first(*options: Optional[str]) -> Optional[str]:
        return next((o for o in options if o), None)

    # Containers hang from their own parents first, so the leaves below can find them.
    for row in tasks:
        thread.attach(thread.knots[f"task:{row.id}"], doc_parent(row.spec_document_id))
    for row in conversations:
        thread.attach(thread.knots[f"conversation:{row.id}"], task_parent(row.task_id))
    for row in runs:
        thread.attach(
            thread.knots[f"run:{row.id}"],
            first(task_parent(row.task_id), conversation_parent(row.conversation_id)),
        )
    for row in docs:
        thread.attach(thread.knots[f"document:{row.id}"], None)

    def leaf(
        key: str, kind: str, title: str, at, end=None, parent=None, *, actors=(), link=None
    ) -> None:
        knot = thread.add(
            _make(
                key,
                kind,
                title,
                at,
                end,
                actors=actors,
                link=link,
                record=key,
            )
        )
        thread.attach(knot, parent)

    for row in await rows(
        SpecDocumentEvent.id,
        SpecDocumentEvent.document_id,
        SpecDocumentEvent.kind,
        SpecDocumentEvent.actor,
        SpecDocumentEvent.detail,
        SpecDocumentEvent.created_at,
        where=SpecDocumentEvent.project_id == project_id,
    ):
        detail = row.detail if isinstance(row.detail, dict) else {}
        kind, title = _DOC_EVENT_TITLES.get(row.kind, ("edit", f"Document {human(row.kind)}"))
        if row.kind == "phase":
            kind = "phase-change"
            if detail.get("to"):
                title = f"Moved to {human(str(detail['to']))}"
            elif detail.get("explore_closed"):
                title = "Exploration closed"
            else:
                title = "Phase changed"
        leaf(
            f"document-event:{row.id}",
            kind,
            title,
            row.created_at,
            parent=doc_parent(row.document_id),
            actors=[row.actor],
        )

    for row in await rows(
        SpecDocumentMerge.id,
        SpecDocumentMerge.change_document_id,
        SpecDocumentMerge.actor,
        SpecDocumentMerge.created_at,
        where=SpecDocumentMerge.project_id == project_id,
    ):
        leaf(
            f"document-merge:{row.id}",
            "merge",
            "Change merged into its capability",
            row.created_at,
            parent=doc_parent(row.change_document_id),
            actors=[row.actor],
        )

    for row in await rows(
        TaskTransition.id,
        TaskTransition.task_id,
        TaskTransition.from_status,
        TaskTransition.to_status,
        TaskTransition.actor_agent,
        TaskTransition.actor_kind,
        TaskTransition.created_at,
        where=TaskTransition.project_id == project_id,
    ):
        leaf(
            f"transition:{row.id}",
            "status-change",
            f"Moved from {human(row.from_status)} to {human(row.to_status)}",
            row.created_at,
            parent=task_parent(row.task_id),
            actors=[row.actor_agent or ("operator" if row.actor_kind == "operator" else None)],
        )

    evidence_parent: Dict[str, Optional[str]] = {}
    evidence_task: Dict[str, Optional[str]] = {}
    run_task = {row.id: row.task_id for row in runs}
    for row in await rows(
        RequirementEvidence.id,
        RequirementEvidence.requirement_id,
        RequirementEvidence.task_id,
        RequirementEvidence.run_id,
        RequirementEvidence.actor,
        RequirementEvidence.produced_at,
        where=RequirementEvidence.project_id == project_id,
    ):
        identifier, document_id = requirement_docs.get(row.requirement_id, (None, None))
        owner_task = first(
            task_parent(row.task_id), task_parent(run_task.get(row.run_id) if row.run_id else None)
        )
        parent = first(run_parent(row.run_id), owner_task, doc_parent(document_id))
        evidence_parent[row.id] = parent
        evidence_task[row.id] = owner_task
        leaf(
            f"evidence:{row.id}",
            "evidence",
            f"Evidence for {identifier}" if identifier else "Evidence recorded",
            row.produced_at,
            parent=parent,
            actors=[row.actor],
            link={"object": "evidence", "id": row.id, "requirement": identifier},
        )

    for row in await rows(
        EvidenceReview.id,
        EvidenceReview.evidence_id,
        EvidenceReview.decision,
        EvidenceReview.actor,
        EvidenceReview.created_at,
        where=EvidenceReview.project_id == project_id,
    ):
        leaf(
            f"verdict:{row.id}",
            "verdict",
            f"Evidence {human(row.decision)}",
            row.created_at,
            parent=first(evidence_task.get(row.evidence_id), evidence_parent.get(row.evidence_id)),
            actors=[row.actor],
        )

    for row in await rows(
        TaskIntegration.id,
        TaskIntegration.task_id,
        TaskIntegration.outcome,
        TaskIntegration.actor,
        TaskIntegration.created_at,
        where=TaskIntegration.project_id == project_id,
    ):
        title = (
            "Merged into main"
            if row.outcome == "merged"
            else "Merge skipped" if row.outcome == "skipped" else f"Merge {human(row.outcome)}"
        )
        leaf(
            f"integration:{row.id}",
            "merge",
            title,
            row.created_at,
            parent=task_parent(row.task_id),
            actors=[row.actor],
        )

    for row in await rows(
        Question.id,
        Question.from_agent,
        Question.question,
        Question.created_by_run_id,
        Question.blocked_task_id,
        Question.conversation_id,
        Question.created_at,
        Question.answered_at,
        Question.declined_at,
        where=Question.project_id == project_id,
    ):
        leaf(
            f"question:{row.id}",
            "question",
            plain(row.question) or "A question",
            row.created_at,
            row.answered_at or row.declined_at,
            parent=first(
                run_parent(row.created_by_run_id),
                task_parent(row.blocked_task_id),
                conversation_parent(row.conversation_id),
            ),
            actors=[row.from_agent] + (["operator"] if row.answered_at or row.declined_at else []),
        )

    for row in await rows(
        PermissionRequest.id,
        PermissionRequest.agent,
        PermissionRequest.run_id,
        PermissionRequest.conversation_id,
        PermissionRequest.tool_name,
        PermissionRequest.status,
        PermissionRequest.decided_by,
        PermissionRequest.created_at,
        PermissionRequest.decided_at,
        where=PermissionRequest.project_id == project_id,
    ):
        tool = human((row.tool_name or "a tool").split("__")[-1]) or "a tool"
        leaf(
            f"permission:{row.id}",
            "permission",
            f"Asked to use {tool} ({human(row.status)})",
            row.created_at,
            row.decided_at,
            parent=first(run_parent(row.run_id), conversation_parent(row.conversation_id)),
            actors=[row.agent, row.decided_by],
        )

    for row in await rows(
        Message.id,
        Message.sender,
        Message.recipient,
        Message.subject,
        Message.task_id,
        Message.conversation_id,
        Message.created_by_run_id,
        Message.timestamp,
        where=Message.project_id == project_id,
    ):
        leaf(
            f"message:{row.id}",
            "message",
            plain(row.subject) or f"{_actor(row.sender)} to {_actor(row.recipient)}",
            row.timestamp,
            parent=first(
                run_parent(row.created_by_run_id),
                task_parent(row.task_id),
                conversation_parent(row.conversation_id),
            ),
            actors=[row.sender, row.recipient],
        )

    for row in await rows(
        JobRun.id,
        JobRun.job_id,
        JobRun.status,
        JobRun.trigger,
        JobRun.conversation_id,
        JobRun.fired_at,
        where=JobRun.project_id == project_id,
    ):
        name = plain(job_names.get(row.job_id)) or "A scheduled job"
        leaf(
            f"firing:{row.id}",
            "firing",
            f"{name} fired ({human(row.status)})",
            row.fired_at,
            parent=doc_parent(loop_docs.get(row.job_id)),
            link={"object": "job-firing", "id": row.id, "job_id": row.job_id},
        )

    for entry in vault_entries:
        at = _parse(entry.get("created_at"))
        if at is None:
            continue
        leaf(
            f"vault:{entry['id']}",
            "vault-entry",
            plain(entry.get("name")) or "Vault entry",
            at,
            actors=[entry.get("added_by") or "operator"],
            link={"object": "vault-entry", "id": entry["id"]},
        )

    thread.settle()
    return thread


# -- reading --------------------------------------------------------------------------------


def cursor_of(knot: Knot) -> str:
    return f"{knot.start.isoformat()}|{knot.key}"


def _cursor_tuple(cursor: str) -> Optional[Tuple[datetime, str]]:
    stamp, _, key = cursor.partition("|")
    moment = _parse(stamp)
    return None if moment is None else (moment, key)


def page(
    knots: Sequence[Knot],
    *,
    limit: int,
    before: Optional[str] = None,
    after: Optional[str] = None,
    first: bool = False,
) -> Optional[Dict[str, Any]]:
    """One page of a level, oldest first. No cursor: the newest page; `first`: the oldest page;
    `before`/`after`: the page just beyond that cursor in that direction. None for a bad cursor."""
    ordered = list(knots)
    sort_keys = [k.sort_key for k in ordered]
    total = len(ordered)
    if first:
        lo, hi = 0, min(limit, total)
    elif before is not None or after is not None:
        point = _cursor_tuple(before or after or "")
        if point is None:
            return None
        if before is not None:
            hi = bisect.bisect_left(sort_keys, point)
            lo = max(0, hi - limit)
        else:
            lo = bisect.bisect_right(sort_keys, point)
            hi = min(total, lo + limit)
    else:
        lo, hi = max(0, total - limit), total
    shown = ordered[lo:hi]
    return {
        "knots": shown,
        "total": total,
        "has_before": lo > 0,
        "has_after": hi < total,
        "before_cursor": cursor_of(shown[0]) if shown else None,
        "after_cursor": cursor_of(shown[-1]) if shown else None,
    }


def face(knot: Knot, thread: Thread) -> Dict[str, Any]:
    """A knot as the route returns it, ready to draw: plain words, no way to read an event type."""
    return {
        "key": knot.key,
        "address": knot.key,
        "kind": knot.kind,
        "fold_of": knot.fold_of,
        "word": (
            PLURAL.get(knot.fold_of or "", "items").capitalize()
            if knot.kind == "fold"
            else WORDS[knot.kind]
        ),
        "title": knot.title,
        "start": knot.start.isoformat(),
        "end": knot.end.isoformat(),
        "actors": knot.actors,
        "child_count": len(thread.level(knot.key) or []),
        "descendant_count": knot.descendants,
        "link": knot.link,
        "records": knot.records[:RECORDS_SHOWN],
        "record_count": knot.record_count,
    }
