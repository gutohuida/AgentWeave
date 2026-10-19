"""A project's API requests as spans (`everything-the-hub-does-is-in-a-trace`, D3 and D4).

`RequestTraceMiddleware` wraps every HTTP request in an `aw.request` span, current for the
request's duration (`traces.current_span`, D2), and when the answer is sent decides whether to keep
it (trace-D4): every request that is not a GET or HEAD, every request made with a run's credential,
every 4xx and 5xx, and every request slower than a second. The operator's other reads (the app's
polling) and the SSE stream are kept only when the project's trace settings ask (`record_reads`).

The project and the run come from what the authentication dependencies stamped on the request
scope (`auth.PROJECT_SCOPE_KEY`, `auth.RUN_SCOPE_KEY`), so the token is looked up once; a request
nothing authenticated for a project is not recorded. A run's request is a span in that run's trace,
never a trace of its own (D4). The span is handed to the writer's queue (`traces.enqueue`, D1):
nothing here touches the database, and nothing here can fail the request.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from . import traces
from .auth import PROJECT_SCOPE_KEY, RUN_SCOPE_KEY

logger = logging.getLogger(__name__)

#: A read slower than this is recorded whoever made it.
SLOW_SECONDS = 1.0
_READS = ("GET", "HEAD")


def _keep(*, method: str, run_id: Optional[str], status: int, stream: bool, elapsed: float) -> bool:
    routine = (
        run_id is None and method in _READS and status < 400 and (stream or elapsed <= SLOW_SECONDS)
    )
    return not routine


def _route_template(scope: Dict[str, Any]) -> str:
    """The matched route's full path template (`/api/v1/projects/{project_id}/tasks`).

    FastAPI 0.141 keeps included routers nested, so `scope["route"]` is the innermost route with
    its own path only; the full template is on the effective route context it records. Earlier
    versions flatten, and the route's own path is already the full one."""
    fastapi_scope = scope.get("fastapi")
    context = (
        fastapi_scope.get("effective_route_context") if isinstance(fastapi_scope, dict) else None
    )
    for candidate in (context, scope.get("route")):
        template = getattr(candidate, "path_format", None) or getattr(candidate, "path", None)
        if template:
            return str(template)
    return scope.get("path", "")


def _finish(
    scope: Dict[str, Any],
    span: traces.PendingSpan,
    *,
    status: int,
    stream: bool,
    elapsed: float,
) -> None:
    project_id = scope.get(PROJECT_SCOPE_KEY)
    if not project_id:
        return
    run_id = scope.get(RUN_SCOPE_KEY)
    method = scope.get("method", "")
    keep = _keep(method=method, run_id=run_id, status=status, stream=stream, elapsed=elapsed)
    if not keep and not traces.records_reads(project_id):
        return
    route = _route_template(scope)
    span.project_id = project_id
    span.run_id = run_id
    span.name = f"{method} {route}"
    span.end_time = traces._now()
    span.attributes = {
        "http.request.method": method,
        "http.route": route,
        "http.response.status_code": status,
        "url.path": traces.redact(run_id, scope.get("path", "")),
        "aw.actor": "run" if run_id else "operator",
        "aw.project.id": project_id,
        "aw.run.id": run_id,
        **span.attributes,
    }
    if status >= 500:  # a server span's error is the server's (OTel HTTP conventions)
        span.status = "error"
        span.status_message = span.status_message or f"HTTP {status}"
    traces.enqueue(span)


class RequestTraceMiddleware:
    """Pure ASGI, so a streamed answer (SSE, the export) passes through unbuffered."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        span = traces.PendingSpan(
            project_id="", name="", operation="aw.request", start_time=traces._now()
        )
        started = time.monotonic()
        status = 500
        stream = False

        async def traced_send(message) -> None:
            nonlocal status, stream
            if message.get("type") == "http.response.start":
                status = message.get("status", 500)
                for name, value in message.get("headers") or []:
                    if name.lower() == b"content-type" and value.startswith(b"text/event-stream"):
                        stream = True
            await send(message)

        token = traces.set_current(span)
        try:
            await self.app(scope, receive, traced_send)
        except Exception as exc:
            status = 500
            span.status_message = traces.redact(None, f"{type(exc).__name__}: {exc}")
            raise
        finally:
            traces.reset_current(token)
            try:
                _finish(
                    scope, span, status=status, stream=stream, elapsed=time.monotonic() - started
                )
            except Exception:  # noqa: BLE001 -- recording a request never fails it (D1)
                logger.debug("recording a request span failed", exc_info=True)
