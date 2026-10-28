"""An open event stream holds no pooled database connection (FR-8, `streams-hold-no-connection`).

Measured before the fix: both stream routes authenticated through `Depends(get_session)`, a
request-scoped session closed only once the response has been sent, which for a stream is when
the tab goes away. So every open stream held one pooled connection; the pool holds 15, and the
16th stream waited out the 30s pool timeout, answered 500, and every other request waited with it.

`httpx.ASGITransport` buffers a whole response before returning it, so it can never hold a stream
open. These tests call the ASGI application themselves and keep each stream running until its
first frame has arrived, which is the state an open tab is in.
"""

import asyncio
import time
from typing import List, Tuple

import pytest

from hub.auth import _make_operator_ticket, _make_ticket
from hub.db.engine import engine

#: More than the pool's 5 + 10 overflow, so a leak cannot hide inside it.
STREAMS = 20


class _HeldStream:
    """One stream request in flight against the ASGI app, as an open EventSource is."""

    def __init__(self, application, path: str, query: str) -> None:
        self.status: List[int] = []
        self.first_frame = asyncio.Event()
        self._disconnect = asyncio.Event()
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": [(b"host", b"test"), (b"accept", b"text/event-stream")],
            "client": ("127.0.0.1", 1),
            "server": ("test", 80),
        }
        self._sent_request = False
        self.task = asyncio.create_task(application(scope, self._receive, self._send))

    async def _receive(self):
        if not self._sent_request:
            self._sent_request = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._disconnect.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message) -> None:
        if message["type"] == "http.response.start":
            self.status.append(message["status"])
        elif message["type"] == "http.response.body" and message.get("body"):
            self.first_frame.set()

    async def close(self) -> None:
        self._disconnect.set()
        try:
            await asyncio.wait_for(self.task, 5)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)


async def _hold_streams(app, path: str, query_for) -> Tuple[List[_HeldStream], int]:
    application = app._transport.app
    held: List[_HeldStream] = []
    opened = 0
    try:
        for _ in range(STREAMS + 1):
            stream = _HeldStream(application, path, query_for())
            held.append(stream)
            # Pre-fix the 16th waited 30s for a connection; 5s is ample for a stream that needs none.
            await asyncio.wait_for(stream.first_frame.wait(), 5)
            assert stream.status == [200]
            opened += 1
    except asyncio.TimeoutError:
        pass
    return held, opened


async def _assert_streams_leave_the_pool_free(app, auth_headers, path: str, query_for) -> None:
    held, opened = await _hold_streams(app, path, query_for)
    try:
        assert opened == STREAMS + 1, (
            f"only {opened} of {STREAMS + 1} streams received a first frame; "
            f"the pool has {engine.pool.checkedout()} connections checked out"
        )
        assert engine.pool.checkedout() == 0, "an open stream is holding a pooled connection"

        # Best of three: a pool leak makes every read wait out the 30s pool timeout, while one slow
        # read under a loaded suite (-n auto) says nothing about the pool.
        elapsed = float("inf")
        for _ in range(3):
            started = time.perf_counter()
            resp = await asyncio.wait_for(
                app.get("/api/v1/projects/proj-test/agents", headers=auth_headers), 10
            )
            elapsed = min(elapsed, time.perf_counter() - started)
            assert resp.status_code == 200, resp.text
        assert elapsed < 1.0, f"GET /agents took {elapsed:.2f}s with {opened} streams open"
    finally:
        await asyncio.gather(*(stream.close() for stream in held))


@pytest.mark.asyncio
async def test_more_project_streams_than_the_pool_holds_all_open(app, auth_headers):
    await _assert_streams_leave_the_pool_free(
        app,
        auth_headers,
        "/api/v1/projects/proj-test/events",
        lambda: f"token={_make_ticket('proj-test')[0]}",
    )


@pytest.mark.asyncio
async def test_more_operator_streams_than_the_pool_holds_all_open(app, auth_headers):
    await _assert_streams_leave_the_pool_free(
        app,
        auth_headers,
        "/api/v1/events",
        lambda: f"token={_make_operator_ticket()[0]}",
    )
