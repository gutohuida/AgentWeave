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
from typing import Any, Dict, List

from sse_starlette.event import JSONServerSentEvent, ServerSentEvent


class SSEManager:
    def __init__(self) -> None:
        # project_id -> list of asyncio.Queue
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}

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
        try:
            subscribers.remove(queue)
        except ValueError:
            pass
        if not subscribers:
            self._subscribers.pop(project_id, None)

    async def broadcast(self, project_id: str, event_type: str, data: Any) -> None:
        """Push an SSE event to all subscribers of a project.

        Builds a JSONServerSentEvent with the event name and JSON-serialized
        payload. The events endpoint yields this directly to
        EventSourceResponse, which produces the correct wire format:
            event: <event_type>\\r\\n
            data: <json>\\r\\n
            \\r\\n
        """
        event = JSONServerSentEvent(data=data, event=event_type)
        for q in list(self._subscribers.get(project_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Slow consumer — drop event rather than block


# Helper so the /api/v1/events generator can produce the "connected" frame
# as a proper ServerSentEvent without re-importing sse_starlette.
def make_connected_event() -> ServerSentEvent:
    """ServerSentEvent sent as the first frame on every SSE connection.

    Replaces the previous hand-crafted `"data: connected\\n\\n"` string
    (which sse_starlette was double-wrapping as `data: data: connected`).
    """
    return ServerSentEvent(data="connected", event="connected")


sse_manager = SSEManager()
