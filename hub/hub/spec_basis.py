"""Which version of a specification document an agent's save is based on (FR-16).

`one-profile-runs-many-turns-at-once-on-different-tasks` FR-16, D7: two threads working one draft
is routine once a profile runs many turns at once, and the last save used to win silently. An
agent's save is refused when the document was saved by anybody else after the copy the save was
based on. The agent tool takes no version argument, so a document read back as-is stays
submittable: the Hub remembers, per conversation, the version that conversation last read or
saved, and that is the copy its next save is based on. A run with no conversation is its own
holder.

Held in memory. A holder with nothing remembered (a conversation that never read or saved the
document through the Hub, or one whose memory a Hub restart cleared) is not refused: there is no
copy it can be shown to be based on. The write itself still never lands over content stored after
the save read the file (`spec_documents.write_document`'s `expected_version`).
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Run

#: Bounded, oldest forgotten first: one entry per (document, conversation) pair still in use.
MAX_ENTRIES = 4096

_Key = Tuple[str, str]
_seen: "OrderedDict[_Key, str]" = OrderedDict()
_lock = threading.Lock()


async def holder(session: AsyncSession, run_id: Optional[str]) -> Optional[str]:
    """Who a run's reads and saves are remembered for: its conversation, or else the run."""
    if not run_id:
        return None
    conversation = (
        await session.execute(select(Run.conversation_id).where(Run.id == run_id))
    ).scalar_one_or_none()
    return f"conversation:{conversation}" if conversation else f"run:{run_id}"


def note(document_id: str, who: Optional[str], version: str) -> None:
    """Remember that `who` now holds `version` of the document (it read or saved it)."""
    if not who:
        return
    key = (document_id, who)
    with _lock:
        _seen[key] = version
        _seen.move_to_end(key)
        while len(_seen) > MAX_ENTRIES:
            _seen.popitem(last=False)


def based_on(document_id: str, who: Optional[str]) -> Optional[str]:
    """The version `who` last read or saved, or ``None`` when nothing is remembered."""
    if not who:
        return None
    with _lock:
        return _seen.get((document_id, who))
