"""Traces of everything the Hub and its agents do (`a-run-is-a-trace-you-can-export`, trace-1019).

A run is one OpenTelemetry-shaped trace, named with the GenAI semantic conventions: its root is an
`invoke_agent` span carrying the prompt; each model call is a `chat` span, each tool call an
`execute_tool` span; a permission decision the run reports is an `aw.judge` span under its tool's
span; permission and `ask_user` waits and deliveries of queued input are spans of their own; a
runner's `retrying` status and its errors are span events. A worker invocation (manager jobs,
titles, checkpoints, distillation, vault reports) is a trace of one `chat` span.

**One writer per fact (design D1).** This module is the only writer of `trace_spans`, and each
function here is called from the seam that already records the fact it traces, inside that seam's
transaction: `start_run` from the run's creation, `observe_output` from `record_agent_output`,
`record_judge` from `/permission-decisions`, `record_deliveries` from `deliver_entries_with_run`,
`finish_run` from `record_turn_usage` (every end of every run passes it), `record_worker` from
`worker.record_invocation`. Nothing here keeps a second account that could drift: the permission and
`ask_user` waits are read from their own rows when the run ends.

**What the Hub does around the runs (`everything-the-hub-does-is-in-a-trace`, D1).** A request
(`aw.request`, recorded by `trace_requests.RequestTraceMiddleware`) is not written in the
transaction of what it records: it is put on an in-memory queue and written in batches by one
lifespan writer (`run_span_writer`), so a request never waits for its span and a span that cannot
be written never reaches the request; it is counted as dropped instead. The span being recorded is
the current one (`current_span`, a contextvar, D2), for what later attaches to it.

Ids are OTLP's (32 hex for a trace, 16 for a span) and deterministic: a run's trace id comes from
its run id, a tool span's from the run and the call, a model call's from the run and its position.
So a judge decision reported before its tool call was recorded still lands under it, and a write
retried on a locked database rewrites the same row instead of adding a second.

**Content is redacted (D2).** Every string stored passes `redact`: the run's registered secret
values (`run_secrets.scrub`) and the named secret patterns (`redact_text_secrets`), the same two
passes `record_agent_output` applies to the timeline. What arrives from `record_agent_output` has
already had both; the prompt, a judge's reason, a queued message and a worker's prompt and answer
have them here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
)

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from . import __version__, run_secrets
from .db.models import PermissionRequest, Question, Run, TraceSettings, TraceSpan
from .runner_events import redact_text_secrets

logger = logging.getLogger(__name__)

#: `gen_ai.provider.name` for each runner CLI the Hub spawns.
PROVIDERS = {"claude": "anthropic", "codex": "openai", "copilot": "github_copilot"}

#: Attributes whose value is content (prompt, response, tool I/O, a message): what the in-app view
#: collapses, and what the export carries as a JSON string.
CONTENT_ATTRIBUTES = (
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.tool.call.arguments",
    "gen_ai.tool.call.result",
    "aw.queue.content",
    "aw.question.text",
    "aw.question.answer",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hex(text: str, size: int) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:size]


def trace_id_for_run(run_id: str) -> str:
    return _hex(f"trace:run:{run_id}", 32)


def trace_id_for_worker(invocation_id: str) -> str:
    return _hex(f"trace:worker:{invocation_id}", 32)


def _span_id(*parts: str) -> str:
    return _hex("span:" + "\x1f".join(parts), 16)


def root_span_id(run_id: str) -> str:
    return _span_id("root", run_id)


def tool_span_id(run_id: str, call_id: str) -> str:
    return _span_id("tool", run_id, call_id)


def chat_span_id(run_id: str, segment: int) -> str:
    return _span_id("chat", run_id, str(segment))


def redact(run_id: Optional[str], value: Any) -> Any:
    """*value* with the run's registered secrets and the named secret patterns replaced."""
    return redact_text_secrets(run_secrets.scrub(run_id, value))


def _text_message(role: str, text: Optional[str]) -> List[Dict[str, Any]]:
    return [{"role": role, "parts": [{"type": "text", "content": text or ""}]}]


# --- the run's trace -------------------------------------------------------------------------


@dataclass
class _Cursor:
    """Where a live run's trace is: which model call is open, and where the next one starts.

    In memory only, and rebuilt from the rows when missing (a Hub restart), so it decides nothing
    a row does not also say; the ids it yields are deterministic either way."""

    trace_started_at: datetime
    boundary: datetime
    segment: int = 0
    chat_open: bool = False


_cursors: Dict[str, _Cursor] = {}


def start_run(
    session: AsyncSession,
    run: Run,
    *,
    prompt: Optional[str],
    runner: Optional[str],
    model: Optional[str],
    task_id: Optional[str] = None,
) -> None:
    """Stage the root span of *run*'s trace in *session*, which commits it with the run."""
    if run.started_at is None:
        # Set here, not left to the column default, so the root and the run start together.
        run.started_at = _now()
    started = run.started_at
    attributes: Dict[str, Any] = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": run.agent,
        "gen_ai.conversation.id": run.conversation_id,
        "gen_ai.provider.name": PROVIDERS.get(runner or "", runner),
        "gen_ai.request.model": model,
        "gen_ai.input.messages": redact(run.id, _text_message("user", prompt)),
        "aw.run.id": run.id,
        "aw.project.id": run.project_id,
        "aw.runner.cli": runner,
        "aw.run.initiator": run.initiator,
        "aw.task.id": task_id or run.task_id,
        "aw.run.retry_of": run.divergence_source_run_id,
        "aw.run.workspace": run.workspace_dir,
    }
    session.add(
        TraceSpan(
            span_id=root_span_id(run.id),
            trace_id=trace_id_for_run(run.id),
            parent_span_id=None,
            project_id=run.project_id,
            run_id=run.id,
            name=f"invoke_agent {run.agent}",
            operation="invoke_agent",
            status="unset",
            start_time=started,
            trace_started_at=started,
            attributes={k: v for k, v in attributes.items() if v is not None},
            events=[],
        )
    )
    _cursors[run.id] = _Cursor(trace_started_at=started, boundary=started)


