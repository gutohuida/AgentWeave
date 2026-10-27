"""Shared agent-output / context-usage recording, used by both compatibility self-report HTTP
endpoints (`POST /agents/{name}/output`, `.../context-usage`) and the
Hub's own direct-spawn output loop (`agent_trigger.py`). Factored out so a Hub-spawned run's
output is recorded through the exact same DB-write + SSE-broadcast shape a self-reporting
agent already produces — one path, not two that can drift.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import weakref
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from . import run_secrets, traces
from .context_readings import IS_CONTEXT_READING
from .conversations import latest_open_conversation, new_conversation, set_provider_session
from .db.engine import async_session_factory
from .db.models import AgentOutput, Conversation, EventLog, Run
from .model_catalog import context_window_for_model
from .runner_events import redact_text_secrets
from .sse import sse_manager
from .utils import persist_event, short_id

logger = logging.getLogger(__name__)


async def record_agent_output(
    db: AsyncSession,
    project_id: str,
    agent: str,
    *,
    content: str,
    session_id: Optional[str],
    conversation_id: Optional[str] = None,
    kind: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    sequence: Optional[int] = None,
    staged: Optional["StagedLine"] = None,
) -> AgentOutput:
    """Persist one AgentOutput row and broadcast it, mirroring `POST .../output`.

    *staged* is the streamed-line writer's call (`flush_streamed`): the line was broadcast when it
    arrived, so this adds its row and span to the batch's session under the id and instant it was
    broadcast with, and neither commits nor broadcasts.

    Every kind's `content` and every string in its `payload` are scrubbed of the run's registered
    secrets first (slice 5 D7), so neither the row nor the broadcast ever holds them.

    That scrub is per event, and it is the floor for every kind and every caller. A value split
    across two of a run's `text`/`thinking` events is joined at the executors instead
    (`run_secrets.scrub_stream`, F488), not here: `_record_observation` re-invokes this function
    on a locked database, and a stateful scrub here would take the same text in twice.
    """
    if staged is not None:
        # Scrubbed when it was streamed (`stream_agent_output`), by the same two passes.
        return await _stage_row(
            db,
            project_id,
            agent,
            content=content,
            session_id=session_id,
            conversation_id=conversation_id,
            kind=kind,
            payload=payload,
            run_id=run_id,
            sequence=sequence,
            row_id=staged.row_id,
            recorded_at=staged.recorded_at,
        )
    content = run_secrets.scrub(run_id, content)
    payload = run_secrets.scrub(run_id, payload)
    # And the named secret patterns, for every kind and caller (F602): a reply quoting a key, or the
    # operator's own `POST .../output`, used to store it verbatim while the tool rows said
    # <redacted>. Stateless, so the locked-database retry is safe; splits are `scrub_stream`'s.
    content = redact_text_secrets(content)
    payload = redact_text_secrets(payload)
    if conversation_id is None and run_id:
        run_result = await db.execute(
            select(Run.conversation_id).where(
                Run.id == run_id,
                Run.project_id == project_id,
                Run.agent == agent,
            )
        )
        conversation_id = run_result.scalar_one_or_none()
    if conversation_id is None and session_id:
        conversation_result = await db.execute(
            select(Conversation.id).where(
                Conversation.project_id == project_id,
                Conversation.agent == agent,
                Conversation.provider_session_id == session_id,
            )
        )
        conversation_id = conversation_result.scalar_one_or_none()
    if conversation_id is None:
        conversation = None
        if session_id is None:
            conversation = await latest_open_conversation(db, project_id=project_id, agent=agent)
        if conversation is None:
            # Reached only when output arrives that no conversation and no run accounts for —
            # a self-reporting agent's session the Hub did not open. `operator` is the floor:
            # the thread it reconstructs is the one the operator sees the agent working in.
            conversation = new_conversation(project_id=project_id, agent=agent, origin="operator")
            # Self-reported: the Hub did not open it, so which CLI made it is not known.
            set_provider_session(conversation, session_id, None)
            db.add(conversation)
            await db.flush()
        conversation_id = conversation.id
    is_new_session = False
    if session_id:
        count_result = await db.execute(
            select(AgentOutput.id)
            .where(
                AgentOutput.project_id == project_id,
                AgentOutput.agent == agent,
                AgentOutput.session_id == session_id,
            )
            .limit(1)
        )
        is_new_session = count_result.scalar() is None

    # One instant for the row and its span (`traces.observe_output`), set here rather than left
    # to the column default, which is applied only at the flush the span is written before.
    recorded_at = datetime.now(timezone.utc)
    row = await _stage_row(
        db,
        project_id,
        agent,
        content=content,
        session_id=session_id,
        conversation_id=conversation_id,
        kind=kind,
        payload=payload,
        run_id=run_id,
        sequence=sequence,
        row_id=f"out-{short_id()}",
        recorded_at=recorded_at,
    )
    await db.commit()

    # No `db.refresh(row)` here, deliberately (F287). It was one extra SELECT by primary key on
    # the Hub's hottest write path -- every streamed line of every turn, on both runners -- and
    # nothing read anything it could have loaded. `async_session_factory` sets
    # `expire_on_commit=False` (`db/engine.py:39`), so the commit does not expire the instance;
    # `AgentOutput` has no server-side defaults, and the one column the caller does not set,
    # `timestamp`, is a Python-side `default=_now` (`db/models.py:1247`) already applied at flush.
    # The broadcast below reads `row.timestamp`; that it is populated without a refresh is pinned
    # by a test in `hub/tests/test_agent_output_stream.py`, which fails if the refresh is the only
    # reason it is set.
    await sse_manager.broadcast(
        project_id,
        "agent_output",
        {
            "id": row.id,
            "agent": agent,
            "session_id": session_id,
            "conversation_id": conversation_id,
            "content": content,
            "kind": kind,
            "payload": payload,
            "run_id": run_id,
            "sequence": sequence,
            "timestamp": row.timestamp.isoformat(),
        },
    )
    if is_new_session:
        await sse_manager.broadcast(
            project_id, "agent_session_changed", {"agent": agent, "session_id": session_id}
        )
    _consider_compaction(project_id, agent, conversation_id, kind, payload)
    return row


async def _stage_row(
    db: AsyncSession,
    project_id: str,
    agent: str,
    *,
    content: str,
    session_id: Optional[str],
    conversation_id: Optional[str],
    kind: Optional[str],
    payload: Optional[Dict[str, Any]],
    run_id: Optional[str],
    sequence: Optional[int],
    row_id: str,
    recorded_at: datetime,
) -> AgentOutput:
    row = AgentOutput(
        id=row_id,
        project_id=project_id,
        agent=agent,
        session_id=session_id,
        conversation_id=conversation_id,
        content=content,
        kind=kind,
        payload=payload,
        run_id=run_id,
        sequence=sequence,
        timestamp=recorded_at,
    )
    db.add(row)
    # The run's trace, from the same scrubbed values and in the same transaction, so the span and
    # the row commit together and the locked-database retry rewrites both (trace-1019, D1).
    # A trace is the Hub's bookkeeping about the run: a defect in it is logged, never allowed to
    # lose the row it describes.
    try:
        await traces.observe_output(
            db,
            project_id=project_id,
            run_id=run_id,
            kind=kind,
            content=content,
            payload=payload,
            at=recorded_at,
        )
    except Exception:  # noqa: BLE001 -- see above
        logger.warning("tracing output for run %s failed", run_id, exc_info=True)
    return row


def _consider_compaction(
    project_id: str,
    agent: str,
    conversation_id: Optional[str],
    kind: Optional[str],
    payload: Optional[Dict[str, Any]],
) -> None:
    if kind == "status" and isinstance(payload, dict) and payload.get("phase") == "compacted":
        # A runner compacted this conversation (slice 5 D4): that counts as its checkpoint
        # threshold being crossed. Dispatched, never awaited, and never raising: the row is
        # already committed, so a raise here would answer 500 for a stored row. `payload` may be
        # None on the self-report route. Imported locally, as `record_context_usage` does.
        from .checkpoint_trigger import consider_from_compaction

        try:
            consider_from_compaction(project_id, agent, conversation_id, payload)
        except Exception:  # noqa: BLE001 -- a consideration never fails the recording
            logger.warning(
                "dispatching a compaction's checkpoint consideration failed", exc_info=True
            )


def resolve_usage_limit(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in `limit_tokens` from the model catalog, and derive `percent` from it.

    Claude reports how many tokens a request carried but not how large its window is; it reports
    the window separately, in a different message, with no tokens. Waiting for those two to meet
    is what produced 329 samples and zero usable percentages. The catalog is authoritative about
    the window, and the sample already knows its model — so the reading completes here, on its
    own, at the one place every write path funnels through.

    Nothing is invented: a model the catalog does not declare leaves `limit_tokens` and `percent`
    as they were. A sample that already carries a limit (Codex reports its own) is untouched, and
    so is one that says it is not a measurement (`unavailable`, `unsupported`): Copilot's
    `usage_update` with no `size` came back as 1.22% of a catalog window nobody measured (F538).
    """
    if payload.get("status") in ("unavailable", "unsupported"):
        return payload
    if payload.get("limit_tokens") is not None or payload.get("percent") is not None:
        return payload
    context_tokens = payload.get("context_tokens")
    if not isinstance(context_tokens, int) or isinstance(context_tokens, bool):
        return payload
    model = payload.get("model")
    limit = context_window_for_model(model) if isinstance(model, str) else None
    if not limit or limit <= 0:
        return payload
    return {
        **payload,
        "limit_tokens": limit,
        "percent": round(min(100.0, max(0.0, (context_tokens / limit) * 100)), 2),
    }


