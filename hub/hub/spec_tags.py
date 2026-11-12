"""A spec's short tag: what a task card calls the spec it belongs to.

At most `MAX_LENGTH` characters and unique within the project (compared without regard to case).
The author may write one in a submission; a spec without one gets one derived from its title the
first time a board asks for it, and keeps it from then on, so a card does not rename itself when
another spec arrives. A derived tag yields to any other spec's; a written tag that another spec
already holds is refused, naming that spec, and leaves the holder untouched.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import SpecDocument

MAX_LENGTH = 24

# Words that name nothing: dropped from a title before it is shortened to a tag.
_FILLER = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "to",
        "for",
        "and",
        "or",
        "in",
        "on",
        "its",
        "it",
        "is",
        "with",
        "without",
        "by",
        "as",
        "at",
    }
)


def normalize(tag: str) -> str:
    """The tag as stored: surrounding space gone, inner runs of space collapsed to one."""
    return " ".join(tag.split())


def derive(title: str, taken: Iterable[str] = ()) -> str:
    """A tag for *title* that is not in *taken* (compared without regard to case).

    The title's meaningful words joined by spaces, cut at a word boundary to fit. When that is held,
    a number is appended (`tasks board 2`), the base cut shorter to make room for it.
    """
    held = {tag.lower() for tag in taken}
    words = re.findall(r"[A-Za-z0-9]+", title.replace("'", ""))
    kept = [word.lower() for word in words if word.lower() not in _FILLER] or [
        word.lower() for word in words
    ]
    base = ""
    for word in kept:
        proposal = f"{base} {word}".strip()
        if len(proposal) > MAX_LENGTH:
            break
        base = proposal
    base = base or (kept[0][:MAX_LENGTH] if kept else "spec")
    if base.lower() not in held:
        return base
    number = 2
    while True:
        suffix = f" {number}"
        candidate = f"{base[: MAX_LENGTH - len(suffix)].rstrip()}{suffix}"
        if candidate.lower() not in held:
            return candidate
        number += 1


class TagTakenError(ValueError):
    """The tag a submission wrote is another spec's."""

    def __init__(self, tag: str, holder: SpecDocument) -> None:
        self.tag = tag
        self.holder = holder
        super().__init__(
            f"the tag {tag!r} already belongs to the spec {holder.title!r} ({holder.path}); "
            "choose another, or leave it out and the Hub derives one"
        )


async def claim(session: AsyncSession, document: SpecDocument, written: str) -> None:
    """Give *document* the tag its author wrote, or raise `TagTakenError` naming the holder.

    Nothing is changed on a refusal.
    """
    tag = normalize(written)
    if not tag:
        return
    found = await session.execute(
        select(SpecDocument).where(
            SpecDocument.project_id == document.project_id,
            SpecDocument.id != document.id,
            func.lower(SpecDocument.tag) == tag.lower(),
        )
    )
    holder = found.scalars().first()
    if holder is not None:
        raise TagTakenError(tag, holder)
    document.tag = tag


async def ensure_tags(session: AsyncSession, project_id: str) -> Dict[str, str]:
    """Every tag in the project by document id, deriving and storing the ones still missing.

    Documents are visited oldest first, so the same project always derives the same tags.
    """
    found = await session.execute(
        select(SpecDocument)
        .where(SpecDocument.project_id == project_id)
        .order_by(SpecDocument.created_at, SpecDocument.id)
    )
    documents: List[SpecDocument] = list(found.scalars())
    taken = [document.tag for document in documents if document.tag]
    changed = False
    for document in documents:
        if document.tag:
            continue
        document.tag = derive(document.title or document.path, taken)
        taken.append(document.tag)
        changed = True
    if changed:
        await session.flush()
    return {document.id: document.tag for document in documents if document.tag}