async def _cursor(db: AsyncSession, run_id: str) -> Optional[_Cursor]:
    cursor = _cursors.get(run_id)
    if cursor is not None:
        return cursor
    root = await db.get(TraceSpan, root_span_id(run_id))
    if root is None:
        return None  # a run that started before traces existed, or whose trace was cleared
    segments = (
        await db.execute(
            select(func.count())
            .select_from(TraceSpan)
            .where(TraceSpan.run_id == run_id, TraceSpan.operation == "chat")
        )
    ).scalar_one()
    # Whatever model call was open belonged to the process that is gone; the next one is new.
    last_end = (
        await db.execute(select(func.max(TraceSpan.end_time)).where(TraceSpan.run_id == run_id))
    ).scalar_one()
    if isinstance(last_end, str):  # an aggregate skips the column's type decorator
        last_end = datetime.fromisoformat(last_end)
    if last_end is not None and last_end.tzinfo is None:
        last_end = last_end.replace(tzinfo=timezone.utc)
    cursor = _Cursor(
        trace_started_at=root.trace_started_at,
        boundary=last_end or root.start_time,
        segment=segments,
        chat_open=False,
    )
    _cursors[run_id] = cursor
    return cursor


def _child(
    *,
    span_id: str,
    run_id: str,
    project_id: str,
    parent: str,
    name: str,
    operation: str,
    start: datetime,
    trace_started_at: datetime,
    attributes: Dict[str, Any],
) -> TraceSpan:
    return TraceSpan(
        span_id=span_id,
        trace_id=trace_id_for_run(run_id),
        parent_span_id=parent,
        project_id=project_id,
        run_id=run_id,
        name=name,
        operation=operation,
        status="unset",
        start_time=start,
        trace_started_at=trace_started_at,
        attributes={k: v for k, v in attributes.items() if v is not None},
        events=[],
    )


async def _chat_span(
    db: AsyncSession, project_id: str, run_id: str, cursor: _Cursor, at: datetime
) -> TraceSpan:
    if not cursor.chat_open:
        cursor.chat_open = True
    span_id = chat_span_id(run_id, cursor.segment)
    span = await db.get(TraceSpan, span_id)
    if span is None:
        root = await db.get(TraceSpan, root_span_id(run_id))
        model = (root.attributes or {}).get("gen_ai.request.model") if root else None
        provider = (root.attributes or {}).get("gen_ai.provider.name") if root else None
        span = _child(
            span_id=span_id,
            run_id=run_id,
            project_id=project_id,
            parent=root_span_id(run_id),
            name=f"chat {model}" if model else "chat",
            operation="chat",
            start=min(cursor.boundary, at),
            trace_started_at=cursor.trace_started_at,
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": model,
                "gen_ai.provider.name": provider,
                "gen_ai.output.messages": [{"role": "assistant", "parts": []}],
            },
        )
        db.add(span)
    return span


def _append_part(span: TraceSpan, part: Dict[str, Any], at: datetime) -> None:
    attributes = dict(span.attributes or {})
    messages = list(
        attributes.get("gen_ai.output.messages") or [{"role": "assistant", "parts": []}]
    )
    last = dict(messages[-1])
    last["parts"] = [*last.get("parts", []), part]
    messages[-1] = last
    attributes["gen_ai.output.messages"] = messages
    span.attributes = attributes  # reassigned: a JSON column does not see an in-place change
    span.end_time = at


async def _add_event(
    db: AsyncSession, run_id: str, name: str, at: datetime, attributes: Dict[str, Any]
) -> bool:
    """Append an event to *run_id*'s root; False when the run has no trace."""
    root = await db.get(TraceSpan, root_span_id(run_id))
    if root is None:
        return False
    root.events = [
        *(root.events or []),
        {
            "name": name,
            "time": at.isoformat(),
            "attributes": {k: v for k, v in attributes.items() if v is not None},
        },
    ]
    return True


