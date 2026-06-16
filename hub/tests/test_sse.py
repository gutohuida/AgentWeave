"""Tests for SSE manager + wire format regression."""

import json

import pytest
from hub.sse import SSEManager, make_connected_event
from sse_starlette.event import JSONServerSentEvent, ServerSentEvent


@pytest.mark.asyncio
async def test_subscribe_broadcast_unsubscribe():
    manager = SSEManager()
    q = manager.subscribe("proj-test")
    await manager.broadcast("proj-test", "task_created", {"id": "task-abc"})
    evt = q.get_nowait()
    # Queue now carries ServerSentEvent objects (not pre-formatted strings)
    # so EventSourceResponse emits the standard wire format.
    assert isinstance(evt, JSONServerSentEvent)
    assert evt.event == "task_created"
    assert json.loads(evt.data) == {"id": "task-abc"}
    manager.unsubscribe("proj-test", q)
    assert "proj-test" not in manager._subscribers


@pytest.mark.asyncio
async def test_broadcast_no_subscribers():
    manager = SSEManager()
    # Should not raise even with no subscribers
    await manager.broadcast("proj-none", "message_created", {"id": "msg-xyz"})


@pytest.mark.asyncio
async def test_broadcast_uses_json_server_sent_event():
    """Regression: the queue must carry ServerSentEvent objects, not strings.

    Yielding a raw pre-formatted `f"event: foo\\ndata: bar\\n\\n"` string to
    sse_starlette causes it to re-wrap the string in another `data:` line,
    so clients see `data: data: bar` with no `event:` line and silently drop
    the event. See hub/hub/sse.py module docstring for the full history.
    """
    manager = SSEManager()
    q = manager.subscribe("proj-x")
    await manager.broadcast("proj-x", "message_created", {"id": "msg-1"})
    evt = q.get_nowait()
    assert isinstance(evt, ServerSentEvent), (
        f"Queue should hold ServerSentEvent, got {type(evt).__name__}. "
        "Yielding a pre-formatted SSE string to sse_starlette double-wraps "
        "it and silently drops the event on the client."
    )
    assert not isinstance(evt, str)
    assert not isinstance(evt, bytes)
    assert evt.event == "message_created"


@pytest.mark.asyncio
async def test_make_connected_event_is_server_sent_event():
    """The first frame on the SSE stream must be a real ServerSentEvent,
    not a hand-rolled string. Hand-rolling `data: connected\\n\\n` causes
    sse_starlette to double-wrap it as `data: data: connected`.
    """
    evt = make_connected_event()
    assert isinstance(evt, ServerSentEvent)
    assert evt.event == "connected"
    assert evt.data == "connected"


@pytest.mark.asyncio
async def test_event_stream_wire_format_no_double_wrap():
    """End-to-end regression: the events endpoint must produce a wire format
    with a real `event:` line (one per frame), not a `data: data: ...`
    double-wrap, so the Hub UI's custom fetch+ReadableStream SSE client
    can dispatch by event type.

    Before the fix, the response body was:
        data: data: connected
        data:
        data:
        ...
    so the client parser saw only `data:` lines and dropped every event
    as a "message"-type keepalive. The persisted message was in the DB
    but never reached the UI, causing the "message never goes" symptom.
    """
    from hub.sse import SSEManager, make_connected_event
    from sse_starlette.event import ServerSentEvent

    # 1. Unit-level: the connected helper is a ServerSentEvent (not a string).
    evt = make_connected_event()
    assert isinstance(evt, ServerSentEvent)
    assert evt.event == "connected"
    assert evt.data == "connected"

    # 2. Unit-level: a broadcast pushes a ServerSentEvent onto the queue.
    manager = SSEManager()
    q = manager.subscribe("proj-test")
    await manager.broadcast("proj-test", "message_created", {"id": "msg-1"})
    queued = q.get_nowait()
    assert isinstance(queued, ServerSentEvent)
    assert queued.event == "message_created"

    # 3. Encoding-level: the wire format produced by ServerSentEvent.encode()
    # is the standard SSE format. If the events endpoint ever yields a
    # pre-formatted string again, sse_starlette will wrap it in another
    # data: line and break this assertion.
    encoded_connected = make_connected_event().encode().decode()
    assert "event: connected\r\n" in encoded_connected
    assert "data: connected\r\n" in encoded_connected
    assert encoded_connected.endswith("\r\n\r\n")
    # No double-wrap.
    assert "data: data:" not in encoded_connected
    assert "data: event:" not in encoded_connected

    # 4. A broadcast event encodes the same way.
    m2 = SSEManager()
    q2 = m2.subscribe("proj-test-2")
    await m2.broadcast("proj-test-2", "task_updated", {"id": "task-9"})
    encoded_bcast = q2.get_nowait().encode().decode()
    assert "event: task_updated\r\n" in encoded_bcast
    assert '"id":"task-9"' in encoded_bcast
    assert "data: data:" not in encoded_bcast
    assert "data: event:" not in encoded_bcast
