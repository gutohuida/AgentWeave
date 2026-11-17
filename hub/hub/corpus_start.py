"""A project with no specs is offered a start (`a-project-with-no-specs-is-offered-a-start`).

**The corpus is empty** when the project holds no specification document in any phase, archived
included, and no spec file on disk waiting to be adopted (FR-1): a folder whose `spec/` files are
not adopted is the adoption flow's case, so it is offered nothing here. Whether the folder holds
code (any file outside `.git/`, `.agentweave/` and `spec/`) only decides which start is recommended;
both are always offered.

**Taking a start** (`start`, FR-5) creates its document at once, as the operator: a `system-map` for
existing code, a `roadmap` for greenfield, in exploring. Creating it first is what ends the offer and
refuses a second start (409), with no lock. Then one operator-origin entry carrying the document is
queued to the chosen agent in a new conversation, as `slice_drafting.take_offer` queues a drafting
turn. The caller commits and schedules the agent.

The preselected agent (FR-4) is the open agent whose charter is Spec Author when exactly one has it,
otherwise the first open agent (by creation).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import blocking, spec_documents, spec_lifecycle, spec_service
from .conversations import name_conversation, new_conversation
from .db.models import Agent, Charter, SpecDocument
from .inbound_queue import new_entry
from .spec_payload import SCHEMA_VERSION

Start = Literal["existing-code", "greenfield"]
EXISTING_CODE: Start = "existing-code"
GREENFIELD: Start = "greenfield"

#: The kind of document each start creates.
START_KINDS: Dict[str, str] = {EXISTING_CODE: "system-map", GREENFIELD: "roadmap"}
_TITLES: Dict[str, str] = {EXISTING_CODE: "System map", GREENFIELD: "Roadmap"}
_CONVERSATION_NAMES: Dict[str, str] = {
    EXISTING_CODE: "Map the existing code",
    GREENFIELD: "Plan the project",
}

#: The charter whose holder is preselected, when exactly one open agent holds it.
SPEC_AUTHOR_CHARTER = "Spec Author"

#: Top-level directories that are not the project's code.
_NOT_CODE = frozenset({".git", ".agentweave", "spec"})


class StartRefused(Exception):  # noqa: N818 -- "refused" is the outcome, not a fault
    def __init__(self, message: str, *, code: str, status_code: int = 409, **detail: Any) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.detail = detail


@dataclass
class CorpusState:
    empty: bool
    has_code: bool
    #: The start recommended while the corpus is empty; None once it is not.
    recommended: Optional[str]
    #: Open agents, in creation order, each `{name, charter}`.
    agents: List[Dict[str, Optional[str]]] = field(default_factory=list)
    preselected_agent: Optional[str] = None
    #: What makes the corpus not empty: a tracked document's path, else an unadopted file's.
    document: Optional[str] = None
    unadopted: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "empty": self.empty,
            "has_code": self.has_code,
            "recommended": self.recommended,
            "starts": [EXISTING_CODE, GREENFIELD] if self.empty else [],
            "agents": self.agents,
            "preselected_agent": self.preselected_agent,
            "document": self.document,
            "unadopted": self.unadopted,
        }


def has_code(root: Path) -> bool:
    """Whether *root* holds at least one file outside `.git/`, `.agentweave/` and `spec/`. Stops at
    the first file found, so a large repository costs one directory read or so."""
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if directory == root and entry.name in _NOT_CODE:
                        continue
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    return True
            except OSError:
                continue
    return False


def preselect(agents: Sequence[Tuple[str, Optional[str]]]) -> Optional[str]:
    """The agent a start preselects from *agents* (`(name, charter name)`, in order): the one whose
    charter is Spec Author when exactly one has it, otherwise the first (FR-4)."""
    authors = [name for name, charter in agents if charter == SPEC_AUTHOR_CHARTER]
    if len(authors) == 1:
        return authors[0]
    return agents[0][0] if agents else None


async def open_agents(session: AsyncSession, project_id: str) -> List[Tuple[str, Optional[str]]]:
    """The project's open agents, in creation order, each with its charter's name."""
    rows = await session.execute(
        select(Agent.name, Charter.name)
        .outerjoin(Charter, Charter.id == Agent.charter_id)
        .where(Agent.project_id == project_id, Agent.lifecycle == "open")
        .order_by(Agent.created_at, Agent.name)
    )
    return [(name, charter) for name, charter in rows.all()]


def _disk_state(workspace) -> Tuple[List[str], bool]:  # noqa: ANN001 -- a ProjectWorkspace
    paths, _ = spec_documents.discover(workspace)
    return paths, has_code(workspace.root)


async def corpus_state(session: AsyncSession, workspace, project_id: str) -> CorpusState:
    """Whether the project's corpus is empty, whether its folder holds code, and who would start
    it (FR-1, FR-4). Archived documents count: a project that ever had one is not offered a start.
    """
    first = await session.scalar(
        select(SpecDocument.path)
        .where(SpecDocument.project_id == project_id)
        .order_by(SpecDocument.created_at, SpecDocument.id)
        .limit(1)
    )
    tracked = set()
    if first is None:
        on_disk, code = await blocking.run(_disk_state, workspace)
    else:
        on_disk, code = [], await blocking.run(has_code, workspace.root)
        tracked = {first}
    if on_disk:
        tracked |= set(
            (
                await session.execute(
                    select(SpecDocument.path).where(
                        SpecDocument.project_id == project_id, SpecDocument.path.in_(on_disk)
                    )
                )
            )
            .scalars()
            .all()
        )
    unadopted = [path for path in on_disk if path not in tracked]
    empty = first is None and not unadopted
    agents = await open_agents(session, project_id)
    return CorpusState(
        empty=empty,
        has_code=code,
        recommended=(EXISTING_CODE if code else GREENFIELD) if empty else None,
        agents=[{"name": name, "charter": charter} for name, charter in agents],
        preselected_agent=preselect(agents),
        document=first or (unadopted[0] if unadopted else None),
        unadopted=unadopted,
    )


async def document_count(session: AsyncSession, project_id: str) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(SpecDocument)
            .where(SpecDocument.project_id == project_id)
        )
        or 0
    )


async def start(
    session: AsyncSession,
    workspace,  # noqa: ANN001 -- a ProjectWorkspace
    project_id: str,
    *,
    which: str,
    agent: Optional[str],
) -> Dict[str, Any]:
    """Take the start *which* with *agent* (the preselected one when not given): create its
    document as the operator and queue the agent's turn in a new conversation. The caller commits
    and schedules the agent. Raises `StartRefused`."""
    if which not in START_KINDS:
        raise StartRefused(
            f"unknown start {which!r}; a start is {EXISTING_CODE} or {GREENFIELD}",
            code="unknown_start",
            status_code=422,
        )
    state = await corpus_state(session, workspace, project_id)
    if not state.empty:
        raise StartRefused(
            f"this project's specifications are already started: {state.document} exists, so a "
            "start would create nothing new",
            code="corpus_not_empty",
            document=state.document,
        )
    names = [a["name"] for a in state.agents]
    chosen = (agent or "").strip() or state.preselected_agent
    if not chosen:
        raise StartRefused(
            "this project has no open agent to start its specifications; add one first",
            code="no_open_agent",
            status_code=422,
        )
    if chosen not in names:
        raise StartRefused(
            f"{chosen} is not an open agent of this project", code="agent_not_open", status_code=422
        )

    kind = START_KINDS[which]
    title = _TITLES[which]
    operator = spec_lifecycle.Actor(kind="operator", name="operator")
    path = await spec_service.mint_document_path(session, project_id, workspace, kind=kind)
    document = await spec_lifecycle.create_document(
        session, project_id, path, actor=operator, title=title, kind=kind
    )
    await spec_service.save_document(
        session,
        workspace,
        document,
        {"schema_version": SCHEMA_VERSION, "kind": kind, "title": title},
        actor=operator,
        via="create",
    )

    content = (existing_code_message if which == EXISTING_CODE else greenfield_message)(path)
    conversation = new_conversation(project_id=project_id, agent=chosen, origin="operator")
    name_conversation(conversation, _CONVERSATION_NAMES[which])
    session.add(conversation)
    entry = new_entry(
        project_id=project_id,
        agent=chosen,
        origin_type="operator",
        content=content,
        hop_depth=0,
        conversation_id=conversation.id,
        spec_document=path,
    )
    session.add(entry)
    return {
        "start": which,
        "agent": chosen,
        "document": {
            "id": document.id,
            "path": path,
            "kind": kind,
            "title": title,
            "phase": document.phase,
        },
        "conversation_id": conversation.id,
        "entry_id": entry.id,
    }


def existing_code_message(path: str) -> str:
    """The fixed Hub text of the existing-code turn (FR-6)."""
    return "\n".join(
        [
            "The operator has asked you to write down what this project's existing code does, "
            f"starting its specifications. The Hub has created a system map for you at `{path}` "
            "(kind `system-map`, exploring); write it and the capability drafts below. Do not "
            "change any code.",
            "1. Read the code. Read the parts that decide what the product does: its entry "
            "points, routes, commands, data model and tests.",
            f"2. Write the system map with `submit_spec_document` at `{path}`, kind `system-map`: "
            "the code's areas, the capabilities it provides and how they relate to one another. "
            "Name each capability you propose, by title, in the map's `capabilities.creates` "
            '(`{"creates": [{"title": ...}, ...]}`; never `capabilities.changes`).',
            "3. Create one capability draft per proposed capability: `create_spec_document` (a "
            "`change-spec`), `rename_spec_document`, then `submit_spec_document`. A draft is a "
            "change document with no tasks whose own `capabilities.creates` holds exactly that "
            "capability's title, as the map names it. It describes current behaviour, not a "
            "change: each requirement states what the code does now and cites the files it rests "
            "on (`path:line`).",
            "4. Code is evidence of what was done, not proof of what was meant. Behaviour you "
            "inferred from the code rather than found confirmed as intended (by a test, a comment "
            "or documentation) is recorded as an unresolved open question (`resolved: false`) "
            "on the draft it belongs to, not stated as a requirement's settled intent.",
            "5. Name in the map's evidence limits (`evidence.limits`) the code you did not read. "
            "A map read as complete when it is not makes people trust a wrong corpus.",
            "Do not approve, fold or create capabilities yourself: the operator reviews each draft, "
            "approves it and folds it into a capability. When you are done, say in your reply "
            "what the map covers, what it does not, and which drafts you wrote.",
        ]
    )


def greenfield_message(path: str) -> str:
    """The fixed Hub text of the greenfield turn (FR-9)."""
    return "\n".join(
        [
            "The operator has asked you to plan this new project, starting its specifications. "
            f"The Hub has created a roadmap for you at `{path}` (kind `roadmap`, exploring).",
            "Interview the operator before writing any slices: ask about the problem the project "
            "solves, who its users are, what is in scope and what its non-goals are. Ask your "
            "questions in your reply, a few at a time, while the roadmap is exploring; the "
            "operator answers in this conversation. Do not use `ask_user` for them.",
            "Start now: the operator has not written anything yet, so your first reply asks your "
            "first questions.",
            f"Once you understand the project, write the roadmap with `submit_spec_document` at "
            f"`{path}`, kind `roadmap`: its slices in build order, each a demonstrable outcome. "
            "Do not implement anything.",
        ]
    )
