"""A task's readable id: `BPS-3` beside the stored `task-<hex>` (`tickets-have-readable-ids`).

The stored id stays the primary key, the branch name and every internal reference. The readable one
is minted once, unique per project, and turned back into the stored id once, where a request enters
(`resolve`); nothing past that door sees it.

`acronym_counters` is both halves of the rule. A row claims its acronym for the project across specs
and the project itself, whichever takes it, so the primary key is what enforces uniqueness; and its
`high_water` is the last number minted, kept when the task or the spec goes, so a number is never
used again (the rule `FR-n` follows, `spec_identity.mint`). Unlike `FR-n`, parallel creation is
normal in a flow, so the number comes from one upsert rather than a read and a write.

Migration `0158` restates `candidates` to number the tasks that already exist; the test module pins
the two together.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Iterator, Optional
from uuid import uuid4

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import AcronymCounter, Project, SpecDocument, Task
from .readable_id_shape import RESERVED_ACRONYMS, is_readable_shaped

logger = logging.getLogger(__name__)

ACRONYM_RE = re.compile(r"^[A-Z][A-Z0-9]{1,4}$")
#: `FR-3` is how a requirement is named everywhere a task's work is discussed. Nothing stops the
#: operator choosing it; the Hub just does not hand it out.
_NOT_DERIVED = frozenset({"FR"})
_STOP_WORDS = frozenset(["a", "an", "and", "at", "by", "for", "from", "in", "into", "is", "it", "its", "of", "on", "or", "the", "to", "with"])
_WORD_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")
SPEC_FALLBACK = "SPEC"
PROJECT_FALLBACK = "PROJ"


class AcronymRefusedError(ValueError):
    """An edit to an acronym that cannot stand. `conflict` separates what the Hub holds (409) from
    what is wrong with the value itself (422)."""

    def __init__(self, message: str, *, conflict: bool = False) -> None:
        super().__init__(message)
        self.conflict = conflict


def acronym_refusal(acronym: str) -> Optional[str]:
    """Why *acronym* cannot be one, in the words the operator reads, or None. It is uppercased first,
    because `sk` is refused for what it is, not for its case."""
    upper = acronym.upper()
    if upper in RESERVED_ACRONYMS:
        return f"{upper} cannot be an acronym: {upper.lower()}-12 would be read as " + (
            "a stored task id." if upper == "TASK" else "a secret and redacted from the logs."
        )
    if not ACRONYM_RE.match(upper):
        return "An acronym is 2 to 5 letters and digits, starting with a letter."
    return None


def _words(title: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    words = _WORD_RE.findall(folded)
    significant = [word for word in words if word.lower() not in _STOP_WORDS]
    # A title of nothing but stop words still has a name.
    return [word.upper() for word in (significant if len(significant) >= 2 else words)]


def candidates(title: str, fallback: str) -> Iterator[str]:
    """What *title* could be called, best first. Every one meets the shape and the refusals; endless
    in practice, so a project holding them all still gets an answer."""

    def proposals() -> Iterator[str]:
        words = _words(title) or [fallback]
        # An acronym starts with a letter, so a leading number is not part of it.
        while words and not words[0][0].isalpha():
            words = words[1:]
        words = words or [fallback]
        initials = "".join(word[0] for word in words)[:5]
        yield initials
        others = initials[1:]
        for length in range(2 if others else 3, 6):
            yield (words[0][:length] + others)[:5]
        joined = "".join(words)
        for length in (3, 4, 5, 2):
            yield joined[:length]
        for digits, keep in ((1, 4), (2, 3), (3, 2)):
            for number in range(2, 10**digits):
                yield f"{joined[:keep]}{number}"

    seen = set()
    for proposal in proposals():
        if proposal in seen or proposal in _NOT_DERIVED or acronym_refusal(proposal) is not None:
            continue
        seen.add(proposal)
        yield proposal
    while True:
        yield "X" + uuid4().hex[:4].upper()


async def _claim(session: AsyncSession, project_id: str, acronym: str) -> bool:
    """Take *acronym* for the project, or say somebody holds it. Never raises on a loser, because a
    derivation just moves on to its next candidate."""
    claimed = await session.execute(
        text(
            "INSERT INTO acronym_counters (project_id, acronym, high_water) "
            "VALUES (:project_id, :acronym, 0) "
            "ON CONFLICT (project_id, acronym) DO NOTHING RETURNING acronym"
        ),
        {"project_id": project_id, "acronym": acronym},
    )
    return claimed.first() is not None


async def derive(session: AsyncSession, project_id: str, title: str, fallback: str) -> str:
    """The acronym *title* earns in this project, claimed."""
    for candidate in candidates(title, fallback):
        if await _claim(session, project_id, candidate):
            return candidate
    raise AssertionError("candidates() does not end")  # pragma: no cover


async def _spec_has_tasks(session: AsyncSession, document: SpecDocument) -> bool:
    """Whether the document's acronym is spent: a task of it exists, or one was minted from it and
    has since been deleted (its id is still in old messages, and it must stay what they say)."""
    linked = await session.scalar(
        select(func.count()).select_from(Task).where(Task.spec_document_id == document.id)
    )
    if linked:
        return True
    return bool(
        await session.scalar(
            select(AcronymCounter.high_water).where(
                AcronymCounter.project_id == document.project_id,
                AcronymCounter.acronym == document.acronym,
            )
        )
    )


async def _replace(session: AsyncSession, document: SpecDocument, new: str) -> None:
    """Hand back the acronym this document held. Only ever reached with nothing minted from it."""
    if document.acronym and document.acronym != new:
        await session.execute(
            delete(AcronymCounter).where(
                AcronymCounter.project_id == document.project_id,
                AcronymCounter.acronym == document.acronym,
            )
        )
    document.acronym = new


async def follow_title(session: AsyncSession, document: SpecDocument) -> None:
    """Re-derive from a title that changed, while nothing has been built on the acronym.

    A document is created before anyone knows what it is about, under a placeholder name, so what
    creation derived is often from the placeholder. An acronym the operator chose stays theirs.
    """
    if document.acronym_chosen or not document.acronym:
        return
    if await _spec_has_tasks(session, document):
        return
    first = next(candidates(document.title or "", SPEC_FALLBACK))
    if first == document.acronym:
        return
    # Claimed before the old one is released, so a title that keeps failing to win its first choice
    # does not walk through candidates by giving back what it holds.
    await _replace(
        session,
        document,
        await derive(session, document.project_id, document.title or "", SPEC_FALLBACK),
    )


async def edit_acronym(session: AsyncSession, document: SpecDocument, value: str) -> str:
    """The operator choosing a document's acronym (FR-11). Raises `AcronymRefusedError` naming why."""
    new = value.strip().upper()
    refusal = acronym_refusal(new)
    if refusal is not None:
        raise AcronymRefusedError(refusal)
    if new == document.acronym:
        return new
    if await _spec_has_tasks(session, document):
        raise AcronymRefusedError(
            f"{document.acronym} cannot change: this spec has tasks named by it, and a task's id "
            "never changes.",
            conflict=True,
        )
    if not await _claim(session, document.project_id, new):
        raise AcronymRefusedError(
            f"{new} is already held in this project, by a spec or by the project itself.",
            conflict=True,
        )
    await _replace(session, document, new)
    document.acronym_chosen = True
    return new