async def record_context_usage(
    db: AsyncSession, project_id: str, agent: str, sample_payload: Dict[str, Any]
) -> str:
    """Persist a context-usage snapshot and broadcast it, mirroring `POST .../context-usage`.

    Returns "ok", "ignored" (a strictly-older observation for the same agent), or "unchanged"
    (a newer observation whose measurement is identical to the latest persisted one).
    """
    payload = resolve_usage_limit({**sample_payload, "agent": agent})
    # F733: a "measured" reading that measured nothing -- Claude's end-of-turn `result` reports
    # the window with no token count, ~40 ms after the turn's real reading -- is not recorded. It
    # doubled every Claude turn's readings, showed in Logs as "a context reading with no
    # measurement", and could never yield a percentage; the trigger ignores it anyway. A reading
    # that says it is not a measurement (`unavailable`, `unsupported`) is still recorded: that is
    # information about the runner, and it scopes the read path's session fallback.
    if (
        payload.get("status") == "measured"
        and payload.get("context_tokens") is None
        and payload.get("percent") is None
    ):
        return "ignored"

    # Which conversation this reading belongs to.
    #
    # `UsageSample.to_payload` does not carry one — it is built by the runner parsers, which know
    # a session id and nothing about AgentWeave's own threading. Without it every reading reached
    # the checkpoint trigger with `conversation_id=None` and was dropped at its first guard, so
    # **no automatic checkpoint could ever fire**. Resolved here rather than pushed onto every
    # caller, and resolved read-only: unlike `record_agent_output` this never creates a
    # conversation, because a usage sample is not evidence that a thread exists.
    conversation_id = payload.get("conversation_id")
    if conversation_id is None:
        session_id = payload.get("session_id")
        if session_id:
            conversation_id = (
                await db.execute(
                    select(Conversation.id).where(
                        Conversation.project_id == project_id,
                        Conversation.agent == agent,
                        Conversation.provider_session_id == session_id,
                    )
                )
            ).scalar_one_or_none()
        if conversation_id is None:
            conversation = await latest_open_conversation(db, project_id=project_id, agent=agent)
            conversation_id = conversation.id if conversation else None
        payload["conversation_id"] = conversation_id
    latest_result = await db.execute(
        select(EventLog)
        .where(
            EventLog.project_id == project_id,
            # The literal form, so this seek uses `ix_event_logs_context_agent_ts` (migration 0144).
            IS_CONTEXT_READING,
            EventLog.agent == agent,
        )
        .order_by(EventLog.timestamp.desc())
        .limit(1)
    )
    latest = latest_result.scalars().first()
    unchanged = False
    if latest and isinstance(latest.data, dict):
        latest_observed = latest.data.get("observed_at")
        observed_at = payload.get("observed_at")
        if (
            isinstance(latest_observed, (int, float))
            and isinstance(observed_at, (int, float))
            and observed_at <= latest_observed
        ):
            return "ignored"
        # Several readings can land within the same turn with the same measurement and only
        # a newer `observed_at` distinguishing them (e.g. context usage sampled more than once
        # before it changes) — a real activity log ended up 65% duplicate rows of an unchanged
        # number this way. Same measurement, newer timestamp: keep the row's freshness (still
        # feeds the checkpoint trigger below) but do not persist or broadcast a second row.
        # Compared field-by-field rather than just `context_tokens`/`percent` — those can
        # coincide across turns that differ in `model` (a conversation whose model changed
        # turn to turn, at identical token counts, is not the same reading) or other fields.
        latest_signal = {k: v for k, v in latest.data.items() if k != "observed_at"}
        current_signal = {k: v for k, v in payload.items() if k != "observed_at"}
        unchanged = latest_signal == current_signal
    if not unchanged:
        await persist_event(
            db, project_id, "context_warning", payload, agent=agent, severity="info"
        )
        await sse_manager.broadcast(project_id, "context_warning", payload)

    # A reading is the moment context pressure first becomes knowable, so it is where the
    # checkpoint policy is evaluated. Dispatched, never awaited: generation is a blocking CLI
    # spawn measured at ~19s live, and awaiting it here would stall every turn's output behind
    # a checkpoint. Imported locally because `checkpoint_trigger` imports the generation stack,
    # which imports this module.
    from .checkpoint_trigger import consider_from_reading

    # `payload`, not `sample_payload`. The conversation is resolved onto `payload` above;
    # `sample_payload` is the runner parser's dict, which never carries one — reading it from
    # there passed None every time and the trigger dropped every reading at its first guard.
    consider_from_reading(project_id, agent, payload.get("conversation_id"), payload)
    return "unchanged" if unchanged else "ok"


