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
import tempfile
import threading
import time
from collections import Counter
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


def _set_process_priority(priority_class: "int | None" = None) -> "int | None":
    """Give the whole process a priority class, and answer the one it had. Whichever thread holds
    the GIL holds the loop too, so a worker thread that a busy machine preempts while it holds it
    stops every thread here: 110 to 196 ms with no sample and no CPU spent (F1119). Raising only the
    threads the probe owns left that one to the other processes. The default is HIGH; git processes
    started meanwhile do not inherit it. None where the platform has no such thing."""
    if sys.platform != "win32":
        return None
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.GetPriorityClass.argtypes = [ctypes.c_void_p]
    kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    process = kernel32.GetCurrentProcess()
    was = kernel32.GetPriorityClass(process)
    kernel32.SetPriorityClass(process, 0x80 if priority_class is None else priority_class)
    return was


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


def _find_gil() -> "tuple[int, int] | None":
    """Where this interpreter keeps who holds its GIL, for the observer to read from outside: the
    address of the GIL's `last_holder` (`locked` follows it) and the offset of the thread id in a
    thread state. Found by looking rather than assumed: CPython keeps `interval`, `last_holder` and
    `locked` in that order in `_PyRuntime.ceval.gil`, so a switch interval nothing else holds marks
    the place, and this thread, holding the GIL, must be what it names. None on any other layout;
    the observer then judges without it. Call with the GIL held, as any Python code is."""
    if sys.platform != "win32" or sys.implementation.name != "cpython":
        return None
    import struct

    try:
        api = ctypes.pythonapi
        runtime = ctypes.addressof(ctypes.c_char.in_dll(api, "_PyRuntime"))
        api.PyThreadState_Get.restype = ctypes.c_void_p
        me = api.PyThreadState_Get()
    except (AttributeError, ValueError, OSError):
        return None
    was = sys.getswitchinterval()
    sys.setswitchinterval(0.004321)
    try:
        marker = round(sys.getswitchinterval() * 1e6)
        found = []
        head = ctypes.string_at(runtime, 1024)
        for at in range(0, len(head) - 24, 4):
            if struct.unpack_from("<I", head, at)[0] != marker:
                continue
            holder_at = (at + 4 + 7) & ~7
            holder, locked = struct.unpack_from("<Qi", head, holder_at)
            if holder == me and locked == 1:
                found.append(runtime + holder_at)
    finally:
        sys.setswitchinterval(was)
    state = ctypes.string_at(me, 256)
    native = threading.get_native_id()
    offsets = [at for at in range(0, 256, 4) if struct.unpack_from("<I", state, at)[0] == native]
    if len(found) != 1 or not offsets:
        return None
    return found[0], offsets[0]


_OBSERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_thread_observer.py")
#: Thread states meaning "could run, but the machine has not given it a core": Ready, Standby,
#: Transition (its kernel stack is paged out), DeferredReady. Running is 2, Waiting 5.
_NOT_SCHEDULED = frozenset({1, 3, 6, 7})
#: Wait reasons meaning the machine, not the code, is what the thread waits for: free memory, a page
#: brought back in, being suspended, being swapped back in, a CPU rate cap (KWAIT_REASON).
_MACHINE_WAITS = frozenset({1, 2, 5, 8, 9, 12, 18, 19, 23, 24})
#: Fewer observer samples than this in a gap and it is not judged: the wall clock counts.
_MIN_OBSERVED = 3


