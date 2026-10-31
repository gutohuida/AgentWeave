"""The probe the never-freeze tests rest on: a real hold counts, a late wake from an idle poll does
not. Without the first those tests prove nothing; without the second they fail on a loaded machine.
"""

import asyncio
import gc
import time

import pytest

from ._loop_lag import GIT_DELAY, STALL_LIMIT, LagProbe


@pytest.mark.asyncio
async def test_a_blocking_call_on_the_loop_counts_as_a_stall():
    async with LagProbe() as probe:
        time.sleep(GIT_DELAY)
    assert probe.worst >= STALL_LIMIT


@pytest.mark.asyncio
async def test_a_counted_stall_says_why_it_was_counted():
    async with LagProbe() as probe:
        time.sleep(GIT_DELAY)
    assert " ms late" in probe.why and "samples" in probe.why


def _cycles(count: int) -> list:
    return [[[]] for _ in range(count)]


@pytest.mark.asyncio
async def test_collecting_a_heap_built_before_the_window_does_not_count():
    earlier = _cycles(1_500_000)
    async with LagProbe() as probe:
        gc.collect()
        await asyncio.sleep(0.03)
    assert earlier
    assert probe.worst < STALL_LIMIT, probe.why


@pytest.mark.asyncio
async def test_collecting_what_the_window_allocated_counts_as_a_stall():
    async with LagProbe() as probe:
        during = _cycles(1_500_000)
        gc.collect()
        await asyncio.sleep(0.03)
    assert during
    assert probe.worst >= STALL_LIMIT


@pytest.mark.asyncio
async def test_the_probe_leaves_nothing_frozen():
    async with LagProbe():
        assert gc.get_freeze_count() > 0
    assert gc.get_freeze_count() == 0


@pytest.mark.asyncio
async def test_work_held_on_the_loop_counts_as_a_stall():
    async with LagProbe() as probe:
        end = time.thread_time() + GIT_DELAY  # CPU time: a busy machine gives less of it per second
        while time.thread_time() < end:
            sum(range(1000))
    assert probe.worst >= STALL_LIMIT


@pytest.mark.asyncio
async def test_an_idle_loop_reads_as_polling():
    async with LagProbe() as probe:
        await asyncio.sleep(0.2)
        samples = list(probe._loop_samples)
    assert samples and probe._waiting_to_wake(samples[0][0], samples[-1][0])


@pytest.mark.asyncio
async def test_a_lock_wait_and_a_call_holding_the_gil_count_as_stalls():
    import re
    import threading

    lock = threading.Lock()
    lock.acquire()
    timer = threading.Timer(GIT_DELAY, lock.release)
    async with LagProbe() as probe:
        timer.start()
        lock.acquire()
    assert probe.worst >= STALL_LIMIT

    async with LagProbe() as probe:
        re.match(r"(a+)+$", "a" * 27 + "b")  # backtracks while holding the GIL
    assert probe.worst >= STALL_LIMIT


@pytest.mark.asyncio
async def test_a_worker_thread_holding_the_gil_counts_as_a_stall():
    import re

    loop = asyncio.get_running_loop()
    async with LagProbe() as probe:
        await loop.run_in_executor(None, re.match, r"(a+)+$", "a" * 26 + "b")
    assert probe.worst >= STALL_LIMIT


@pytest.mark.asyncio
async def test_a_blocking_call_keeping_the_gil_counts_as_a_stall():
    import sys

    if sys.platform != "win32":
        pytest.skip("PyDLL sleep is probed on Windows")
    import ctypes

    sleep = ctypes.PyDLL("kernel32").Sleep  # a PyDLL call does not release the GIL
    async with LagProbe() as probe:
        sleep(int(GIT_DELAY * 1000))
    assert probe.worst >= STALL_LIMIT


@pytest.mark.asyncio
async def test_starting_a_thread_behind_a_gil_holder_counts_as_a_stall():
    import re
    import threading

    holder = threading.Thread(target=re.match, args=(r"(a+)+$", "a" * 26 + "b"))
    async with LagProbe() as probe:
        holder.start()
        await asyncio.sleep(0.02)
        started = threading.Thread(target=lambda: None)
        started.start()  # waits for the new thread, which needs the GIL the holder has
        started.join()
    holder.join()
    assert probe.worst >= STALL_LIMIT
