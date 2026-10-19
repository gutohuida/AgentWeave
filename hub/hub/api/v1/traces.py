"""A project's traces: list, read, export as OTLP JSON, clear, and the OTLP push settings.

`a-run-is-a-trace-you-can-export` (trace-1019). Operator routes, on the project credential. The
fixed paths (`export`, `settings`, `by-run`) are declared before `/{trace_id}` so none of them is
read as a trace id.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import traces
from ...auth import get_project
from ...db.engine import async_session_factory, get_session
from ...db.models import Run, TraceSettings
from ...schemas.common import RequestModel

router = APIRouter(prefix="/traces", tags=["traces"])

MAX_PAGE = 2000


def _bounds(since: Optional[str], until: Optional[str]):
    try:
        start, end = traces.parse_bound(since), traces.parse_bound(until)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if start is not None and end is not None and end <= start:
        raise HTTPException(status_code=422, detail="`until` must be after `since`")
    return start, end


@router.get("")
async def list_project_traces(
    limit: int = Query(50, ge=1, le=200),
    before: Optional[str] = Query(None),
    run_id: Optional[str] = Query(None),
    task_id: Optional[str] = Query(None),
    conversation_id: Optional[str] = Query(None),
    operation: Optional[str] = Query(
        None,
        max_length=32,
        description="Only traces whose root is this operation: invoke_agent, chat, aw.request, ...",
    ),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The project's traces, newest first. `task_id`/`conversation_id` select the traces of the
    runs that worked that task or ran in that conversation; `operation` one kind of trace."""
    project_id, _ = project
    run_ids = None
    if run_id or task_id or conversation_id:
        query = select(Run.id).where(Run.project_id == project_id)
        if run_id:
            query = query.where(Run.id == run_id)
        if task_id:
            query = query.where(Run.task_id == task_id)
        if conversation_id:
            query = query.where(Run.conversation_id == conversation_id)
        run_ids = list((await session.execute(query)).scalars().all())
    try:
        return await traces.list_traces(
            session, project_id, limit=limit, before=before, run_ids=run_ids, operation=operation
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"`before` is not a cursor: {exc}") from exc


@router.get("/export")
async def export_traces(
    since: Optional[str] = Query(None, description="YYYY-MM-DD or ISO datetime, inclusive"),
    until: Optional[str] = Query(None, description="YYYY-MM-DD or ISO datetime, exclusive"),
    project: Tuple[str, str] = Depends(get_project),
):
    """Every trace of the project that started in the range, as one OTLP/HTTP JSON
    `ExportTraceServiceRequest`, streamed a page at a time."""
    project_id, _ = project
    start, end = _bounds(since, until)
    label = "-".join(part for part in (since, until) if part) or "all"
    filename = f"traces-{project_id}-{label}.json".replace(":", "")
    return StreamingResponse(
        traces.stream_export(async_session_factory, project_id, start, end),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("")
async def clear_project_traces(
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Delete every trace of the project that started in the range (all of them with neither
    bound). Runs, conversations and their timelines are untouched."""
    project_id, _ = project
    start, end = _bounds(since, until)
    result = await traces.clear_traces(session, project_id, start, end)
    await session.commit()
    return result


class TraceSettingsUpdate(RequestModel):
    otlp_endpoint: Optional[str] = Field(default=None, max_length=1024)
    #: Replaces the whole set when given; values are never returned.
    otlp_headers: Optional[Dict[str, str]] = None
    export_enabled: Optional[bool] = None
    #: Record the operator's routine reads (the app's polling) and the SSE stream too (trace-D4).
    record_reads: Optional[bool] = None


async def _settings_body(session: AsyncSession, project_id: str) -> dict:
    row = await session.get(TraceSettings, project_id)
    counts = await traces.trace_counts(session, project_id)
    return {
        "otlp_endpoint": row.otlp_endpoint if row else None,
        "otlp_header_names": sorted((row.otlp_headers or {}).keys()) if row else [],
        "export_enabled": bool(row.export_enabled) if row else False,
        "enabled_at": row.enabled_at.isoformat() if row and row.enabled_at else None,
        "last_export_at": row.last_export_at.isoformat() if row and row.last_export_at else None,
        "last_error": row.last_error if row else None,
        "exported_spans": row.exported_spans if row else 0,
        "record_reads": bool(row.record_reads) if row else False,
        **counts,
    }


@router.get("/settings")
async def get_trace_settings(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    return await _settings_body(session, project_id)


@router.put("/settings")
async def update_trace_settings(
    body: TraceSettingsUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    row = await session.get(TraceSettings, project_id)
    if row is None:
        row = TraceSettings(project_id=project_id, otlp_headers={}, export_enabled=False)
        session.add(row)
    fields = body.model_fields_set
    if "otlp_endpoint" in fields:
        endpoint = (body.otlp_endpoint or "").strip() or None
        if endpoint is not None:
            parsed = urlparse(endpoint)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise HTTPException(
                    status_code=422,
                    detail="The OTLP endpoint must be an http(s) URL, e.g. http://127.0.0.1:4318",
                )
        row.otlp_endpoint = endpoint
    if "otlp_headers" in fields:
        headers = body.otlp_headers or {}
        for name in headers:
            if not name.strip() or any(ch in name for ch in ":\r\n"):
                raise HTTPException(status_code=422, detail=f"{name!r} is not a header name")
        row.otlp_headers = {name.strip(): value for name, value in headers.items()}
    if "export_enabled" in fields and body.export_enabled is not None:
        if body.export_enabled and not row.export_enabled:
            # Only spans that end from now on are pushed; the download is for history.
            row.enabled_at = datetime.now(timezone.utc)
            row.last_error = None
        row.export_enabled = body.export_enabled
    if "record_reads" in fields and body.record_reads is not None:
        row.record_reads = body.record_reads
    if row.export_enabled and not row.otlp_endpoint:
        raise HTTPException(status_code=422, detail="Set an OTLP endpoint before enabling export")
    await session.commit()
    traces.set_record_reads(project_id, bool(row.record_reads))
    return await _settings_body(session, project_id)


@router.get("/by-run/{run_id}")
async def get_run_trace(
    run_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=MAX_PAGE),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    found = await traces.get_trace(
        session, project_id, traces.trace_id_for_run(run_id), offset=offset, limit=limit
    )
    if found is None:
        raise HTTPException(status_code=404, detail="This run has no trace")
    return found


@router.get("/{trace_id}")
async def get_one_trace(
    trace_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=MAX_PAGE),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    found = await traces.get_trace(session, project_id, trace_id, offset=offset, limit=limit)
    if found is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return found
