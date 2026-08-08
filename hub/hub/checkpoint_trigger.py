"""Deciding, from a context reading, whether to ask for notes or take a checkpoint.

Hooked into `output_recording.record_context_usage` — the one funnel every context reading already
passes through, and the moment a percentage first becomes known (section 3 built it for exactly
this). Every other candidate hook is later or vaguer: run completion misses a single long turn
that blows past the threshold mid-run, and a periodic sweep adds a scheduler the Hub does not
otherwise need here.

**Dispatched off that path, never awaited on it.** Generation is a blocking CLI spawn measured at
~19s live. Awaiting it inside output recording would stall every turn's output behind a
checkpoint, so `consider_from_reading` returns immediately and the work runs in its own task with
its own session.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from sqlalchemy import select

from .checkpoint_cutover import CutoverRefusedError, cut_over
from .checkpoint_generation import generate_checkpoint
from .checkpoint_policy import resolve_policy, should_checkpoint, should_request_notes
from .db.engine import async_session_factory
from .db.models import (
    Agent,
    Checkpoint,
    CheckpointNote,
    Conversation,
    InboundQueueEntry,
    Project,
    Run,
    Runner,
)
from .inbound_queue import new_entry
from .sse import sse_manager

logger = logging.getLogger(__name__)

# One checkpoint attempt per conversation at a time. Context readings arrive several times a
# turn, and without this a conversation sitting above its threshold would spawn a generation on
# every one of them.
_in_flight: set = set()

# Strong references to the dispatched tasks.
#
# `asyncio` holds only a weak reference to a running task, so a task whose only reference was the
# local in the function that created it can be garbage-collected mid-flight. Observed exactly
# that: readings crossed the threshold, nothing spawned, and because the collected task never ran
# its `finally`, the conversation stayed in `_in_flight` forever and could never fire again.
_dispatched: set = set()

_NOTES_REQUEST = """\
This conversation is approaching the point where the Hub will checkpoint it and continue in a \
successor.

Before that happens, call `submit_checkpoint_notes` with what the record cannot show: what you \
are in the middle of doing, what you suspect but have not verified, and what a successor should \
not repeat. Do not list changed files, tasks, or open questions — the Hub already has those.