# ---------------------------------------------------------------------------------------------
# Streamed lines: shown at once, written in batches (D3 of
# `turn-starts-approvals-and-evidence-never-freeze-the-hub`)
# ---------------------------------------------------------------------------------------------

#: The longest a streamed line waits to be written with the lines after it. Its broadcast does not
#: wait: the line is on screen as soon as the Hub has it.
STREAM_FLUSH_SECONDS = float(os.environ.get("AW_STREAM_FLUSH_SECONDS") or 1.0)
#: A burst this long is written at once rather than after the wait.
STREAM_FLUSH_LINES = 64
#: Spacing between attempts when the database is locked, as `_record_observation`'s.
STREAM_RETRY_DELAYS = (0.5, 2.0)


@dataclass(frozen=True)
class StagedLine:
    """What `record_agent_output` is given to stage a streamed line rather than record one."""

    row_id: str
    recorded_at: datetime


#: `record_agent_output`'s shape: the writer stages each line through the callable its executor
#: handed it, so whatever that executor records through is what writes the line.
Recorder = Callable[..., Awaitable[Any]]


@dataclass
class _StreamedLine:
    project_id: str
    agent: str
    session_id: Optional[str]
    conversation_id: str
    content: str
    kind: Optional[str]
    payload: Optional[Dict[str, Any]]
    run_id: Optional[str]
    sequence: Optional[int]
    row_id: str
    recorded_at: datetime
    record: Recorder
    retry_delays: Tuple[float, ...]