async def observe_output(
    db: AsyncSession,
    *,
    project_id: str,
    run_id: Optional[str],
    kind: Optional[str],
    content: str,
    payload: Optional[Dict[str, Any]],
    at: datetime,
) -> None:
    """Trace one recorded stream event (already scrubbed by `record_agent_output`). Called in
    that function's transaction, before its commit, so the row and the span commit together."""
    if not run_id or not kind:
        return
    cursor = await _cursor(db, run_id)
    if cursor is None:
        return
    data = payload if isinstance(payload, dict) else {}
    if kind in ("text", "thinking"):
        span = await _chat_span(db, project_id, run_id, cursor, at)
        part_type = "text" if kind == "text" else "reasoning"
        _append_part(span, {"type": part_type, "content": content}, at)
    elif kind == "tool_use":
        call_id = data.get("call_id") or f"seq-{at.timestamp()}"
        tool = data.get("tool") or "tool"
        span = await _chat_span(db, project_id, run_id, cursor, at)
        _append_part(
            span,
            {"type": "tool_call", "id": call_id, "name": tool, "arguments": data.get("input")},
            at,
        )
        tool_span = await db.get(TraceSpan, tool_span_id(run_id, call_id))
        if tool_span is None:
            db.add(
                _child(
                    span_id=tool_span_id(run_id, call_id),
                    run_id=run_id,
                    project_id=project_id,
                    parent=root_span_id(run_id),
                    name=f"execute_tool {tool}",
                    operation="execute_tool",
                    start=at,
                    trace_started_at=cursor.trace_started_at,
                    attributes={
                        "gen_ai.operation.name": "execute_tool",
                        "gen_ai.tool.name": tool,
                        "gen_ai.tool.call.id": call_id,
                        "gen_ai.tool.type": "function",
                        "gen_ai.tool.call.arguments": data.get("input"),
                        "aw.tool.category": data.get("category"),
                        "aw.tool.input_truncated": data.get("truncated") or None,
                    },
                )
            )
    elif kind == "tool_result":
        call_id = data.get("call_id")
        if call_id:
            span_id = tool_span_id(run_id, call_id)
            tool_span = await db.get(TraceSpan, span_id)
            if tool_span is None:
                tool = data.get("tool") or "tool"
                tool_span = _child(
                    span_id=span_id,
                    run_id=run_id,
                    project_id=project_id,
                    parent=root_span_id(run_id),
                    name=f"execute_tool {tool}",
                    operation="execute_tool",
                    start=at,
                    trace_started_at=cursor.trace_started_at,
                    attributes={
                        "gen_ai.operation.name": "execute_tool",
                        "gen_ai.tool.name": tool,
                        "gen_ai.tool.call.id": call_id,
                    },
                )
                db.add(tool_span)
            attributes = dict(tool_span.attributes or {})
            attributes["gen_ai.tool.call.result"] = data.get("output")
            if data.get("truncated"):
                attributes["aw.tool.result_truncated"] = True
            if data.get("status"):
                attributes["aw.tool.status"] = data.get("status")
            tool_span.attributes = attributes
            tool_span.end_time = at
            tool_span.ended = True
            if data.get("is_error") or data.get("status") == "interrupted":
                tool_span.status = "error"
                tool_span.status_message = content
            else:
                tool_span.status = "ok"
        # A tool's result goes back to the model, so the model call that asked for it is over and
        # the next one starts here.
        chat = await db.get(TraceSpan, chat_span_id(run_id, cursor.segment))
        if chat is not None and cursor.chat_open:
            chat.ended = True
            chat.end_time = chat.end_time or at
            chat.status = "ok"
            cursor.segment += 1
        cursor.chat_open = False
        cursor.boundary = at
    elif kind == "status":
        phase = data.get("phase") or "status"
        facts = {
            f"aw.status.{key}": value
            for key, value in data.items()
            if key not in ("version", "phase", "summary") and isinstance(value, (str, int, float))
        }
        name = "gen_ai.retry" if phase == "retrying" else f"aw.status.{phase}"
        await _add_event(db, run_id, name, at, {"aw.status.summary": content, **facts})
    elif kind == "error":
        await _add_event(
            db,
            run_id,
            "exception",
            at,
            {
                "exception.type": data.get("code"),
                "exception.message": data.get("message") or content,
                "aw.error.retryable": data.get("retryable"),
            },
        )
    elif kind == "diagnostic":
        await _add_event(
            db,
            run_id,
            "aw.diagnostic",
            at,
            {
                "aw.diagnostic.severity": data.get("severity"),
                "aw.diagnostic.code": data.get("code"),
                "aw.diagnostic.summary": content,
            },
        )


