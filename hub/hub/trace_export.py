"""Pushing ended spans to a project's OTLP/HTTP endpoint (`a-run-is-a-trace-you-can-export`, D4).

An outbox: a span is pushed once it has ended (`ended`), and marked with `exported_at` when the
endpoint accepted it. A lifespan task drains it every few seconds, so a run never waits on an
exporter, a Hub restart loses nothing (the marks are rows), and an endpoint that is down is retried
on the next pass with its error shown in the project's trace settings.

Off by default (trace-D1): only a project whose `trace_settings` row is enabled and names an
endpoint is pushed, and only spans that ended after it was enabled. OTLP/HTTP JSON is one POST to
`<endpoint>/v1/traces`; it is sent with the standard library rather than an SDK or a new HTTP
dependency, in a worker thread, with a short timeout.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select, update

from . import traces
from .db.engine import async_session_factory
from .db.models import TraceSettings, TraceSpan

logger = logging.getLogger(__name__)

#: A project whose endpoint failed is not tried again before this (monotonic seconds), doubling
#: per failure up to five minutes, so an endpoint that is down costs a line every few minutes.
_retry_after: Dict[str, float] = {}
_failures: Dict[str, int] = {}
MAX_BACKOFF_SECONDS = 300.0

#: Seconds between passes; `AW_TRACE_PUSH_INTERVAL` overrides it.
PUSH_INTERVAL_SECONDS = 5.0
#: Spans per POST.
BATCH = 200
TIMEOUT_SECONDS = 10.0


def traces_url(endpoint: str) -> str:
    """`<endpoint>/v1/traces`, unless the operator gave the signal path already."""
    base = endpoint.rstrip("/")
    return base if base.endswith("/v1/traces") else f"{base}/v1/traces"


def _post(url: str, body: bytes, headers: Dict[str, str]) -> int:
    request = urllib.request.Request(  # noqa: S310 -- an operator-configured http(s) endpoint
        url,
        data=body,
        method="POST",
        headers={**headers, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        return response.status


async def push_project(project_id: str) -> int:
    """Push one batch of the project's ended, unexported spans. Returns how many were accepted."""
    async with async_session_factory() as db:
        settings = await db.get(TraceSettings, project_id)
        if settings is None or not settings.export_enabled or not settings.otlp_endpoint:
            return 0
        query = select(TraceSpan).where(
            TraceSpan.project_id == project_id,
            TraceSpan.ended.is_(True),
            TraceSpan.exported_at.is_(None),
        )
        if settings.enabled_at is not None:
            query = query.where(TraceSpan.end_time >= settings.enabled_at)
        spans: List[TraceSpan] = list(
            (await db.execute(query.order_by(TraceSpan.end_time).limit(BATCH))).scalars().all()
        )
        if not spans:
            return 0
        endpoint = settings.otlp_endpoint
        headers = dict(settings.otlp_headers or {})
        body = json.dumps(traces.otlp_payload(project_id, spans), ensure_ascii=False).encode(
            "utf-8"
        )
        ids = [span.span_id for span in spans]
    error: Optional[str] = None
    try:
        status = await asyncio.to_thread(_post, traces_url(endpoint), body, headers)
        if status >= 300:
            error = f"the endpoint answered {status}"
    except urllib.error.HTTPError as exc:
        error = f"the endpoint answered {exc.code}"
    except Exception as exc:  # noqa: BLE001 -- recorded for the operator, retried next pass
        error = f"{type(exc).__name__}: {exc}"
    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        settings = await db.get(TraceSettings, project_id)
        if error is None:
            await db.execute(
                update(TraceSpan)
                .where(TraceSpan.span_id.in_(ids))
                .values(exported_at=now)
                .execution_options(synchronize_session=False)
            )
        if settings is not None:
            settings.last_error = error
            if error is None:
                settings.last_export_at = now
                settings.exported_spans = (settings.exported_spans or 0) + len(ids)
        await db.commit()
    loop = asyncio.get_running_loop()
    if error is not None:
        failures = _failures.get(project_id, 0) + 1
        _failures[project_id] = failures
        _retry_after[project_id] = loop.time() + min(
            MAX_BACKOFF_SECONDS, push_interval() * (2 ** min(failures, 10))
        )
        logger.warning("pushing %d spans of %s failed: %s", len(ids), project_id, error)
        return 0
    _failures.pop(project_id, None)
    _retry_after.pop(project_id, None)
    return len(ids)


async def push_once() -> int:
    """One pass over every project with push enabled; a full batch is drained before returning."""
    async with async_session_factory() as db:
        projects = list(
            (
                await db.execute(
                    select(TraceSettings.project_id).where(
                        TraceSettings.export_enabled.is_(True),
                        TraceSettings.otlp_endpoint.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
    pushed = 0
    now = asyncio.get_running_loop().time()
    for project_id in projects:
        if _retry_after.get(project_id, 0.0) > now:
            continue
        while True:
            sent = await push_project(project_id)
            pushed += sent
            if sent < BATCH:
                break
    return pushed


def push_interval() -> float:
    try:
        return max(0.2, float(os.environ.get("AW_TRACE_PUSH_INTERVAL", PUSH_INTERVAL_SECONDS)))
    except ValueError:
        return PUSH_INTERVAL_SECONDS


async def run_pusher() -> None:
    """The lifespan task: a pass every `push_interval()` seconds until cancelled."""
    interval = push_interval()
    while True:
        try:
            await push_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- a pass that fails is retried, never fatal
            logger.warning("the trace push pass failed", exc_info=True)
        await asyncio.sleep(interval)
