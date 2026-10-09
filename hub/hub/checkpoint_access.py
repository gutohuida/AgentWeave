"""Who may read a checkpoint, and who may recall the observations behind it.

Two independent grants on the agent, both closed by default. The read grant reaches every
checkpoint in the project, from every conversation: no checkpoint can restrict itself, and no
surface exists to set such a restriction, so the reader's grant is the whole answer.

The two grants are separate because **summary access is not transcript access**. A checkpoint is
a bounded, deliberate distillation. `recall` returns another agent's recorded output verbatim —
every path a tool printed, every fragment of a file it read. An agent that may see what a peer
concluded need not be able to see everything that peer's tools ever emitted, and a single flag
would make that narrower grant impossible to express.

Both grants live on the `Agent` row. **They are deliberately not readable from a charter**: a
charter is behaviour text a model reads, so if it could widen access then prose an agent could be
persuaded to write would be an authorisation mechanism.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from sqlalchemy import select

from .db.models import Agent, AgentOutput, Checkpoint

# How much of a cited observation the checkpoint itself shows. Enough to recognise, short enough
# that citing is not quietly a way to inline the whole transcript.
CITATION_PREVIEW_CHARS = 200


class AccessDeniedError(PermissionError):
    """The reader lacks the grant, or the record is not visible to it."""


def may_read_checkpoint(reader: Optional[Agent], checkpoint: Checkpoint) -> bool:
    """The reader's grant, plus an agent's standing access to its own checkpoints.

    An agent always reads its own checkpoints. Otherwise the grant is all-or-nothing across the
    project: `can_read_checkpoints` reaches every checkpoint, from every conversation.
    """
    if reader is None:
        return False
    if reader.name == checkpoint.agent:
        return True
    return reader.can_read_checkpoints


def may_recall(reader: Optional[Agent], checkpoint: Checkpoint) -> bool:
    """Recall additionally requires the reader to be able to read the checkpoint citing it.

    Recall is scoped to the conversation the checkpoint describes (v1). Without that scope the
    grant would be "read any recorded output in the project", which is a different and much
    larger permission than the one being asked for.
    """
    if reader is None:
        return False
    if reader.name == checkpoint.agent:
        return True
    return reader.can_recall and may_read_checkpoint(reader, checkpoint)


async def build_citations(db, conversation_id: str, run_ids: Sequence[str]) -> List[dict]:
    """Stable ids plus short previews for the observations a checkpoint summarises.

    Ids come straight from `agent_outputs`, which already retains recorded output verbatim under
    stable identifiers — this cites what exists rather than storing a second copy.
    """
    query = select(AgentOutput).where(
        AgentOutput.conversation_id == conversation_id,
        AgentOutput.kind == "text",
    )
    if run_ids:
        query = query.where(AgentOutput.run_id.in_(list(run_ids)))
    rows = list(
        (await db.execute(query.order_by(AgentOutput.timestamp, AgentOutput.id))).scalars().all()
    )
    return [
        {
            "id": row.id,
            "run_id": row.run_id,
            "preview": (row.content or "")[:CITATION_PREVIEW_CHARS],
        }
        for row in rows
    ]


async def _reader(db, project_id: str, reader_name: str) -> Optional[Agent]:
    return (
        (
            await db.execute(
                select(Agent).where(Agent.project_id == project_id, Agent.name == reader_name)
            )
        )
        .scalars()
        .first()
    )


async def readable_checkpoints(
    db, reader_name: str, project_id: str, *, agent: Optional[str] = None, limit: int = 20
) -> List[dict]:
    """The checkpoints this reader may open, newest first.

    Discovery exists because a grant nobody can spend is the same as no grant. `recall` scopes
    itself to observations a checkpoint cites, and `read_checkpoint` takes an id — and until this
    was here, the only checkpoint id an agent ever saw was the one its own cutover handed it. A
    reviewer told by `submit_checkpoint_notes`'s own docstring that it "reads it too" had no way
    to find the thing it was supposed to read.

    Filtered by `may_read_checkpoint` rather than by a query predicate, so the one definition of
    who may read what serves the list and the read alike. `unwritten` and `failed` checkpoints are
    excluded: neither has a body, and offering an id that opens to nothing is a worse answer than
    not listing it.
    """
    rows = list(
        (
            await db.execute(
                select(Checkpoint)
                .where(Checkpoint.project_id == project_id, Checkpoint.status == "ready")
                .order_by(Checkpoint.sequence.desc())
            )
        )
        .scalars()
        .all()
    )
    reader = await _reader(db, project_id, reader_name)
    out: List[dict] = []
    for row in rows:
        if agent is not None and row.agent != agent:
            continue
        if not may_read_checkpoint(reader, row):
            continue
        out.append(
            {
                "id": row.id,
                "agent": row.agent,
                "conversation_id": row.conversation_id,
                "trigger": row.trigger,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "yours": row.agent == reader_name,
            }
        )
        if len(out) >= limit:
            break
    return out


async def read_checkpoint(db, reader_name: str, project_id: str, checkpoint_id: str) -> dict:
    """One checkpoint, rendered exactly as a successor receives it, or refuse.

    Refused the same way `recall_observation` refuses, and for the same reason: an id that is out
    of reach must be indistinguishable from an id that does not exist, or the refusal itself
    confirms the record.
    """
    # Imported here, not at module scope: `checkpoint_generation` imports this module for
    # `build_citations`, so a top-level import would close the cycle.
    from .checkpoint_generation import render_checkpoint

    row = (
        (
            await db.execute(
                select(Checkpoint).where(
                    Checkpoint.id == checkpoint_id, Checkpoint.project_id == project_id
                )
            )
        )
        .scalars()
        .first()
    )
    reader = await _reader(db, project_id, reader_name)
    if row is None or not may_read_checkpoint(reader, row):
        raise AccessDeniedError("No checkpoint by that id is available to you.")
    return {
        "id": row.id,
        "agent": row.agent,
        "conversation_id": row.conversation_id,
        "trigger": row.trigger,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "rendered": render_checkpoint(row),
    }


async def recall_observation(db, reader_name: str, project_id: str, output_id: str) -> dict:
    """Materialise one cited observation exactly, or refuse.

    Refusals are deliberately indistinguishable between "no such observation" and "not cited by
    a checkpoint you may read": telling an ungranted caller that an id exists is itself a
    disclosure.
    """
    reader = (
        (
            await db.execute(
                select(Agent).where(Agent.project_id == project_id, Agent.name == reader_name)
            )
        )
        .scalars()
        .first()
    )

    output = (
        (
            await db.execute(
                select(AgentOutput).where(
                    AgentOutput.id == output_id, AgentOutput.project_id == project_id
                )
            )
        )
        .scalars()
        .first()
    )
    if output is None or not output.conversation_id:
        raise AccessDeniedError("No recorded observation by that id is available to you.")

    # The observation must be cited by a checkpoint the reader may read. Citation is what scopes
    # recall to a conversation rather than to the whole project.
    checkpoints = list(
        (
            await db.execute(
                select(Checkpoint).where(Checkpoint.conversation_id == output.conversation_id)
            )
        )
        .scalars()
        .all()
    )
    for checkpoint in checkpoints:
        cited = {entry.get("id") for entry in (checkpoint.citations or [])}
        if output_id in cited and may_recall(reader, checkpoint):
            return {
                "id": output.id,
                "conversation_id": output.conversation_id,
                "agent": output.agent,
                "run_id": output.run_id,
                "recorded_at": output.timestamp.isoformat() if output.timestamp else None,
                "content": output.content,
                "checkpoint_id": checkpoint.id,
            }

    raise AccessDeniedError("No recorded observation by that id is available to you.")