Then carry on with your work. This is not a request to stop."""


def _declined(conversation_id: str, reason: str) -> None:
    """Say why a reading did not produce a checkpoint.

    Every exit in `consider` is a decision not to act, and an unexplained one is indistinguishable
    from a broken trigger — which is what it was: a dropped task reference meant nothing ever
    fired and nothing ever said so. Debug level, because readings arrive several times a turn.
    """
    logger.debug("no checkpoint for %s: %s", conversation_id, reason)


async def _notes_already_in_hand(db, conversation_id: str) -> bool:
    """Whether notes were already given, or already asked for and not yet answered."""
    unconsumed = (
        await db.execute(
            select(CheckpointNote.id)
            .where(
                CheckpointNote.conversation_id == conversation_id,
                CheckpointNote.consumed_by_checkpoint_id.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if unconsumed is not None:
        return True

    pending_request = (
        await db.execute(
            select(InboundQueueEntry.id)
            .where(
                InboundQueueEntry.conversation_id == conversation_id,
                InboundQueueEntry.origin_type == "checkpoint",
                InboundQueueEntry.state == "queued",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return pending_request is not None


async def _nothing_new_since_last_checkpoint(db, conversation_id: str) -> bool:
    """Whether the newest checkpoint already covers the newest run.

    Without this a conversation that crosses its threshold and then goes quiet would be
    checkpointed again on every subsequent reading, each one summarising nothing.
    """
    latest = (
        await db.execute(
            select(Checkpoint.covers_through_run_id)
            .where(Checkpoint.conversation_id == conversation_id)
            .order_by(Checkpoint.created_at.desc(), Checkpoint.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is None:
        return False

    newest_run = (
        await db.execute(
            select(Run.id)
            .where(Run.conversation_id == conversation_id)
            .order_by(Run.started_at.desc(), Run.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return newest_run is not None and newest_run == latest


async def _resolve_runner(db, project: Project) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """(cli, model, runner_id) for generation — the project's chosen runner.

    Returns (None, None, None) when nothing is chosen. Generation is then skipped rather than
    guessed at: spawning some other agent's expensive runner because none was configured is a
    bill the operator did not agree to.
    """
    if not project.checkpoint_runner_id:
        return None, None, None
    runner = await db.get(Runner, project.checkpoint_runner_id)
    if runner is None or runner.project_id != project.id:
        return None, None, None
    return runner.cli, project.checkpoint_model or runner.model, runner.id


async def consider(
    project_id: str,
    agent_name: str,
    conversation_id: str,
    *,
    context_tokens: Optional[int],
    percent: Optional[float],
) -> Optional[str]:
    """Act on one context reading. Returns the checkpoint id if one was taken.

    Runs in its own session; never raises into a caller.
    """
    async with async_session_factory() as db:
        project = await db.get(Project, project_id)
        agent = (
            await db.execute(
                select(Agent).where(Agent.project_id == project_id, Agent.name == agent_name)
            )
        ).scalars().first()
        if project is None:
            return None

        policy = resolve_policy(agent, project)
        if not policy.enabled:
            _declined(conversation_id, "checkpointing is off for this agent and project")
            return None

        conversation = await db.get(Conversation, conversation_id)
        if conversation is None or conversation.lifecycle != "open":
            _declined(conversation_id, "the conversation is missing or not open")
            return None

        if should_request_notes(policy, context_tokens=context_tokens, percent=percent):
            if not await _notes_already_in_hand(db, conversation_id):
                db.add(
                    new_entry(
                        project_id=project_id,
                        agent=agent_name,
                        origin_type="checkpoint",
                        content=_NOTES_REQUEST,
                        hop_depth=0,
                        conversation_id=conversation_id,
                    )
                )
                await db.commit()
                logger.info("requested checkpoint notes for %s", conversation_id)
            return None

        if not should_checkpoint(policy, context_tokens=context_tokens, percent=percent):
            _declined(
                conversation_id,
                f"below the {policy.threshold_mode} threshold of {policy.threshold_value} "
                f"(tokens={context_tokens}, percent={percent})",
            )
            return None
        if await _nothing_new_since_last_checkpoint(db, conversation_id):
            _declined(conversation_id, "nothing has happened since the last checkpoint")
            return None

        cli, model, runner_id = await _resolve_runner(db, project)
        if cli is None:
            logger.info(
                "conversation %s crossed its checkpoint threshold but the project has no "
                "checkpoint runner configured",
                conversation_id,
            )
            return None

        checkpoint = await generate_checkpoint(
            db,
            conversation,
            trigger="context_pressure",
            cli=cli,
            model=model,
            runner_id=runner_id,
        )

        payload = {
            "checkpoint_id": checkpoint.id,
            "conversation_id": conversation_id,
            "agent": agent_name,
            "status": checkpoint.status,
            "probe_status": checkpoint.probe_status,
        }

        if policy.automatic and checkpoint.status == "ready":
            try:
                successor, entry_id = await cut_over(db, conversation, checkpoint)
            except CutoverRefusedError as exc:
                # The checkpoint stands; only the handover was refused. The operator is told why
                # rather than being left with a conversation that quietly kept going.
                payload["cutover_refused"] = str(exc)
                await sse_manager.broadcast(project_id, "checkpoint_ready", payload)
                return checkpoint.id
            payload["successor_conversation_id"] = successor.id
            payload["queue_entry_id"] = entry_id
            await sse_manager.broadcast(project_id, "conversation_cut_over", payload)
            return checkpoint.id

        # "Offered" is not "shall I ask the agent to write one?" — it is "I made one, here it
        # is, cut over?". Generation no longer depends on the agent, so there is nothing to ask
        # permission for before doing it.
        await sse_manager.broadcast(project_id, "checkpoint_ready", payload)
        return checkpoint.id


def consider_from_reading(
    project_id: str,
    agent_name: str,
    conversation_id: Optional[str],
    payload: dict,
) -> None:
    """Fire-and-forget entry point for the context-recording path.

    Returns immediately. A checkpoint is a ~19s CLI spawn; awaiting it here would put every
    turn's output recording behind it.
    """
    if not conversation_id:
        return
    percent = payload.get("percent")
    context_tokens = payload.get("context_tokens")
    if percent is None and context_tokens is None:
        return
    if conversation_id in _in_flight:
        return

    _in_flight.add(conversation_id)

    async def _run() -> None:
        try:
            await consider(
                project_id,
                agent_name,
                conversation_id,
                context_tokens=context_tokens if isinstance(context_tokens, int) else None,
                percent=percent if isinstance(percent, (int, float)) else None,
            )
        except Exception:  # noqa: BLE001 — a checkpoint is never worth failing a live turn over
            logger.warning("checkpoint consideration failed", exc_info=True)
        finally:
            _in_flight.discard(conversation_id)

    try:
        task = asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        # No loop (a synchronous caller, or a test). Nothing to dispatch onto; drop the reading
        # rather than block, since another will arrive within the turn.
        _in_flight.discard(conversation_id)
        return
    # Held until it finishes, or asyncio's weak reference lets it be collected mid-flight.
    _dispatched.add(task)
    task.add_done_callback(_dispatched.discard)
