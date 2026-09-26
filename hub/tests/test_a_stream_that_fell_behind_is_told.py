"""F253: a subscriber whose queue overflowed is told with a `stream_gap` frame."""

import asyncio
import json

from hub.sse import SSEManager, stream_frames

QUEUE_SIZE = 256


def _never_disconnected():
    async def is_disconnected() -> bool:
        return False

    return is_disconnected


def _fill_and_overflow(mgr: SSEManager, queue, extra: int) -> None:
    for i in range(QUEUE_SIZE):
        mgr.publish("proj-a", "task_updated", {"n": i})
    for i in range(extra):
        # Spread across two projects on the operator stream: one count mixes them.
        mgr.publish("proj-a" if i % 2 else "proj-b", "task_updated", {"n": QUEUE_SIZE + i})


def test_operator_queue_counts_what_it_dropped():
    mgr = SSEManager()
    q = mgr.subscribe_operator()
    _fill_and_overflow(mgr, q, 10)
    assert q.qsize() == QUEUE_SIZE
    assert q.dropped == 10


def test_project_queue_counts_what_it_dropped():
    mgr = SSEManager()
    q = mgr.subscribe("proj-a")
    for i in range(QUEUE_SIZE + 4):
        mgr.publish("proj-a", "task_updated", {"n": i})
    assert q.qsize() == QUEUE_SIZE
    assert q.dropped == 4


def test_a_fresh_subscription_starts_at_zero():
    mgr = SSEManager()
    assert mgr.subscribe("proj-a").dropped == 0
    assert mgr.subscribe_operator().dropped == 0


async def _read(queue, count: int):
    frames = []
    gen = stream_frames(queue, _never_disconnected())
    for _ in range(count):
        frames.append(await asyncio.wait_for(gen.__anext__(), timeout=2))
    return frames


async def test_stream_frames_writes_one_gap_without_a_project_id():
    mgr = SSEManager()
    q = mgr.subscribe_operator()
    _fill_and_overflow(mgr, q, 10)

    # connected, first queued event, gap, then the remaining 255 queued events.
    frames = await _read(q, 1 + 1 + 1 + (QUEUE_SIZE - 1))
    assert frames[0].event == "connected"
    assert frames[1].event == "task_updated"
    assert frames[2].event == "stream_gap"
    assert json.loads(frames[2].encode().decode().split("data: ", 1)[1].split("\r\n")[0]) == {
        "dropped": 10,
        "severity": "warn",
    }
    assert "project_id" not in frames[2].encode().decode()
    assert [f.event for f in frames].count("stream_gap") == 1
    assert q.dropped == 0


async def test_a_burst_followed_by_silence_still_yields_the_gap():
    mgr = SSEManager()
    q = mgr.subscribe("proj-a")
    for i in range(QUEUE_SIZE + 1):
        mgr.publish("proj-a", "task_updated", {"n": i})
    # Nothing more is ever published: the gap must not wait for a next put.
    frames = await _read(q, 1 + QUEUE_SIZE + 1 - 255)  # connected, first event, gap
    assert [f.event for f in frames] == ["connected", "task_updated", "stream_gap"]


async def test_a_subscriber_that_never_overflowed_gets_no_gap():
    mgr = SSEManager()
    q = mgr.subscribe("proj-a")
    for i in range(5):
        mgr.publish("proj-a", "task_updated", {"n": i})
    frames = await _read(q, 6)
    assert [f.event for f in frames] == ["connected"] + ["task_updated"] * 5
