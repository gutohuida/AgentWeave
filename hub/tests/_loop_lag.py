"""A loop-lag probe and a slow git, for the tests that a Hub path never freezes its event loop
(`turn-starts-approvals-and-evidence-never-freeze-the-hub`).

`slow_git` makes every git process take at least `GIT_DELAY` seconds longer, wherever it runs, and
records which thread ran it. A git call made on the loop then shows as a stall of at least that
long; one made in a thread shows as none. That turns "it runs off the loop" into a measurement
that does not depend on how fast git happens to be on the machine running the suite.
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import gc
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Iterator, List

#: Longer than the 100 ms the requirements allow, so one git call on the loop always fails them.
GIT_DELAY = 0.25
#: The sampling interval: the spec's probe samples every 10 ms.
SAMPLE = 0.010
STALL_LIMIT = 0.100
#: The share of the expected samples a window needs to be read as sampled; Windows timers are coarse.
_MIN_COVERAGE = 0.25
#: Where an idle loop's thread sits: the proactor's `_poll`, or a selector's `select`.
_LOOP_POLL_FRAMES = frozenset({"_poll", "select"})


def _raise_priority(level: int = 2) -> int:
    """Have the calling thread scheduled promptly on a busy machine, so its samples are not the
    first thing a loaded machine loses. It sleeps nearly all the time; this costs nobody anything.
    """
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentThread.restype = ctypes.c_void_p
        kernel32.GetThreadPriority.argtypes = [ctypes.c_void_p]
        thread = ctypes.c_void_p(kernel32.GetCurrentThread())
        was = kernel32.GetThreadPriority(thread)
        kernel32.SetThreadPriority(thread, level)  # 2 is HIGHEST
        return was
    return 0


def _thread_waiting_reader(native_id: int):  # noqa: ANN202
    """A callable saying whether thread `native_id` is waiting on the OS (asleep, on a lock, in a
    blocking call) rather than runnable, or None where the platform does not tell."""
    try:
        if sys.platform == "win32":
            import struct

            ntdll = ctypes.WinDLL("ntdll")
            pid = os.getpid()

            def waiting() -> "bool | None":
                size = 1 << 20
                while True:
                    buf = ctypes.create_string_buffer(size)
                    got = ctypes.c_ulong()
                    if ntdll.NtQuerySystemInformation(5, buf, size, ctypes.byref(got)) == 0:
                        break
                    if got.value <= size:
                        return None
                    size = got.value + (1 << 16)
                at = 0
                while True:
                    following, count = struct.unpack_from("<II", buf, at)
                    if struct.unpack_from("<Q", buf, at + 0x50)[0] == pid:
                        for i in range(count):
                            thread = at + 0x100 + 80 * i
                            if struct.unpack_from("<Q", buf, thread + 48)[0] == native_id:
                                return struct.unpack_from("<I", buf, thread + 68)[0] == 5
                        return None
                    if not following:
                        return None
                    at += following

            return waiting
        if os.path.isdir(f"/proc/self/task/{native_id}"):

            def waiting() -> "bool | None":
                try:
                    with open(f"/proc/self/task/{native_id}/stat", encoding="ascii") as handle:
                        return handle.read().rpartition(")")[2].split()[0] in ("S", "D")
                except (OSError, IndexError):
                    return None

            return waiting
    except (AttributeError, OSError):
        pass
    return None


@dataclass
class GitCall:
    argv: List[str]
    started: float
    on_loop: bool


@dataclass
class GitLog:
    calls: List[GitCall] = field(default_factory=list)

    @property
    def on_loop(self) -> List[GitCall]:
        return [call for call in self.calls if call.on_loop]


@contextlib.contextmanager
def slow_git(loop_thread: threading.Thread) -> Iterator[GitLog]:
    log = GitLog()
    real = subprocess.run

    def _run(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        argv = args[0] if args else kwargs.get("args")
        if isinstance(argv, (list, tuple)) and argv and "git" in os.path.basename(str(argv[0])):
            on_loop = threading.current_thread() is loop_thread
            log.calls.append(GitCall([str(a) for a in argv], time.perf_counter(), on_loop))
            time.sleep(GIT_DELAY)
        return real(*args, **kwargs)

    subprocess.run = _run
    try:
        yield log
    finally:
        subprocess.run = real


class LagProbe:
    """`async with LagProbe() as probe:` samples the loop every 10 ms; `probe.worst` is the longest
    the loop was held, in seconds.

    Every hold counts, whatever held the loop: a git call, a sleep, a lock, a call that keeps the
    GIL (on any thread: the samples go missing, and a window without them counts in full), work.
    A late wake while the loop sat in its poll is not one: it ran late. Time the loop's
    thread spent waiting on the OS counts as the wall clock says; time it spent runnable counts as
    the CPU it used, so a machine that left it without a core for 300 ms adds nothing. On a platform
    that cannot tell waiting from runnable, the wall clock counts throughout.
    """

    def __init__(self) -> None:
        self.worst = 0.0
        #: Why `worst` was counted, for the failure to say (F1111).
        self.why = "nothing was counted"
        self._on = True
        self._task: "asyncio.Task[None] | None" = None
        self._thread: "threading.Thread | None" = None
        self._loop_thread = threading.get_ident()
        self._waiting = _thread_waiting_reader(threading.get_native_id())
        #: (time, in the poll, waiting on the OS or None if unknown)
        self._loop_samples: List[tuple] = []
        #: (start, end) of each garbage collection, which holds the GIL on whichever thread runs it.
        self._collections: List[tuple] = []
        self._collecting = 0.0

    def _on_collection(self, phase: str, info: dict) -> None:
        if phase == "start":
            self._collecting = time.perf_counter()
        else:
            self._collections.append((self._collecting, time.perf_counter()))

    def _loop_is_polling(self) -> bool:
        frame = sys._current_frames().get(self._loop_thread)
        return frame is not None and frame.f_code.co_name in _LOOP_POLL_FRAMES

    def _starting_a_thread(self) -> bool:
        """Is the loop's thread waiting for a thread it just created to begin? That is the
        scheduler's latency, not something the loop was held by."""
        frame = sys._current_frames().get(self._loop_thread)
        while frame is not None:
            code = frame.f_code
            if code.co_name == "start" and code.co_filename.replace("\\", "/").endswith(
                "/threading.py"
            ):
                return True
            frame = frame.f_back
        return False

    def _control(self) -> None:
        _raise_priority()
        while self._on:
            time.sleep(SAMPLE)
            polling = self._loop_is_polling()
            waiting = None if polling or self._waiting is None else self._waiting()
            if waiting and self._starting_a_thread():
                waiting = False
            self._loop_samples.append((time.perf_counter(), polling, waiting))

    def _covered(self, started: float, ended: float) -> bool:
        """Did the control thread sample through most of the window? It cannot while something holds
        the GIL, so a window it has gaps in was held by a call keeping the GIL, whichever thread."""
        got = sum(1 for at, _, _ in self._loop_samples if started <= at <= ended)
        return got >= _MIN_COVERAGE * (ended - started) / SAMPLE

    def _waiting_to_wake(self, started: float, ended: float) -> bool:
        """Was the loop in its poll throughout, so nothing held it and only waking it ran late?"""
        if not self._covered(started, ended):
            return False
        seen = [polling for at, polling, _ in self._loop_samples if started <= at <= ended]
        return bool(seen) and sum(seen) >= 0.8 * len(seen)

    def _waited(self, started: float, ended: float) -> bool:
        """Was the loop's thread seen waiting on the OS, outside its poll, through most of the window?"""
        if self._waiting is None or not self._covered(started, ended):
            return True  # the platform cannot tell, or the GIL was held: count the whole wake
        seen = [w for at, _, w in self._loop_samples if started <= at <= ended]
        return bool(seen) and sum(w is not False for w in seen) >= 0.5 * len(seen)

    async def _sample(self) -> None:
        while self._on:
            started, cpu_started = time.perf_counter(), time.thread_time()
            process_started = time.process_time()
            await asyncio.sleep(SAMPLE)
            ended, cpu = time.perf_counter(), time.thread_time() - cpu_started
            self._process_cpu = time.process_time() - process_started
            late = raw = ended - started - SAMPLE
            branch = "on time"
            if late > SAMPLE:
                if self._waiting_to_wake(started, ended):
                    continue
                if not self._covered(started, ended):
                    branch = "samples missing, so read as the GIL held: the wall clock counts"
                elif self._waiting is None:
                    branch = "the platform cannot tell waiting: the wall clock counts"
                elif self._waited(started, ended):
                    branch = "the loop's thread waited on the OS outside its poll"
                else:
                    # Work, or no core to run it on: only the CPU the thread used is the loop's own.
                    late = min(late, cpu)
                    branch = "the loop's thread was runnable: its CPU counts"
            if late > self.worst:
                self.worst = late
                self.why = self._explain(started, ended, raw, cpu, branch)

    def _explain(self, started: float, ended: float, raw: float, cpu: float, branch: str) -> str:
        seen = [s for s in self._loop_samples if started <= s[0] <= ended]
        expected = (ended - started) / SAMPLE
        frame = sys._current_frames().get(self._loop_thread)
        collected = sum(
            min(end, ended) - max(start, started)
            for start, end in self._collections
            if start < ended and end > started
        )
        return (
            f"{branch}; {raw * 1000:.0f} ms late, {cpu * 1000:.0f} ms of the thread's CPU, "
            f"{self._process_cpu * 1000:.0f} ms of the process's, "
            f"{collected * 1000:.0f} ms collecting garbage, "
            f"{len(seen)} of {expected:.0f} samples, "
            f"{sum(1 for s in seen if s[1])} in the poll, "
            f"{sum(1 for s in seen if s[2])} waiting on the OS, "
            f"{sum(1 for s in seen if s[2] is False)} runnable; "
            f"sampling from {frame.f_code.co_name if frame else 'nowhere'}"
        )

    async def __aenter__(self) -> "LagProbe":
        # The loop's thread runs at the control thread's priority: a loop thread that a busy machine
        # preempted while it held the GIL would leave the same gap in the samples a real hold does.
        self._priority = _raise_priority()
        gc.callbacks.append(self._on_collection)
        # The heap the suite built before this window is not the measured path's: a full collection
        # walking it held the loop 104 of 123 ms on a busy machine (F1111). What the path allocates
        # in the window is still collected and still counts.
        gc.collect()
        gc.freeze()
        self._thread = threading.Thread(target=self._control, daemon=True)
        self._thread.start()
        self._task = asyncio.create_task(self._sample())
        await asyncio.sleep(0.03)
        self.worst = 0.0
        self.why = "nothing was counted"
        self._loop_samples.clear()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await asyncio.sleep(0.03)
        self._on = False
        if self._task is not None:
            await self._task
        if self._thread is not None:
            self._thread.join()
        gc.unfreeze()
        gc.callbacks.remove(self._on_collection)
        _raise_priority(self._priority)