@dataclass
class _StreamWriter:
    """One per event loop, so nothing bound to a finished loop reaches the next one (tests)."""

    pending: List[_StreamedLine] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    timer: Optional[asyncio.TimerHandle] = None
    #: `(project, agent, session)` known to have output, so a session's first line is told apart
    #: without asking the database about rows still waiting to be written.
    sessions_seen: set = field(default_factory=set)
    flushes: set = field(default_factory=set)
    #: A write that failed for a reason other than the lock, kept for the run it belongs to: its
    #: next `flush_streamed` raises it, as the line's own write used to raise into the run.
    failures: Dict[Optional[str], BaseException] = field(default_factory=dict)


_writers: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _StreamWriter]" = (
    weakref.WeakKeyDictionary()
)


def _writer() -> _StreamWriter:
    loop = asyncio.get_running_loop()
    writer = _writers.get(loop)
    if writer is None:
        writer = _writers[loop] = _StreamWriter()
    return writer


async def stream_agent_output(
    project_id: str,
    agent: str,
    *,
    content: str,
    session_id: Optional[str],
    conversation_id: str,
    kind: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    sequence: Optional[int] = None,
    db: Optional[AsyncSession] = None,
    record: Optional[Recorder] = None,
    retry_delays: Tuple[float, ...] = STREAM_RETRY_DELAYS,
) -> None:
    """Record one streamed line of a run the Hub is executing: broadcast now, written soon.

    *record* is what the line is written through (`record_agent_output` unless the executor
    passes its own), called with `staged=` at the write; *retry_delays* space its attempts on a
    locked database, as `_record_observation`'s did for one line.

    The same row, span and frames as `record_agent_output` -- scrubbed the same way, stamped with
    the moment the Hub received it -- but the database work is shared by every line that arrives
    within `STREAM_FLUSH_SECONDS` (D3): one session and one commit for a burst instead of one per
    line, and the run's chat span read and rewritten once per batch instead of once per line. The
    dashboard applies the broadcast row directly, so what it shows does not wait for the write.
    `flush_streamed` writes everything waiting; the executors call it before a run is reported
    finished, and the Hub's shutdown calls it last.
    """
    content = run_secrets.scrub(run_id, content)
    payload = run_secrets.scrub(run_id, payload)
    content = redact_text_secrets(content)
    payload = redact_text_secrets(payload)
    writer = _writer()
    is_new_session = False
    if session_id:
        seen = (project_id, agent, session_id)
        if seen not in writer.sessions_seen:
            # One read per session per process; a line already waiting counts as written.
            if not any(
                line.session_id == session_id
                and line.agent == agent
                and line.project_id == project_id
                for line in writer.pending
            ):
                async with contextlib.AsyncExitStack() as stack:
                    if db is None:
                        db = await stack.enter_async_context(async_session_factory())
                    is_new_session = (
                        await db.execute(
                            select(AgentOutput.id)
                            .where(
                                AgentOutput.project_id == project_id,
                                AgentOutput.agent == agent,
                                AgentOutput.session_id == session_id,
                            )
                            .limit(1)
                        )
                    ).scalar() is None
            if len(writer.sessions_seen) > 4096:
                writer.sessions_seen.clear()
            writer.sessions_seen.add(seen)
    line = _StreamedLine(
        project_id=project_id,
        agent=agent,
        session_id=session_id,
        conversation_id=conversation_id,
        content=content,
        kind=kind,
        payload=payload,
        run_id=run_id,
        sequence=sequence,
        row_id=f"out-{short_id()}",
        recorded_at=datetime.now(timezone.utc),
        record=record or record_agent_output,
        retry_delays=tuple(retry_delays),
    )
    writer.pending.append(line)
    await sse_manager.broadcast(
        project_id,
        "agent_output",
        {
            "id": line.row_id,
            "agent": agent,
            "session_id": session_id,
            "conversation_id": conversation_id,
            "content": content,
            "kind": kind,
            "payload": payload,
            "run_id": run_id,
            "sequence": sequence,
            "timestamp": line.recorded_at.isoformat(),
        },
    )
    if is_new_session:
        await sse_manager.broadcast(
            project_id, "agent_session_changed", {"agent": agent, "session_id": session_id}
        )
    if len(writer.pending) >= STREAM_FLUSH_LINES:
        _flush_soon(writer, 0.0)
    elif writer.timer is None:
        _flush_soon(writer, STREAM_FLUSH_SECONDS)


