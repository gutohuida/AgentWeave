"""Which agent run a job or loop firing started.

`JobRun` and `Run` share no foreign key: the firing records the conversation it used
(`JobRun.conversation_id`) and the run lives in that conversation, which is also how
`scheduler.finalize_job_run_for_conversation` pairs them when the run ends. The run a firing started
is the first one in its conversation that began at or after the firing, and before the same
conversation's next firing (a session-resuming job reuses one conversation for every firing).

A firing with no conversation (refused before one existed), a skipped one, or one whose run has not
started yet has no run, and says so with `None` rather than guessing.
"""

from typing import Dict, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import JobRun, Run


async def run_ids_for_firings(
    session: AsyncSession, firings: Iterable[JobRun]
) -> Dict[str, Optional[str]]:
    """Firing id -> the id of the run it started, or None."""
    by_conversation: Dict[str, list] = {}
    for firing in firings:
        if firing.conversation_id is not None and firing.status != "skipped":
            by_conversation.setdefault(firing.conversation_id, []).append(firing)
    answer: Dict[str, Optional[str]] = {f.id: None for fs in by_conversation.values() for f in fs}
    if not by_conversation:
        return answer

    rows = await session.execute(
        select(Run.id, Run.conversation_id, Run.started_at)
        .where(Run.conversation_id.in_(list(by_conversation)))
        .order_by(Run.started_at.asc())
    )
    runs: Dict[str, list] = {}
    for run_id, conversation_id, started_at in rows.all():
        runs.setdefault(conversation_id, []).append((run_id, started_at))

    for conversation_id, group in by_conversation.items():
        group.sort(key=lambda f: f.fired_at)
        for index, firing in enumerate(group):
            until = group[index + 1].fired_at if index + 1 < len(group) else None
            for run_id, started_at in runs.get(conversation_id, []):
                if started_at < firing.fired_at:
                    continue
                if until is not None and started_at >= until:
                    break
                answer[firing.id] = run_id
                break
    return answer
