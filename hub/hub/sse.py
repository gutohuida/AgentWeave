"""SSE fan-out manager.

One SSEManager instance is shared across all requests.
Agents subscribe by calling .subscribe(project_id), which returns a queue.
After every write operation, call .broadcast(project_id, event_type, data).

The queue carries `sse_starlette.ServerSentEvent` objects (not pre-formatted
SSE wire strings). The /api/v1/events generator passes them straight to
`EventSourceResponse`, which encodes them with the correct `event:` and
`data:` lines.

Why not push a pre-formatted `"event: foo\\ndata: bar\\n\\n"` string?
sse_starlette treats any yielded string as the *data payload* of a
single-field ServerSentEvent and re-wraps it in another `data:` line.
The client then sees a doubled wire format
(`data: data: bar`) with no `event:` line, so the browser-side
EventSource / custom fetch() parser either ignores the event
(dispatches as the default `message` type) or surfaces the raw wire
format string as the payload. Pushing ServerSentEvent objects fixes
this once and for all.
"""

import asyncio
import contextlib
from typing import Any, Dict, List

from sse_starlette.event import JSONServerSentEvent, ServerSentEvent


class SSEManager:
    def __init__(self) -> None:
        # project_id -> list of asyncio.Queue
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        # one instance-level operator stream, fed by every project's broadcasts
        self._operator_subscribers: List[asyncio.Queue] = []

    def subscribe(self, project_id: str) -> asyncio.Queue:
        """Register a new SSE subscriber for a project. Returns the queue.

        The queue carries `sse_starlette.ServerSentEvent` (or subclass)
        instances, NOT pre-formatted SSE wire strings. See module docstring.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.setdefault(project_id, []).append(q)
        return q

    def unsubscribe(self, project_id: str, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue (called on client disconnect)."""
        subscribers = self._subscribers.get(project_id, [])
        with contextlib.suppress(ValueError):
            subscribers.remove(queue)
        if not subscribers:
            self._subscribers.pop(project_id, None)

    def subscribe_operator(self) -> asyncio.Queue:
        """Register a new subscriber for the one instance-level operator stream.

        Every project's broadcast also fans out here, envelope-stamped with
        that project's ID, so one connection sees every project's events —
        including a project with no open tab and no `subscribe(project_id)`
        listener of its own.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._operator_subscribers.append(q)
        return q

    def unsubscribe_operator(self, queue: asyncio.Queue) -> None:
        with contextlib.suppress(ValueError):
            self._operator_subscribers.remove(queue)

    async def broadcast(self, project_id: str, event_type: str, data: Any) -> None:
        """Push an SSE event to all subscribers of a project, plus the one
        operator stream with `project_id` stamped into the envelope.

        Builds a JSONServerSentEvent with the event name and JSON-serialized
        payload. The events endpoint yields this directly to
        EventSourceResponse, which produces the correct wire format:
            event: <event_type>\\r\\n
            data: <json>\\r\\n
            \\r\\n

        The operator envelope's `project_id` always comes from this method's
        own argument, never from `data` — a caller-supplied `project_id` key
        in `data` is overwritten, not trusted.
        """
        event = JSONServerSentEvent(data=data, event=event_type)
        for q in list(self._subscribers.get(project_id, [])):
            # Slow consumer — drop event rather than block. Kept as try/except
            # rather than contextlib.suppress: this runs per-subscriber on every
            # broadcast, and suppress() allocates a context manager each pass.
            try:  # noqa: SIM105
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

        if self._operator_subscribers:
            stamped_data = {**data, "project_id": project_id}
            operator_event = JSONServerSentEvent(data=stamped_data, event=event_type)
            for q in list(self._operator_subscribers):
                try:  # noqa: SIM105
                    q.put_nowait(operator_event)
                except asyncio.QueueFull:
                    pass


# Helper so the /api/v1/events generator can produce the "connected" frame
# as a proper ServerSentEvent without re-importing sse_starlette.
def make_connected_event() -> ServerSentEvent:
    """ServerSentEvent sent as the first frame on every SSE connection.

    Replaces the previous hand-crafted `"data: connected\\n\\n"` string
    (which sse_starlette was double-wrapping as `data: data: connected`).
    """
    return ServerSentEvent(data="connected", event="connected")


sse_manager = SSEManager()
