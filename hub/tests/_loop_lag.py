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
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Iterator, List

#: Longer than the 100 ms the requirements allow, so one git call on the loop always fails them.
GIT_DELAY = 0.25
#: The sampling interval: the spec's probe samples every 10 ms.
SAMPLE = 0.010
STALL_LIMIT = 0.100


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
    """`async with LagProbe() as probe:` samples the loop every 10 ms; `probe.worst` is the
    longest a sample woke late, in seconds.

    A control thread samples the same way. A late wake-up the control thread shares (it was late
    over the same interval) is the whole process starved by a loaded machine, not the loop held by
    its own work, and is not counted: a git call on the loop sleeps without the GIL, so the thread
    keeps waking on time and the stall still counts.
    """

    def __init__(self) -> None:
        self.worst = 0.0
        self._on = True
        self._task: "asyncio.Task[None] | None" = None
        self._thread: "threading.Thread | None" = None
        self._thread_late: List[tuple] = []

    def _control(self) -> None:
        while self._on:
            started = time.perf_counter()
            time.sleep(SAMPLE)
            ended = time.perf_counter()
            if ended - started - SAMPLE > SAMPLE:
                self._thread_late.append((started, ended))

    def _starved(self, started: float, ended: float) -> bool:
        covered = 0.0
        for begin, end in self._thread_late:
            covered += max(0.0, min(end, ended) - max(begin, started))
        return covered >= 0.8 * (ended - started)

    async def _sample(self) -> None:
        while self._on:
            started = time.perf_counter()
            await asyncio.sleep(SAMPLE)
            ended = time.perf_counter()
            late = ended - started - SAMPLE
            if late > SAMPLE and self._starved(started, ended):
                continue
            self.worst = max(self.worst, late)

    async def __aenter__(self) -> "LagProbe":
        self._thread = threading.Thread(target=self._control, daemon=True)
        self._thread.start()
        self._task = asyncio.create_task(self._sample())
        await asyncio.sleep(0.03)
        self.worst = 0.0
        self._thread_late.clear()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await asyncio.sleep(0.03)
        self._on = False
        if self._task is not None:
            await self._task
        if self._thread is not None:
            self._thread.join()
