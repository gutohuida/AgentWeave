"""Generating the author's checkpoint when a flow agent hands its task over.

Finding F43. `_compose_loop_briefing` tells every agent in a flow to "record what a reviewer will
need (see `submit_checkpoint_notes`); somebody else reads it." Nobody read it, and nobody could:
every link in the chain worked, and there was no trigger.

`generate_checkpoint` had exactly two callers -- a context-usage threshold
(`checkpoint_trigger.consider_from_reading`) and an operator button (`api/v1/checkpoints.py`).
A flow firing is `session_mode: new`, one small task, and then that conversation never runs again.
Its context never approaches a threshold and no operator presses a button per handover, so the
notes were never consumed and `latest_checkpoint_for_loop` returned None on every firing the flow
would ever have. Measured on the live database when this was recorded: 3 of 3 notes unconsumed,
0 of 6 checkpoints carrying a `loop_id`.

**The hook is the run boundary, not the review dispatch.** A flow agent's conversation ends for
good when its run ends, so that run ending *is* the author's handover, and it is the moment their
notes are complete. Generating at review-dispatch time instead would have to happen inside the
firing, ~20 lines before `_compose_loop_briefing` reads the result (`scheduler.py`), so it would
either block the scheduler on a ~19s CLI spawn or race it and lose.

**Dispatched off that path, never awaited on it**, exactly as `checkpoint_trigger` is and for the
same measured reason: generation is a blocking CLI spawn at ~19s, and awaiting it at the run
boundary would hold every flow turn open behind a checkpoint.

**Gated on notes actually existing** (the operator's decision, 2026-08-25). A handover where the
agent recorded nothing has nothing to deliver, so it generates nothing and costs nothing; spend is
proportional to agents doing the thing the product asked them to do. The consequence is stated
rather than discovered later: an agent that ignores the instruction produces no briefing, and its
reviewer is no worse off than before this module existed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from sqlalchemy import select

from .checkpoint_generation import format_notes, generate_checkpoint
from .checkpoint_policy import resolve_policy
from .checkpoints import loop_for_conversation
from .conversations import get_conversation_by_id
from .db.engine import async_session_factory
from .db.models import (
    Agent,
    Checkpoint,
    CheckpointNote,
    JobRun,
    Project,
    Run,
    Runner,
    TaskTransition,
)
from .sse import sse_manager

logger = logging.getLogger(__name__)

#: One handover checkpoint per run at a time. The run boundary is reached once per run, so this is
#: a guard against a retry or a reconciliation pass arriving at the same run twice rather than
#: against ordinary repetition.
_in_flight: set = set()

#: Strong references to dispatched tasks. `asyncio` holds only a weak reference to a running task,
#: and `checkpoint_trigger` observed exactly this collected mid-flight: nothing spawned, and the
#: `finally` that clears `_in_flight` never ran, so the key was never released.
_dispatched: set = set()


def _declined(run_id: str, reason: str) -> None:
    """Say why a run boundary did not produce a handover checkpoint.

    Every exit below is a decision not to act, and an unexplained one is indistinguishable from a
    broken trigger -- which is precisely what F43 was, for as long as it went unnoticed.
    """
    logger.debug("no handover checkpoint for %s: %s", run_id, reason)


async def _task_this_run_completed(db, run: Run) -> Optional[str]:
    """The id of the task *run* moved into `completed`, or None.

    Read from the transition history rather than from the task's current status: by the time a
    later firing looks, the task may already be `under_review` (which is what F45's fix does to it
    at dispatch), and a status check would answer no for every task that was handed over
    successfully -- the exact population this exists to serve.

    **And never from `run.task_id`.** An earlier draft of this gated on that column being set, and
    measurement on the live database killed it before it shipped: of the ten runs that had recorded
    a `completed` transition, **six carried `run.task_id = NULL`**. The binding column is not a
    reliable record of what a run finished; the append-only table is, which is the same reason
    `agent_that_completed` gives for not reading `Task.updated_by_run_id`.
    """
    return (
        await db.execute(
            select(TaskTransition.task_id)
            .where(TaskTransition.to_status == "completed")
            .where(TaskTransition.run_id == run.id)
            .order_by(TaskTransition.sequence.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _conversation_ids_for_loop(db, loop) -> list:
    """Every conversation this loop has ever fired into.

    The inverse of `loop_for_conversation`'s join, and needed for the same reason that one exists:
    a loop's firings do not share a conversation.
    """
    return list(
        (
            await db.execute(
                select(JobRun.conversation_id)
                .where(JobRun.job_id == loop.job_id)
                .where(JobRun.conversation_id.is_not(None))
            )
        )
        .scalars()
        .all()
    )


async def _authors_pending_note(db, loop, *, agent: str) -> Optional[CheckpointNote]:
    """The newest unconsumed note *agent* has written anywhere in this loop.

    **Scoped to the loop, not to the completing conversation**, and that distinction is the whole
    difference between this firing and never firing at all. `submit_checkpoint_notes` scopes a note
    to the conversation that wrote it, and a flow job is `session_mode: new`, so **every firing gets
    a fresh conversation**. A task that takes more than one firing therefore records its notes in
    one conversation and its completion in another, as a matter of course rather than as an edge
    case.

    Measured on the live database before this was written: of four stranded notes, **none** shared a
    conversation with a run that had completed a task. `builder` wrote `note-e8cf4afcb4b1` at
    22:39:08 in `conv-ad35f0971ebc` and completed that same task at 22:40:00 in
    `conv-d047f286c1a3` -- two firings, three minutes apart. A conversation-scoped gate would have
    declined every one of them, which is F41's failure mode reproduced inside F41's own remedy.

    By agent, because a flow runs several concurrently and one agent's notes are not another's.
    """
    conversations = await _conversation_ids_for_loop(db, loop)
    if not conversations:
        return None
    return (
        (
            await db.execute(
                select(CheckpointNote)
                .where(CheckpointNote.conversation_id.in_(conversations))
                .where(CheckpointNote.agent == agent)
                .where(CheckpointNote.consumed_by_checkpoint_id.is_(None))
                .order_by(CheckpointNote.created_at.desc(), CheckpointNote.id.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def _already_checkpointed(db, conversation_id: str, run_id: str) -> bool:
    """Whether a checkpoint already covers this run.

    Cheap protection against the same boundary being evaluated twice -- a reconciliation pass over
    an interrupted run, or a retry -- spending a second model call to summarise the same turn.
    """
    return (
        await db.execute(
            select(Checkpoint.id)
            .where(Checkpoint.conversation_id == conversation_id)
            .where(Checkpoint.covers_through_run_id == run_id)
            .limit(1)
        )
    ).scalar_one_or_none() is not None


async def _resolve_runner(db, project: Project):
    """(cli, model, runner_id) for generation, or (None, None, None).

    Deliberately identical in shape and reasoning to `checkpoint_trigger._resolve_runner`: with no
    runner chosen, generation is skipped rather than guessed at, because spawning some other
    agent's expensive runner because none was configured is a bill the operator did not agree to.
    """
    if not project.checkpoint_runner_id:
        return None, None, None
    runner = await db.get(Runner, project.checkpoint_runner_id)
    if runner is None or runner.project_id != project.id:
        return None, None, None
    return runner.cli, project.checkpoint_model or runner.model, runner.id


async def consider_handover(run_id: str) -> Optional[str]:
    """Act on one run boundary. Returns the checkpoint id if one was generated.

    Runs in its own session and never raises into a caller: a checkpoint is never worth failing a
    finished turn over.
    """
    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        if run is None or not run.conversation_id:
            _declined(run_id, "no run, or no conversation")
            return None

        completed_task_id = await _task_this_run_completed(db, run)
        if completed_task_id is None:
            _declined(run_id, "this run completed no task")
            return None

        loop = await loop_for_conversation(db, run.conversation_id)
        if loop is None:
            # Not a loop firing at all. An ordinary conversation keeps running, so the
            # context-pressure trigger still owns it and this must not pre-empt that.
            _declined(run_id, "the conversation is not a loop firing")
            return None

        note = await _authors_pending_note(db, loop, agent=run.agent)
        if note is None:
            _declined(run_id, "the agent recorded no notes for its reviewer")
            return None

        if await _already_checkpointed(db, run.conversation_id, run_id):
            _declined(run_id, "a checkpoint already covers this run")
            return None

        conversation = await get_conversation_by_id(db, run.conversation_id)
        if conversation is None:
            _declined(run_id, "the conversation is missing")
            return None

        project = await db.get(Project, run.project_id)
        if project is None:
            return None

        agent = (
            (
                await db.execute(
                    select(Agent).where(Agent.project_id == run.project_id, Agent.name == run.agent)
                )
            )
            .scalars()
            .first()
        )
        # The same policy that governs the context-pressure path governs this one. An operator who
        # turned checkpointing off for an agent did not mean "except at handovers".
        if not resolve_policy(agent, project).enabled:
            _declined(run_id, "checkpointing is off for this agent and project")
            return None

        cli, model, runner_id = await _resolve_runner(db, project)
        if cli is None:
            logger.info(
                "run %s handed over with notes for its reviewer but the project has no "
                "checkpoint runner configured, so no briefing was generated",
                run_id,
            )
            return None

        # The note is passed explicitly rather than left to `generate_checkpoint`'s own
        # `pending_notes` lookup, because that lookup is conversation-scoped and this note may
        # belong to an earlier firing's conversation -- which, per `_authors_pending_note`, is the
        # ordinary case rather than the exception. An explicit `notes=` argument wins there by
        # design, "so a caller can generate without them deliberately"; this is the mirrored use.
        checkpoint = await generate_checkpoint(
            db,
            conversation,
            trigger="task_completion",
            cli=cli,
            model=model,
            runner_id=runner_id,
            notes=format_notes(note),
        )

        # And consumed here for the same reason: `generate_checkpoint` marks only the note its own
        # lookup found, so a note carried across from another conversation would otherwise be
        # delivered and then offered again to the next handover as though it were still pending.
        note.consumed_by_checkpoint_id = checkpoint.id
        await db.commit()

        await sse_manager.broadcast(
            run.project_id,
            "checkpoint_ready",
            {
                "checkpoint_id": checkpoint.id,
                "conversation_id": run.conversation_id,
                "agent": run.agent,
                "status": checkpoint.status,
                "probe_status": checkpoint.probe_status,
                "loop_id": loop.id,
                "task_id": completed_task_id,
            },
        )
        logger.info(
            "handover checkpoint %s generated for run %s on task %s, carrying note %s",
            checkpoint.id,
            run_id,
            completed_task_id,
            note.id,
        )
        return checkpoint.id


def consider_handover_from_run_end(run_id: str) -> None:
    """Fire-and-forget entry point for the run boundary.

    Returns immediately. Generation is a ~19s CLI spawn; awaiting it here would hold every flow
    turn's completion behind a checkpoint, which is the same reason `consider_from_reading` does
    not await either.
    """
    if not run_id or run_id in _in_flight:
        return

    _in_flight.add(run_id)

    async def _run() -> None:
        try:
            await consider_handover(run_id)
        except Exception:  # noqa: BLE001 -- never worth failing a finished turn over
            logger.warning("handover checkpoint failed for %s", run_id, exc_info=True)
        finally:
            _in_flight.discard(run_id)

    try:
        task = asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        # No running loop (a synchronous caller, or a test calling the sync entry point). Drop it
        # rather than block: the awaitable `consider_handover` is what a test should call.
        _in_flight.discard(run_id)
        return
    _dispatched.add(task)
    task.add_done_callback(_dispatched.discard)