def _flush_soon(writer: _StreamWriter, delay: float) -> None:
    if writer.timer is not None:
        writer.timer.cancel()
    loop = asyncio.get_running_loop()

    def _start() -> None:
        writer.timer = None
        task = loop.create_task(_flush_logged())
        writer.flushes.add(task)
        task.add_done_callback(writer.flushes.discard)

    writer.timer = loop.call_later(delay, _start)


async def _flush_logged() -> None:
    try:
        await flush_streamed()
    except Exception:  # noqa: BLE001 -- a timed write has nobody to raise to
        logger.exception("writing streamed output failed")


async def flush_streamed(run_id: Optional[str] = None) -> None:
    """Write every streamed line still waiting, in the order received; return once it is stored.

    Each line keeps the treatment its own write had (F359): a locked database is retried with the
    line's delays and the line dropped with a warning if the lock outlasts them, so a lock never
    fails the run; anything else raises. A failure in a timed write is kept and raised by the next
    flush for that run (*run_id*), which the executors call before reporting the run finished."""
    writer = _writer()
    async with writer.lock:
        if writer.timer is not None:
            writer.timer.cancel()
            writer.timer = None
        batch, writer.pending = writer.pending, []
        try:
            written = await _write_batch(batch) if batch else []
        except Exception as exc:
            for run in {line.run_id for line in batch}:
                writer.failures[run] = exc
            raise
        finally:
            failure = writer.failures.pop(run_id, None) if run_id is not None else None
        if failure is not None:
            raise failure
    for line in written:
        _consider_compaction(
            line.project_id, line.agent, line.conversation_id, line.kind, line.payload
        )


