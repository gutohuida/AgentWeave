"""The probe the never-freeze tests rest on: a real hold counts, a late wake from an idle poll does
not. Without the first those tests prove nothing; without the second they fail on a loaded machine.
"""

import asyncio
import gc
import time

import pytest

from ._loop_lag import GIT_DELAY, STALL_LIMIT, LagProbe, _set_process_priority


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
    assert "seen at" in probe.why and "test_a_counted_stall" in probe.why


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
async def test_the_probe_raises_the_whole_process_and_puts_it_back():
    before = _set_process_priority()
    if before is None:
        pytest.skip("a process priority class is Windows'")
    _set_process_priority(before)
    async with LagProbe():
        during = _set_process_priority()
        _set_process_priority(during)
    after = _set_process_priority()
    _set_process_priority(after)
    assert during == 0x80
    assert after == before


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


def _suspend_this_process_from_outside(seconds: float):  # noqa: ANN202
    """Another process suspends every thread of this one for `seconds`, the way a machine short of
    cores or memory stops it: nothing here holds the GIL, and no sample is taken."""
    import os
    import subprocess
    import sys

    script = (
        "import ctypes, sys, time\n"
        "k = ctypes.WinDLL('kernel32'); n = ctypes.WinDLL('ntdll')\n"
        "k.OpenProcess.restype = ctypes.c_void_p\n"
        "n.NtSuspendProcess.argtypes = n.NtResumeProcess.argtypes = [ctypes.c_void_p]\n"
        "h = k.OpenProcess(0x0800, False, int(sys.argv[1]))\n"  # PROCESS_SUSPEND_RESUME
        "sys.stdin.readline()\n"
        "n.NtSuspendProcess(h); time.sleep(float(sys.argv[2])); n.NtResumeProcess(h)\n"
    )
    return subprocess.Popen(
        [sys.executable, "-I", "-c", script, str(os.getpid()), str(seconds)],
        stdin=subprocess.PIPE,
    )


@pytest.mark.asyncio
async def test_the_machine_stopping_the_whole_process_does_not_count():
    """AW-25: 167 ms with 1 of 18 samples and 0 ms of the process's CPU, in a check run, three days
    after F1119 raised the process's priority. A gap in the samples alone cannot tell a call keeping
    the GIL from the machine stopping the process; the observer outside it can."""
    import sys

    if sys.platform != "win32":
        pytest.skip("the observer is Windows'")
    suspender = _suspend_this_process_from_outside(GIT_DELAY)
    async with LagProbe() as probe:
        assert suspender.stdin is not None
        suspender.stdin.write(b"go\n")
        suspender.stdin.flush()
        await asyncio.to_thread(suspender.wait, 10)
        await asyncio.sleep(0.03)
    assert suspender.returncode == 0
    # The suspension left a gap that failed the tests before the observer judged it...
    gaps = [(started, ended) for started, ended, late, _ in probe._unsampled if late >= STALL_LIMIT]
    assert gaps, "the suspension left no gap in the samples, so this measured nothing"
    # ...seen from outside as the machine's, so it no longer does.
    assert all(probe._observer.stopped_share(*gap) >= 0.8 for gap in gaps), probe._observer.samples
    assert probe.worst < STALL_LIMIT, probe.why


@pytest.mark.asyncio
async def test_a_call_keeping_the_gil_is_not_read_as_the_machine():
    """The other half: the same gap, made by a thread here blocking with the GIL held, still counts,
    and the observer is why the failure says so."""
    import ctypes
    import sys

    if sys.platform != "win32":
        pytest.skip("PyDLL sleep is probed on Windows")
    sleep = ctypes.PyDLL("kernel32").Sleep
    async with LagProbe() as probe:
        sleep(int(GIT_DELAY * 1000))
    assert probe.worst >= STALL_LIMIT
    assert "read as the GIL held except" in probe.why and "observer samples" in probe.why, probe.why


def test_the_observer_describes_threads_that_begin_or_end_in_the_window():
    from ._loop_lag import _ThreadObserver

    observer = _ThreadObserver()
    observer.samples = [
        (1.0, 0, {1: (5, 6, 0), 2: (5, 6, 0)}),
        (1.1, 0, {1: (2, 6, 10_000), 2: (5, 6, 0), 3: (5, 6, 0)}),  # 3 began
        (1.2, 0, {1: (1, 32, 20_000), 3: (5, 6, 50_000)}),  # 2 ended
    ]
    described = observer.describe(1.05, 1.25)
    assert "t1 2 ms" in described and "t2 0 ms" in described and "t3 5 ms" in described
    assert observer.stopped_share(1.05, 1.25) is None  # two samples are too few to judge