class _ThreadObserver:
    """What every thread of this process was doing, sampled from another process
    (`_thread_observer.py`). Inside the process a sample needs the GIL, so when the probe's own
    samples go missing they cannot say whether a thread here kept the GIL or the machine stopped
    the whole process (F1119, AW-25). This one can, and it reads who holds the GIL (AW-27).
    Windows only; elsewhere it has no samples and judges nothing."""

    def __init__(self) -> None:
        self._process: "subprocess.Popen[bytes] | None" = None
        self._out = ""
        #: (time, hard faults, GIL, {thread id: (state, wait reason, cpu in 100 ns)}), the GIL as
        #: the id of the thread holding it, 0 when nobody did, -1 when it was not read.
        self.samples: List[tuple] = []

    async def start(self) -> None:
        if sys.platform != "win32":
            return
        handle, self._out = tempfile.mkstemp(prefix="aw-thread-observer-", suffix=".txt")
        os.close(handle)
        gil = _find_gil()
        self._process = subprocess.Popen(
            [sys.executable, "-I", _OBSERVER, str(os.getpid()), self._out]
            + ([str(part) for part in gil] if gil else []),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        assert self._process.stdout is not None
        # It says so once it has sampled, so the window it is there for is observed from its start.
        await asyncio.to_thread(self._process.stdout.readline)

    def stop(self) -> None:
        if self._process is None:
            return
        assert self._process.stdin is not None
        self._process.stdin.close()
        try:
            self._process.wait(60)
        except subprocess.TimeoutExpired:
            self._process.kill()  # judged without it: the wall clock counts
            self._process.wait()
        try:
            with open(self._out, encoding="ascii") as handle:
                lines = handle.read().splitlines()
            os.remove(self._out)
        except OSError:
            return
        for line in lines:
            at, faults, gil, threads = line.split(" ", 3)
            seen = {}
            for thread in threads.split(","):
                tid, state, reason, cpu = thread.split(":")
                seen[int(tid)] = (int(state), int(reason), int(cpu))
            self.samples.append((float(at), int(faults), int(gil), seen))

    @staticmethod
    def _machines(state: int, reason: int) -> bool:
        """Is a thread in this state held up by the machine rather than by the code?"""
        return state in _NOT_SCHEDULED or (state == 5 and reason in _MACHINE_WAITS)

    @classmethod
    def _stopped(cls, gil: int, threads: dict) -> bool:
        """Was nothing in this process holding it up? Only a thread holding the GIL can keep the
        others from running Python, so with the GIL read: nobody held it, or its holder was held
        up by the machine (no core, memory, a page-in, a suspension). A holder that ran, or waited
        on anything else -- a call that keeps the GIL -- is the code's. With the GIL unread: no
        thread ran, and one was held up by the machine."""
        if gil == 0:
            return True  # every thread here could have taken it: none was let run (AW-27)
        if gil > 0 and gil in threads:
            return cls._machines(*threads[gil][:2])
        if any(state == 2 for state, _, _ in threads.values()):
            return False
        return any(cls._machines(state, reason) for state, reason, _ in threads.values())

    def stopped_share(self, started: float, ended: float) -> "float | None":
        """The share of a window nothing in the process held it up, or None if it was not
        observed through enough of it to say."""
        seen = [(gil, threads) for at, _, gil, threads in self.samples if started <= at <= ended]
        if len(seen) < _MIN_OBSERVED:
            return None
        return sum(self._stopped(*sample) for sample in seen) / len(seen)

    def describe(self, started: float, ended: float, names: "dict | None" = None) -> str:
        """*names*: thread names by native id, so a holder can be told apart (AW-18)."""
        names = names or {}
        seen = [s for s in self.samples if started <= s[0] <= ended]
        if not seen:
            return "no observer samples"
        history = [s for s in self.samples if s[0] < started][-1:] + seen
        holders = Counter(
            {0: "free", -1: "unread"}.get(s[2], f"held by t{s[2]}{_named(names, s[2])}")
            for s in seen
        )
        parts = [
            f"{len(seen)} observer samples, {sum(self._stopped(*s[2:]) for s in seen)} stopped, "
            f"{seen[-1][1] - history[0][1]} hard faults, GIL "
            + " ".join(f"{k}x{v}" for k, v in holders.most_common(3))
        ]
        for tid in sorted({tid for s in seen for tid in s[3]}):
            mine = [s[3][tid] for s in history if tid in s[3]]
            states = Counter(f"{state}/{reason}" for state, reason, _ in mine)
            cpu = (mine[-1][2] - mine[0][2]) / 10_000  # a thread can begin or end in the window
            common = " ".join(f"{k}x{v}" for k, v in states.most_common(3))
            parts.append(f"t{tid}{_named(names, tid)} {cpu:.0f} ms {common}")
        return "state/reason: " + "; ".join(parts)


def _named(names: dict, tid: int) -> str:
    return f" ({names[tid]})" if tid in names else ""


@dataclass
class GitCall:
    argv: List[str]
    started: float
    on_loop: bool
    #: The name of the thread that ran it: which pool it waited in does not depend on the machine.
    thread: str = ""


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
            log.calls.append(
                GitCall(
                    [str(a) for a in argv],
                    time.perf_counter(),
                    on_loop,
                    threading.current_thread().name,
                )
            )
            time.sleep(GIT_DELAY)
        return real(*args, **kwargs)

    subprocess.run = _run
    try:
        yield log
    finally:
        subprocess.run = real


#: What the interpreter reports of a file or directory being touched (`sys.addaudithook`). A stat
#: reports nothing, so this is a floor; the lag probe still measures the rest.
_DISK_EVENTS = frozenset(
    {
        "open",
        "os.chmod",
        "os.link",
        "os.listdir",
        "os.mkdir",
        "os.remove",
        "os.rename",
        "os.rmdir",
        "os.scandir",
        "os.symlink",
        "os.truncate",
        "os.utime",
        "shutil.copyfile",
        "shutil.rmtree",
    }
)
_disk_watch: "tuple[int, List[str]] | None" = None
_disk_hook_added = False


def _on_audit(event: str, args: tuple) -> None:
    watch = _disk_watch
    if watch is not None and event in _DISK_EVENTS and threading.get_ident() == watch[0]:
        watch[1].append(f"{event} {args[0] if args else ''}")


@contextlib.contextmanager
def disk_on_loop() -> Iterator[List[str]]:
    """The file calls the calling thread makes, as they happen: how long one takes depends on the
    machine, whether it was made on the loop does not. An audit hook cannot be removed, so one stays
    installed and does nothing outside this block."""
    global _disk_watch, _disk_hook_added
    if not _disk_hook_added:
        sys.addaudithook(_on_audit)
        _disk_hook_added = True
    calls: List[str] = []
    _disk_watch = (threading.get_ident(), calls)
    try:
        yield calls
    finally:
        _disk_watch = None


class LagProbe:
    """`async with LagProbe() as probe:` samples the loop every 10 ms; `probe.worst` is the longest
    the loop was held, in seconds.

    Every hold counts, whatever held the loop: a git call, a sleep, a lock, a call that keeps the
    GIL (on any thread: the samples go missing, and a window without them counts in full, less
    the share an observer outside the process saw the machine keep it stopped), work.
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
        #: (time, where the loop's thread was) outside its poll, for the failure to say.
        self._loop_places: List[tuple] = []
        #: (start, end) of each garbage collection, which holds the GIL on whichever thread runs it.
        self._collections: List[tuple] = []
        self._collecting = 0.0
        self._observer = _ThreadObserver()
        #: The window `worst` was counted in, for the observer to explain once it has stopped.
        self._worst_window = (0.0, 0.0)
        #: (start, end, lateness, explanation) of each window the samples went missing in, judged
        #: once the observer has stopped.
        self._unsampled: List[tuple] = []
        #: Every thread's name by native id, as the control thread last saw it running.
        self._names: dict = {}
        #: (gap start, gap end, {thread name: place}) at the first sample after each gap.
        self._after_gaps: List[tuple] = []

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

    def _loop_place(self) -> str:
        """The innermost frames of the loop's thread, innermost last."""
        frame = sys._current_frames().get(self._loop_thread)
        places = []
        while frame is not None and len(places) < 6:
            code = frame.f_code
            places.append(f"{os.path.basename(code.co_filename)}:{frame.f_lineno} {code.co_name}")
            frame = frame.f_back
        return " < ".join(places)

    def _control(self) -> None:
        _raise_priority()
        last = time.perf_counter()
        while self._on:
            time.sleep(SAMPLE)
            for thread in threading.enumerate():
                self._names.setdefault(thread.native_id, thread.name)
            if time.perf_counter() - last > 5 * SAMPLE:
                # The first sample after a gap: whichever thread kept the GIL through it has only
                # just let it go, so where it is now is where it was.
                self._after_gaps.append((last, time.perf_counter(), self._every_place()))
            last = time.perf_counter()
            polling = self._loop_is_polling()
            waiting = None if polling or self._waiting is None else self._waiting()
            if waiting and self._starting_a_thread():
                waiting = False
            now = time.perf_counter()
            self._loop_samples.append((now, polling, waiting))
            if not polling:
                self._loop_places.append((now, self._loop_place()))

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
                    why = self._explain(started, ended, raw, cpu, "samples missing")
                    self._unsampled.append((started, ended, late, why))
                    continue
                if self._waiting is None:
                    branch = "the platform cannot tell waiting: the wall clock counts"
                elif self._waited(started, ended):
                    branch = "the loop's thread waited on the OS outside its poll"
                else:
                    # Work, or no core to run it on: only the CPU the thread used is the loop's own.
                    late = min(late, cpu)
                    branch = "the loop's thread was runnable: its CPU counts"
            if late > self.worst:
                self._count(late, self._explain(started, ended, raw, cpu, branch), started, ended)

    def _count(self, late: float, why: str, started: float, ended: float) -> None:
        if late > self.worst:
            self.worst, self.why, self._worst_window = late, why, (started, ended)

    def _judge_unsampled(self) -> None:
        """A window without samples was held by a call keeping the GIL, on whichever thread, or
        the machine did not let the process run: no core for it, memory, a page-in, a suspension,
        or every thread left waiting with the GIL free (AW-27: 371 ms, no thread ran or could).
        Only the observer, sampling from outside, saw which. The time nothing here held the process
        up is not the code's; the rest counts in full, and all of it counts unobserved."""
        for started, ended, late, why in self._unsampled:
            stopped = self._observer.stopped_share(started, ended)
            if stopped is None:
                verdict = "read as the GIL held, unobserved: the wall clock counts"
            else:
                late *= 1 - stopped
                verdict = (
                    f"read as the GIL held except the {stopped:.0%} of it nothing here held the "
                    "process up: the rest counts"
                )
            self._count(
                late,
                why.replace("samples missing", f"samples missing, {verdict}", 1),
                started,
                ended,
            )

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
            f"sampling from {frame.f_code.co_name if frame else 'nowhere'}; "
            f"seen at {self._places_in(started, ended)}"
        )

    def _every_place(self) -> dict:
        names = {thread.ident: thread.name for thread in threading.enumerate()}
        places = {}
        for ident, frame in sys._current_frames().items():
            if ident == threading.get_ident():
                continue
            parts = []
            while frame is not None and len(parts) < 7:
                code = frame.f_code
                parts.append(
                    f"{os.path.basename(code.co_filename)}:{frame.f_lineno} {code.co_name}"
                )
                frame = frame.f_back
            places[names.get(ident, str(ident))] = " < ".join(parts)
        return places

    def _after_gap_in(self, started: float, ended: float) -> str:
        """Where every thread was at the first sample after the longest gap in the window."""
        gaps = [g for g in self._after_gaps if g[1] >= started and g[0] <= ended]
        if not gaps:
            return "no gap"
        gap = max(gaps, key=lambda g: g[1] - g[0])
        return " || ".join(f"{name}: {place}" for name, place in sorted(gap[2].items()))

    def _places_in(self, started: float, ended: float) -> str:
        seen = Counter(place for at, place in self._loop_places if started <= at <= ended)
        return " | ".join(f"{count}x {place}" for place, count in seen.most_common(3)) or "nothing"

    async def __aenter__(self) -> "LagProbe":
        # The loop's thread runs at the control thread's priority: a loop thread that a busy machine
        # preempted while it held the GIL would leave the same gap in the samples a real hold does.
        self._priority = _raise_priority()
        self._process_priority = _set_process_priority()
        gc.callbacks.append(self._on_collection)
        # The heap the suite built before this window is not the measured path's: a full collection
        # walking it held the loop 104 of 123 ms on a busy machine (F1111). What the path allocates
        # in the window is still collected and still counts.
        gc.collect()
        gc.freeze()
        await self._observer.start()
        self._thread = threading.Thread(target=self._control, daemon=True)
        self._thread.start()
        self._task = asyncio.create_task(self._sample())
        await asyncio.sleep(0.03)
        self.worst = 0.0
        self.why = "nothing was counted"
        self._loop_samples.clear()
        self._loop_places.clear()
        self._unsampled.clear()
        self._after_gaps.clear()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await asyncio.sleep(0.03)
        self._on = False
        if self._task is not None:
            await self._task
        if self._thread is not None:
            self._thread.join()
        self._observer.stop()
        self._judge_unsampled()
        if self.worst:
            self._names[threading.get_native_id()] = "the loop"
            self.why += f"; after the gap: {self._after_gap_in(*self._worst_window)}"
            self.why += (
                f"; threads: {self._observer.describe(*self._worst_window, names=self._names)}"
            )
        gc.unfreeze()
        gc.callbacks.remove(self._on_collection)
        _raise_priority(self._priority)
        if self._process_priority is not None:
            _set_process_priority(self._process_priority)