async def _acronym_for_project(session: AsyncSession, project_id: str) -> str:
    """The project's acronym. Normally set when the project is made or by the migration; a row that
    has neither gets it here, under the write lock so two first tasks agree on it."""
    held = await session.scalar(select(Project.acronym).where(Project.id == project_id))
    if held:
        return held
    await session.execute(
        update(Project)
        .where(Project.id == project_id)
        .values(acronym=Project.acronym)
        .execution_options(synchronize_session=False)
    )
    row = (
        await session.execute(select(Project.acronym, Project.name).where(Project.id == project_id))
    ).first()
    if row is not None and row.acronym:
        return row.acronym
    acronym = await derive(session, project_id, row.name if row else "", PROJECT_FALLBACK)
    await session.execute(
        update(Project)
        .where(Project.id == project_id)
        .values(acronym=acronym)
        .execution_options(synchronize_session="fetch")
    )
    return acronym


async def _acronym_for_document(session: AsyncSession, document_id: str) -> Optional[str]:
    """The acronym of the document, or None where it no longer exists."""
    row = (
        await session.execute(
            select(SpecDocument.acronym, SpecDocument.title, SpecDocument.project_id).where(
                SpecDocument.id == document_id
            )
        )
    ).first()
    if row is None:
        return None
    if row.acronym:
        return row.acronym
    await session.execute(
        update(SpecDocument)
        .where(SpecDocument.id == document_id)
        .values(acronym=SpecDocument.acronym)
        .execution_options(synchronize_session=False)
    )
    held = await session.scalar(select(SpecDocument.acronym).where(SpecDocument.id == document_id))
    if held:
        return held
    acronym = await derive(session, row.project_id, row.title or "", SPEC_FALLBACK)
    await session.execute(
        update(SpecDocument)
        .where(SpecDocument.id == document_id)
        .values(acronym=acronym)
        .execution_options(synchronize_session="fetch")
    )
    return acronym