def _is_locked(exc: BaseException) -> bool:
    return isinstance(exc, OperationalError) and "database is locked" in str(exc)


async def _write_batch(batch: List[_StreamedLine]) -> List[_StreamedLine]:
    """One session and one commit for *batch*; returns the lines stored.

    A line whose staging meets the lock is retried after its delay, the whole transaction from the
    start because the session rolled back, and dropped once it has failed as often as it may; a
    lock at the commit retries the batch the same way. The runs' trace cursors are restored before
    each retry, so a rolled-back attempt leaves no trace of itself in them."""
    lines = list(batch)
    failures: Dict[int, int] = {}
    runs = {line.run_id for line in lines if line.run_id}
    cursors = traces.cursor_snapshot(runs)
    while lines:
        failed_at: Optional[int] = None
        error: Optional[BaseException] = None
        async with async_session_factory() as db:
            traces.defer_chat_parts(db)
            try:
                for index, line in enumerate(lines):
                    failed_at = index
                    await line.record(
                        db,
                        line.project_id,
                        line.agent,
                        content=line.content,
                        session_id=line.session_id,
                        conversation_id=line.conversation_id,
                        kind=line.kind,
                        payload=line.payload,
                        run_id=line.run_id,
                        sequence=line.sequence,
                        staged=StagedLine(row_id=line.row_id, recorded_at=line.recorded_at),
                    )
                failed_at = None
                await traces.write_deferred_parts(db)
                await db.commit()
                return lines
            except Exception as exc:  # noqa: BLE001 -- sorted below
                if not _is_locked(exc):
                    raise
                error = exc
                await db.rollback()
        traces.cursor_restore(cursors)
        # The line that met the lock, or the first one when it was the commit.
        index = failed_at if failed_at is not None else 0
        line = lines[index]
        failures[id(line)] = failures.get(id(line), 0) + 1
        delays = line.retry_delays
        if failures[id(line)] > len(delays):
            logger.warning(
                "Dropped output %s for run %s: the database stayed locked through %d attempts (%s)",
                line.sequence,
                line.run_id,
                len(delays) + 1,
                error,
            )
            del lines[index]
            continue
        await asyncio.sleep(delays[failures[id(line)] - 1])
    return lines