async def record_judge(
    db: AsyncSession,
    *,
    project_id: str,
    run_id: str,
    tool_name: str,
    tool_use_id: str,
    allowed: bool,
    reason: str,
    source: str,
) -> None:
    """Trace one permission decision a run reported (`/permission-decisions`), under its tool's
    span. Allowed decisions are traced too: this is the only place the Hub sees them."""
    root = await db.get(TraceSpan, root_span_id(run_id))
    if root is None:
        return
    at = _now()
    if tool_use_id:
        parent = tool_span_id(run_id, tool_use_id)
        span_id = _span_id("judge", run_id, tool_use_id)
    else:
        # No call id to join on: the latest still-open call of that tool, else the root.
        latest = (
            await db.execute(
                select(TraceSpan.span_id)
                .where(
                    TraceSpan.run_id == run_id,
                    TraceSpan.operation == "execute_tool",
                    TraceSpan.ended.is_(False),
                    TraceSpan.name == f"execute_tool {tool_name}",
                )
                .order_by(TraceSpan.start_time.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        parent = latest or root.span_id
        span_id = _span_id("judge", run_id, tool_name, at.isoformat())
    span = await db.get(TraceSpan, span_id)
    if span is None:
        span = _child(
            span_id=span_id,
            run_id=run_id,
            project_id=project_id,
            parent=parent,
            name=f"aw.judge {tool_name}",
            operation="aw.judge",
            start=at,
            trace_started_at=root.trace_started_at,
            attributes={},
        )
        db.add(span)
    span.attributes = {
        "gen_ai.tool.name": tool_name,
        "gen_ai.tool.call.id": tool_use_id or None,
        "aw.decision.allowed": allowed,
        "aw.decision.reason": redact(run_id, reason),
        "aw.decision.source": source,
    }
    span.attributes = {k: v for k, v in span.attributes.items() if v is not None}
    span.end_time = at
    span.ended = True


async def record_deliveries(
    db: AsyncSession, *, run: Run, entries: Sequence[Any], at: datetime
) -> None:
    """Trace each queued input *run* delivers: from its arrival to this delivery."""
    root_id = root_span_id(run.id)
    started = run.started_at or at
    for entry in entries:
        span_id = _span_id("deliver", run.id, entry.id)
        if await db.get(TraceSpan, span_id) is not None:
            continue
        span = _child(
            span_id=span_id,
            run_id=run.id,
            project_id=run.project_id,
            parent=root_id,
            name="aw.deliver",
            operation="aw.deliver",
            start=min(entry.arrived_at or at, at),
            trace_started_at=started,
            attributes={
                "aw.queue.entry_id": entry.id,
                "aw.queue.origin_type": entry.origin_type,
                "aw.queue.origin_agent": entry.origin_agent,
                "aw.queue.delivery_attempt": (entry.delivery_attempts or 0) + 1,
                "aw.queue.hop_depth": entry.hop_depth,
                "aw.queue.content": redact(run.id, entry.content),
            },
        )
        span.end_time = at
        span.ended = True
        span.status = "ok"
        db.add(span)


async def finish_run(db: AsyncSession, run_id: str, usage: Any = None) -> None:
    """Close *run_id*'s trace when the run ends, in the transaction that records its end.

    Every span still open ends where it last moved (or now); the waits the run opened are read from
    their own rows (`permission_requests`, `questions`) and traced; the root takes the run's
    status, error and usage. Idempotent: a second call rewrites the same rows."""
    cursor = _cursors.pop(run_id, None)
    root = await db.get(TraceSpan, root_span_id(run_id))
    if root is None:
        return
    run = await db.get(Run, run_id)
    now = (run.ended_at if run is not None and run.ended_at else None) or _now()
    started = root.trace_started_at if cursor is None else cursor.trace_started_at

    await db.execute(
        update(TraceSpan)
        .where(
            TraceSpan.run_id == run_id,
            TraceSpan.ended.is_(False),
            TraceSpan.span_id != root.span_id,
        )
        .values(ended=True, end_time=func.coalesce(TraceSpan.end_time, now))
        .execution_options(synchronize_session=False)
    )
    # The turn's last model call answered with text and the run ended normally: it completed.
    if run is not None and run.status != "failed":
        await db.execute(
            update(TraceSpan)
            .where(
                TraceSpan.run_id == run_id,
                TraceSpan.operation == "chat",
                TraceSpan.status == "unset",
            )
            .values(status="ok")
            .execution_options(synchronize_session=False)
        )

    requests = (
        (await db.execute(select(PermissionRequest).where(PermissionRequest.run_id == run_id)))
        .scalars()
        .all()
    )
    for request in requests:
        span_id = _span_id("permission", request.id)
        parent = tool_span_id(run_id, request.tool_use_id) if request.tool_use_id else root.span_id
        span = await db.get(TraceSpan, span_id)
        if span is None:
            span = _child(
                span_id=span_id,
                run_id=run_id,
                project_id=root.project_id,
                parent=parent,
                name=f"aw.permission_wait {request.tool_name}",
                operation="aw.permission_wait",
                start=request.created_at,
                trace_started_at=started,
                attributes={},
            )
            db.add(span)
        span.attributes = {
            k: v
            for k, v in {
                "gen_ai.tool.name": request.tool_name,
                "gen_ai.tool.call.id": request.tool_use_id or None,
                "aw.permission.request_id": request.id,
                "aw.permission.status": request.status,
                "aw.permission.decided_by": request.decided_by,
                "aw.permission.workspace_verdict": (
                    json.dumps(redact(run_id, request.workspace_verdict))
                    if request.workspace_verdict
                    else None
                ),
                "gen_ai.tool.call.arguments": json.dumps(
                    redact(run_id, request.tool_input or {}), ensure_ascii=False
                ),
            }.items()
            if v is not None
        }
        span.end_time = request.decided_at or now
        span.ended = True
        span.status = "ok" if request.status == "allowed" else "unset"

    questions = (
        (await db.execute(select(Question).where(Question.created_by_run_id == run_id)))
        .scalars()
        .all()
    )
    for question in questions:
        span_id = _span_id("ask", question.id)
        span = await db.get(TraceSpan, span_id)
        if span is None:
            span = _child(
                span_id=span_id,
                run_id=run_id,
                project_id=root.project_id,
                parent=root.span_id,
                name="aw.ask_user",
                operation="aw.ask_user",
                start=question.created_at,
                trace_started_at=started,
                attributes={},
            )
            db.add(span)
        ended_at = question.answered_at or question.declined_at or question.wait_ended_at or now
        span.attributes = {
            k: v
            for k, v in {
                "aw.question.id": question.id,
                "aw.question.header": question.header,
                "aw.question.text": redact(run_id, question.question),
                "aw.question.options": json.dumps(question.options or [], ensure_ascii=False),
                "aw.question.answered": question.answered,
                "aw.question.declined": question.declined,
                "aw.question.answer": redact(run_id, question.answer),
            }.items()
            if v is not None
        }
        span.end_time = max(ended_at, question.created_at)
        span.ended = True

    attributes = dict(root.attributes or {})
    if run is not None:
        attributes["aw.run.status"] = run.status
        if run.exit_code is not None:
            attributes["aw.run.exit_code"] = run.exit_code
        if run.snapshot_commit_sha:
            attributes["aw.run.snapshot_commit"] = run.snapshot_commit_sha
        if run.runner_version:
            attributes["aw.runner.version"] = run.runner_version
        if run.session_id:
            attributes["aw.provider.session_id"] = run.session_id
        if run.task_id:
            attributes["aw.task.id"] = run.task_id
    if usage is not None:
        for key, field in (
            ("gen_ai.response.model", "model"),
            ("gen_ai.usage.input_tokens", "input_tokens"),
            ("gen_ai.usage.output_tokens", "output_tokens"),
            ("aw.usage.total_tokens", "total_tokens"),
            ("aw.usage.cache_read_tokens", "cache_read_tokens"),
            ("aw.usage.cache_write_tokens", "cache_write_tokens"),
            ("aw.usage.reasoning_tokens", "reasoning_tokens"),
            ("aw.usage.api_equivalent_usd_micros", "api_equivalent_usd_micros"),
        ):
            value = getattr(usage, field, None)
            if value is not None:
                attributes[key] = value
        attributes["aw.usage.status"] = getattr(usage, "status", None)
    root.attributes = {k: v for k, v in attributes.items() if v is not None}
    root.end_time = now
    root.ended = True
    if run is not None and run.status == "failed":
        root.status = "error"
        root.status_message = redact(run_id, run.error) if run.error else "run failed"
    else:
        root.status = "ok"


def forget(run_id: str) -> None:
    _cursors.pop(run_id, None)


# --- worker invocations -----------------------------------------------------------------------


def worker_span(
    *,
    invocation_id: str,
    project_id: str,
    kind: str,
    cli: str,
    model: Optional[str],
    conversation_id: Optional[str],
    prompt: Optional[str],
    result: Any,
    ended_at: Optional[datetime] = None,
) -> TraceSpan:
    """The one span of a worker invocation's trace, for `record_invocation` to add beside it."""
    end = ended_at or _now()
    duration = getattr(result, "duration_ms", None)
    start = end - timedelta(milliseconds=duration) if duration else end
    usage = getattr(result, "usage", None)
    answer = getattr(result, "answer_text", None)
    attributes: Dict[str, Any] = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": PROVIDERS.get(cli, cli),
        "gen_ai.request.model": model,
        "gen_ai.conversation.id": conversation_id,
        "aw.worker.kind": kind,
        "aw.worker.invocation_id": invocation_id,
        "aw.worker.outcome": getattr(result, "outcome", None),
        "aw.runner.cli": cli,
        "aw.worker.exit_code": getattr(result, "exit_code", None),
    }
    if prompt is not None:
        attributes["gen_ai.input.messages"] = redact(None, _text_message("user", prompt))
    if answer is not None:
        attributes["gen_ai.output.messages"] = redact(None, _text_message("assistant", answer))
    if usage is not None:
        for key, field in (
            ("gen_ai.usage.input_tokens", "input_tokens"),
            ("gen_ai.usage.output_tokens", "output_tokens"),
            ("aw.usage.cache_read_tokens", "cache_read_tokens"),
            ("aw.usage.cache_write_tokens", "cache_write_tokens"),
            ("aw.usage.reasoning_tokens", "reasoning_tokens"),
            ("aw.usage.cost_usd_micros", "cost_usd_micros"),
        ):
            value = getattr(usage, field, None)
            if value is not None:
                attributes[key] = value
    ok = getattr(result, "outcome", None) == "ok"
    error = getattr(result, "error", None)
    return TraceSpan(
        span_id=_span_id("worker", invocation_id),
        trace_id=trace_id_for_worker(invocation_id),
        parent_span_id=None,
        project_id=project_id,
        run_id=None,
        name=f"chat {model}" if model else f"chat {cli}",
        operation="chat",
        status="ok" if ok else "error",
        status_message=None if ok else redact(None, error or getattr(result, "outcome", "")),
        start_time=start,
        end_time=end,
        ended=True,
        trace_started_at=start,
        attributes={k: v for k, v in attributes.items() if v is not None},
        events=[],
    )


# --- the Hub's own work: the span queue (everything-the-hub-does-is-in-a-trace, D1-D4) ---------


@dataclass
class PendingSpan:
    """A span of the Hub's own work, held in memory until the writer stores it.

    A span with `run_id` set nests in that run's trace (D4): the writer copies the run's trace id
    and start and parents it under the run's tool call open at `start_time`, else the run's root.
    Any other span is the root of a trace of its own."""

    project_id: str
    name: str
    operation: str
    start_time: datetime
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    end_time: Optional[datetime] = None
    status: str = "unset"
    status_message: Optional[str] = None
    run_id: Optional[str] = None
    span_id: str = field(default_factory=lambda: secrets.token_hex(8))
    trace_id: str = field(default_factory=lambda: secrets.token_hex(16))
    #: Writer passes a locked database refused this span (`flush_spans`).
    write_attempts: int = 0
    #: Handed to the writer (`enqueue`): what is appended now would never be written (D5).
    enqueued: bool = False
    #: Recorded even if its request would not be (a read that emitted an event, D5).
    keep: bool = False


@dataclass(frozen=True)
class RunTrace:
    """The current trace while a run's executor works (D5): the run's root, already written, so
    what attaches to it goes on the row, in the attaching session."""

    project_id: str
    run_id: str


#: Spans waiting for the writer; past `MAX_QUEUE` a span is dropped and counted, never waited on.
MAX_QUEUE = 10_000
#: Seconds between the writer's passes.
WRITE_INTERVAL_SECONDS = 1.0
_queue: List[PendingSpan] = []
#: Spans that could not be written, per project, since this process started (the settings show it).
_dropped: Dict[str, int] = {}
#: Projects that record the operator's routine reads (`trace_settings.record_reads`): read by the
#: request path, which never queries for it, and refreshed by the writer and the settings route.
_record_reads: Dict[str, bool] = {}

Current = Optional[PendingSpan | RunTrace]
_current: ContextVar[Current] = ContextVar("aw_current_span", default=None)


def current_span() -> Current:
    """The span of the work this code runs inside (a request, a run), if any (D2)."""
    return _current.get()


def set_current(span: Current) -> Token:
    return _current.set(span)


def reset_current(token: Token) -> None:
    _current.reset(token)


T = TypeVar("T")


async def within_run(project_id: str, run_id: str, work: Awaitable[T]) -> T:
    """Await *work* with *run_id*'s trace current (D5): the run's executor, so what it records
    lands on the run's trace instead of the request that started it (which it would inherit)."""
    token = set_current(RunTrace(project_id=project_id, run_id=run_id))
    try:
        return await work
    finally:
        reset_current(token)


#: The bound on an event's data stored on a span (D5), in characters of its JSON.
EVENT_DATA_LIMIT = 8 * 1024


def _event_record(
    run_id: Optional[str],
    *,
    event_id: str,
    event_type: str,
    data: Optional[Dict[str, Any]],
    agent: Optional[str],
    severity: str,
    loop_id: Optional[str],
    at: datetime,
) -> Dict[str, Any]:
    text = json.dumps(redact(run_id, data or {}), default=str, ensure_ascii=False)
    if len(text) > EVENT_DATA_LIMIT:
        text = text[:EVENT_DATA_LIMIT] + "... [truncated]"
    attributes = {
        "aw.event.id": event_id,
        "aw.event.severity": severity,
        "aw.agent": agent,
        "aw.loop.id": loop_id,
        "aw.event.data": text,
    }
    return {
        "name": event_type,
        "time": at.isoformat(),
        "attributes": {k: v for k, v in attributes.items() if v is not None},
    }


async def record_event(
    session: AsyncSession,
    *,
    project_id: str,
    event_id: str,
    event_type: str,
    data: Optional[Dict[str, Any]],
    agent: Optional[str],
    severity: str,
    loop_id: Optional[str],
) -> None:
    """Put the event `persist_event` is writing in a trace (D5, `every-event-is-in-a-trace`).

    On the current request's span while it is still being recorded; on the run's root while a
    run's executor is current; else a short ended `aw.event` span of its own, staged in *session*
    so the event and its span commit together."""
    at = _now()
    current = current_span()

    def _record(run_id: Optional[str]) -> Dict[str, Any]:
        return _event_record(
            run_id,
            event_id=event_id,
            event_type=event_type,
            data=data,
            agent=agent,
            severity=severity,
            loop_id=loop_id,
            at=at,
        )

    if isinstance(current, PendingSpan) and not current.enqueued:
        current.events.append(_record(current.run_id))
        current.keep = True
        current.project_id = current.project_id or project_id
        return
    if isinstance(current, RunTrace) and current.project_id == project_id:
        attached = _record(current.run_id)["attributes"]
        if await _add_event(session, current.run_id, event_type, at, attached):
            return
    record = _record(None)
    attributes = {
        "aw.event.type": event_type,
        "aw.event.id": event_id,
        "aw.event.severity": severity,
        "aw.project.id": project_id,
        "aw.agent": agent,
        "aw.loop.id": loop_id,
    }
    session.add(
        TraceSpan(
            span_id=secrets.token_hex(8),
            trace_id=secrets.token_hex(16),
            parent_span_id=None,
            project_id=project_id,
            run_id=None,
            name=event_type[:256],
            operation="aw.event",
            status="error" if severity == "error" else "unset",
            start_time=at,
            end_time=at,
            ended=True,
            trace_started_at=at,
            attributes={k: v for k, v in attributes.items() if v is not None},
            events=[record],
        )
    )


def records_reads(project_id: str) -> bool:
    return _record_reads.get(project_id, False)


def set_record_reads(project_id: str, value: bool) -> None:
    _record_reads[project_id] = bool(value)


def dropped_spans(project_id: str) -> int:
    return _dropped.get(project_id, 0)


def _drop(spans: Iterable[PendingSpan]) -> None:
    for span in spans:
        _dropped[span.project_id] = _dropped.get(span.project_id, 0) + 1


def enqueue(span: PendingSpan) -> None:
    """Hand *span* to the writer. Never blocks and never raises into the caller's work."""
    span.enqueued = True
    if len(_queue) >= MAX_QUEUE:
        _drop([span])
        return
    _queue.append(span)


def reset_spans() -> None:
    """Forget every queued span and count (a fresh database: the test suite's reset)."""
    _queue.clear()
    _dropped.clear()
    _record_reads.clear()


async def _tool_span_during(
    db: AsyncSession, run_id: str, start: datetime, end: datetime
) -> Optional[str]:
    """The run's newest tool call whose span overlaps [*start*, *end*] (D4).

    Overlap rather than "open when the request began": the runner's stream can deliver a tool
    call's line after the call into the Hub has started (measured on Claude: 50 ms later), and a
    tool span starts when its line is recorded. One that overlaps the request was recorded by the
    time the request ended, so the writer, which runs later, always sees it."""
    return (
        await db.execute(
            select(TraceSpan.span_id)
            .where(
                TraceSpan.run_id == run_id,
                TraceSpan.operation == "execute_tool",
                TraceSpan.start_time <= end,
                or_(TraceSpan.ended.is_(False), TraceSpan.end_time >= start),
            )
            .order_by(TraceSpan.start_time.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _write_spans(batch: Sequence[PendingSpan]) -> None:
    """Store *batch* in one transaction: the writer's only database write."""
    from .db.engine import async_session_factory

    async with async_session_factory() as db:
        for pending in batch:
            parent: Optional[str] = None
            trace_id, trace_started_at = pending.trace_id, pending.start_time
            if pending.run_id:
                root = await db.get(TraceSpan, root_span_id(pending.run_id))
                if root is None:
                    continue  # a run with no trace; its request is never a trace of its own
                trace_id, trace_started_at = root.trace_id, root.trace_started_at
                end = pending.end_time or pending.start_time
                parent = (
                    await _tool_span_during(db, pending.run_id, pending.start_time, end)
                    or root.span_id
                )
            db.add(
                TraceSpan(
                    span_id=pending.span_id,
                    trace_id=trace_id,
                    parent_span_id=parent,
                    project_id=pending.project_id,
                    run_id=pending.run_id,
                    name=pending.name[:256],
                    operation=pending.operation,
                    status=pending.status,
                    status_message=pending.status_message,
                    start_time=pending.start_time,
                    end_time=pending.end_time or pending.start_time,
                    ended=True,
                    trace_started_at=trace_started_at,
                    attributes={k: v for k, v in pending.attributes.items() if v is not None},
                    events=list(pending.events),
                )
            )
        await db.commit()


#: Passes a batch the locked database refused is offered again before it is dropped.
LOCKED_ATTEMPTS = 3


def _locked(exc: BaseException) -> bool:
    return isinstance(exc, OperationalError) and "database is locked" in str(exc)


async def flush_spans() -> int:
    """Write every queued span now. Returns how many were handed to the store.

    A batch the database refused because another writer held it past the busy timeout goes back on
    the queue for the next pass (a run's start can hold it that long), up to `LOCKED_ATTEMPTS`
    passes; any other failure, or the last of those, is logged and counted as dropped. Never
    raised."""
    if not _queue:
        return 0
    batch = list(_queue)
    _queue.clear()
    try:
        await _write_spans(batch)
    except Exception as exc:  # noqa: BLE001 -- a span write must never reach the work it records
        dropped = batch
        if _locked(exc):
            for span in batch:
                span.write_attempts += 1
            retry = [span for span in batch if span.write_attempts < LOCKED_ATTEMPTS]
            room = max(0, MAX_QUEUE - len(_queue))
            _queue[:0] = retry[:room]  # ahead of what arrived meanwhile: oldest first
            dropped = [span for span in batch if span.write_attempts >= LOCKED_ATTEMPTS]
            dropped += retry[room:]
        _drop(dropped)
        logger.warning(
            "writing %d trace spans failed (%s); %d dropped, the rest retried",
            len(batch),
            type(exc).__name__,
            len(dropped),
            exc_info=not _locked(exc),
        )
        return 0
    return len(batch)


async def _refresh_record_reads() -> None:
    from .db.engine import async_session_factory

    async with async_session_factory() as db:
        rows = (
            await db.execute(select(TraceSettings.project_id, TraceSettings.record_reads))
        ).all()
    for project_id, value in rows:
        _record_reads[project_id] = bool(value)


async def run_span_writer() -> None:
    """The lifespan writer (D1): drain the queue every `WRITE_INTERVAL_SECONDS` until cancelled,
    then once more, so a clean shutdown loses nothing queued."""
    try:
        await _refresh_record_reads()
    except Exception:  # noqa: BLE001 -- reads stay unrecorded until the next refresh
        logger.warning("reading the trace settings failed", exc_info=True)
    try:
        while True:
            await asyncio.sleep(WRITE_INTERVAL_SECONDS)
            await flush_spans()
    finally:
        await flush_spans()


# --- reading ----------------------------------------------------------------------------------


def span_dict(span: TraceSpan) -> Dict[str, Any]:
    return {
        "span_id": span.span_id,
        "trace_id": span.trace_id,
        "parent_span_id": span.parent_span_id,
        "name": span.name,
        "operation": span.operation,
        "status": span.status,
        "status_message": span.status_message,
        "start_time": span.start_time.isoformat(),
        "end_time": span.end_time.isoformat() if span.end_time else None,
        "ended": bool(span.ended),
        "attributes": span.attributes or {},
        "events": span.events or [],
    }


#: What a trace is, by its root's operation; a run's (`invoke_agent`) is told by its run id.
_KINDS = {"chat": "worker", "aw.request": "request", "aw.event": "event", "aw.work": "work"}


def trace_kind(root: TraceSpan) -> str:
    return "run" if root.run_id else _KINDS.get(root.operation, root.operation)


def _summary(root: TraceSpan, span_count: int) -> Dict[str, Any]:
    attributes = root.attributes or {}
    return {
        "trace_id": root.trace_id,
        "root_span_id": root.span_id,
        "run_id": root.run_id,
        "name": root.name,
        "operation": root.operation,
        "kind": trace_kind(root),
        "agent": attributes.get("gen_ai.agent.name"),
        "conversation_id": attributes.get("gen_ai.conversation.id"),
        "task_id": attributes.get("aw.task.id"),
        "worker_kind": attributes.get("aw.worker.kind"),
        "status": root.status,
        "status_message": root.status_message,
        "start_time": root.start_time.isoformat(),
        "end_time": root.end_time.isoformat() if root.end_time else None,
        "ended": bool(root.ended),
        "span_count": span_count,
    }


def _cursor_text(span: TraceSpan) -> str:
    return f"{span.start_time.isoformat()}|{span.span_id}"


async def list_traces(
    db: AsyncSession,
    project_id: str,
    *,
    limit: int = 50,
    before: Optional[str] = None,
    run_ids: Optional[Iterable[str]] = None,
    operation: Optional[str] = None,
) -> Dict[str, Any]:
    """The project's traces, newest first, one page (keyset on the root's start); with
    *operation*, only the traces whose root is that operation (D8)."""
    query = select(TraceSpan).where(
        TraceSpan.project_id == project_id, TraceSpan.parent_span_id.is_(None)
    )
    if operation:
        query = query.where(TraceSpan.operation == operation)
    if run_ids is not None:
        query = query.where(TraceSpan.run_id.in_(list(run_ids)))
    if before:
        stamp, _, span_id = before.partition("|")
        at = datetime.fromisoformat(stamp)
        query = query.where(
            or_(
                TraceSpan.start_time < at,
                and_(TraceSpan.start_time == at, TraceSpan.span_id < span_id),
            )
        )
    rows = (
        (
            await db.execute(
                query.order_by(TraceSpan.start_time.desc(), TraceSpan.span_id.desc()).limit(
                    limit + 1
                )
            )
        )
        .scalars()
        .all()
    )
    page = list(rows[:limit])
    counts: Dict[str, int] = {}
    if page:
        counts = dict(
            (
                await db.execute(
                    select(TraceSpan.trace_id, func.count())
                    .where(TraceSpan.trace_id.in_([row.trace_id for row in page]))
                    .group_by(TraceSpan.trace_id)
                )
            ).all()
        )
    return {
        "traces": [_summary(row, counts.get(row.trace_id, 1)) for row in page],
        "next_before": _cursor_text(page[-1]) if len(rows) > limit and page else None,
    }


async def get_trace(
    db: AsyncSession, project_id: str, trace_id: str, *, offset: int = 0, limit: int = 500
) -> Optional[Dict[str, Any]]:
    root = (
        await db.execute(
            select(TraceSpan).where(
                TraceSpan.project_id == project_id,
                TraceSpan.trace_id == trace_id,
                TraceSpan.parent_span_id.is_(None),
            )
        )
    ).scalar_one_or_none()
    if root is None:
        return None
    total = (
        await db.execute(
            select(func.count())
            .select_from(TraceSpan)
            .where(TraceSpan.project_id == project_id, TraceSpan.trace_id == trace_id)
        )
    ).scalar_one()
    spans = (
        (
            await db.execute(
                select(TraceSpan)
                .where(TraceSpan.project_id == project_id, TraceSpan.trace_id == trace_id)
                .order_by(TraceSpan.start_time, TraceSpan.span_id)
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {
        "trace_id": trace_id,
        "kind": trace_kind(root),
        "run_id": root.run_id,
        "root": span_dict(root),
        "spans": [span_dict(span) for span in spans],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


async def trace_counts(db: AsyncSession, project_id: str) -> Dict[str, Any]:
    spans, traces, oldest = (
        await db.execute(
            select(
                func.count(),
                func.count(func.distinct(TraceSpan.trace_id)),
                func.min(TraceSpan.trace_started_at),
            ).where(TraceSpan.project_id == project_id)
        )
    ).one()
    if isinstance(oldest, str):  # an aggregate skips the column's type decorator
        oldest = datetime.fromisoformat(oldest)
    if oldest is not None and oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    by_operation = dict(
        (
            await db.execute(
                select(TraceSpan.operation, func.count())
                .where(TraceSpan.project_id == project_id)
                .group_by(TraceSpan.operation)
            )
        ).all()
    )
    return {
        "span_count": spans,
        "trace_count": traces,
        "oldest_trace_at": oldest.isoformat() if oldest else None,
        "spans_by_operation": by_operation,
        "dropped_spans": dropped_spans(project_id),
    }


# --- export and clear (D3) --------------------------------------------------------------------


def parse_bound(value: Optional[str]) -> Optional[datetime]:
    """A date (`2026-10-19`, read as midnight UTC) or an ISO datetime, as an aware datetime."""
    if not value:
        return None
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), time.min, tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{value!r} is not a date (YYYY-MM-DD) or an ISO datetime") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _window(project_id: str, since: Optional[datetime], until: Optional[datetime]) -> List[Any]:
    clauses: List[Any] = [TraceSpan.project_id == project_id]
    if since is not None:
        clauses.append(TraceSpan.trace_started_at >= since)
    if until is not None:
        clauses.append(TraceSpan.trace_started_at < until)
    return clauses


async def clear_traces(
    db: AsyncSession, project_id: str, since: Optional[datetime], until: Optional[datetime]
) -> Dict[str, int]:
    """Delete every trace of the project that started in [since, until). Caller commits."""
    clauses = _window(project_id, since, until)
    traces = (
        await db.execute(select(func.count(func.distinct(TraceSpan.trace_id))).where(*clauses))
    ).scalar_one()
    result = await db.execute(delete(TraceSpan).where(*clauses))
    return {"deleted_spans": result.rowcount or 0, "deleted_traces": traces}


def _nanos(at: Optional[datetime]) -> str:
    if at is None:
        return "0"
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return str(int(at.timestamp()) * 1_000_000_000 + at.microsecond * 1000)


def _any_value(value: Any) -> Dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, (list, tuple)) and all(
        isinstance(item, (str, bool, int, float)) for item in value
    ):
        return {"arrayValue": {"values": [_any_value(item) for item in value]}}
    # Structured content (messages, tool arguments) travels as JSON text, which every OTLP backend
    # reads; the GenAI conventions allow it where structured attributes are unsupported.
    return {"stringValue": json.dumps(value, ensure_ascii=False, default=str)}


def _attributes(values: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {"key": key, "value": _any_value(value)}
        for key, value in values.items()
        if value is not None
    ]


_OTLP_STATUS = {"unset": 0, "ok": 1, "error": 2}
#: SPAN_KIND_INTERNAL (1) for the Hub's own work, CLIENT (3) for a call out to a model.
_OTLP_KIND = {"chat": 3}


def otlp_span(span: TraceSpan) -> Dict[str, Any]:
    status: Dict[str, Any] = {"code": _OTLP_STATUS.get(span.status, 0)}
    if span.status_message and span.status == "error":
        status["message"] = span.status_message
    body: Dict[str, Any] = {
        "traceId": span.trace_id,
        "spanId": span.span_id,
        "name": span.name,
        "kind": _OTLP_KIND.get(span.operation, 1),
        "startTimeUnixNano": _nanos(span.start_time),
        "endTimeUnixNano": _nanos(span.end_time or span.start_time),
        "attributes": _attributes(span.attributes or {}),
        "events": [
            {
                "timeUnixNano": _nanos(
                    datetime.fromisoformat(event["time"]) if event.get("time") else None
                ),
                "name": event.get("name", "event"),
                "attributes": _attributes(event.get("attributes") or {}),
            }
            for event in (span.events or [])
        ],
        "status": status,
    }
    if span.parent_span_id:
        body["parentSpanId"] = span.parent_span_id
    retry_of = (span.attributes or {}).get("aw.run.retry_of") if not span.parent_span_id else None
    if retry_of:
        body["links"] = [
            {
                "traceId": trace_id_for_run(retry_of),
                "spanId": root_span_id(retry_of),
                "attributes": _attributes({"aw.link": "retry_of"}),
            }
        ]
    return body


def _resource(project_id: str) -> Dict[str, Any]:
    return {
        "attributes": _attributes(
            {
                "service.name": "agentweave-hub",
                "service.version": __version__,
                "aw.project.id": project_id,
            }
        )
    }


SCOPE = {"name": "agentweave.hub", "version": __version__}


def otlp_payload(project_id: str, spans: Sequence[TraceSpan]) -> Dict[str, Any]:
    """One OTLP/HTTP JSON `ExportTraceServiceRequest` for *spans* of one project."""
    return {
        "resourceSpans": [
            {
                "resource": _resource(project_id),
                "scopeSpans": [{"scope": SCOPE, "spans": [otlp_span(span) for span in spans]}],
            }
        ]
    }


async def stream_export(
    session_factory: Any,
    project_id: str,
    since: Optional[datetime],
    until: Optional[datetime],
    page: int = 500,
) -> AsyncIterator[bytes]:
    """The export as OTLP JSON, produced a page at a time (keyset on trace start and span id), so a
    project kept forever is never held in memory whole."""
    head = json.dumps(
        {"resource": _resource(project_id), "scopeSpans": [{"scope": SCOPE, "spans": []}]},
        ensure_ascii=False,
    )
    # Split the empty span list open: everything before `[]` and the closing after it.
    marker = '"spans": []'
    prefix, _, suffix = head.partition(marker)
    yield ('{"resourceSpans": [' + prefix + '"spans": [').encode("utf-8")
    after: Optional[Tuple[datetime, str]] = None
    first = True
    while True:
        async with session_factory() as db:
            query = select(TraceSpan).where(*_window(project_id, since, until))
            if after is not None:
                query = query.where(
                    or_(
                        TraceSpan.trace_started_at > after[0],
                        and_(
                            TraceSpan.trace_started_at == after[0],
                            TraceSpan.span_id > after[1],
                        ),
                    )
                )
            rows = (
                (
                    await db.execute(
                        query.order_by(TraceSpan.trace_started_at, TraceSpan.span_id).limit(page)
                    )
                )
                .scalars()
                .all()
            )
        for span in rows:
            chunk = json.dumps(otlp_span(span), ensure_ascii=False)
            yield (chunk if first else "," + chunk).encode("utf-8")
            first = False
        if len(rows) < page:
            break
        after = (rows[-1].trace_started_at, rows[-1].span_id)
    yield ("]" + suffix + "]}").encode("utf-8")