async def mint(session: AsyncSession, project_id: str, spec_document_id: Optional[str]) -> str:
    """The next readable id for a task being created: its spec's acronym, else the project's.

    One atomic upsert, so simultaneous creates cannot read the same number. It rides the caller's
    transaction: a create that fails uses up nothing.
    """
    acronym = None
    if spec_document_id:
        acronym = await _acronym_for_document(session, spec_document_id)
    if acronym is None:
        acronym = await _acronym_for_project(session, project_id)
    number = await session.scalar(
        text(
            "INSERT INTO acronym_counters (project_id, acronym, high_water) "
            "VALUES (:project_id, :acronym, 1) "
            "ON CONFLICT (project_id, acronym) DO UPDATE "
            "SET high_water = acronym_counters.high_water + 1 RETURNING high_water"
        ),
        {"project_id": project_id, "acronym": acronym},
    )
    return f"{acronym}-{number}"


async def resolve(session: AsyncSession, project_id: str, reference: str) -> str:
    """The stored id *reference* names in this project, or *reference* unchanged.

    Unchanged is the answer for anything else too: the caller's own lookup then answers as it
    always has, so a stored id keeps resolving (FR-7) and an unknown one keeps its refusal. A stored
    id wins over a readable one, because a caller could once store `BPS-3` as an id and it must go on
    meaning what it meant; creation now refuses that shape (FR-8).
    """
    if not is_readable_shaped(reference):
        return reference
    stored = await session.scalar(
        select(Task.id).where(Task.project_id == project_id, Task.id == reference)
    )
    if stored is not None:
        return stored
    matched = await session.scalar(
        select(Task.id).where(Task.project_id == project_id, Task.readable_id == reference.upper())
    )
    return matched if matched is not None else reference


async def snapshot_message(worktree: Path, agent: str) -> Optional[str]:
    """The message for the snapshot of a turn's checkout, or None to leave it to `snapshot_worktree`
    (not a task's checkout, or the name cannot be read: the work still gets committed).

    In its own session, because the turn's end holds none, and worth one query: which task a checkout
    is comes from the directory, so the message cannot disagree with where the commit lands.
    """
    from .db.engine import async_session_factory
    from .worktrees import task_id_of

    task_id = task_id_of(worktree)
    if task_id is None:
        return None
    try:
        async with async_session_factory() as session:
            readable = await session.scalar(select(Task.readable_id).where(Task.id == task_id))
    except Exception:  # noqa: BLE001 -- a label is never worth losing a turn's snapshot
        logger.warning("could not read the readable id of %s", task_id, exc_info=True)
        return None
    if not readable:
        return None
    return f"Auto-snapshot: {agent}'s turn on {commit_name(task_id, readable)}"


def commit_name(task_id: str, readable_id: Optional[str]) -> str:
    """How a commit message names a task: both ids (FR-12), because the readable one means nothing
    outside its project and the stored one means nothing to a person."""
    return f"{readable_id} ({task_id})" if readable_id else task_id
