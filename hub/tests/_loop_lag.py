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
#: Where an idle loop's thread sits: the proactor's `_poll`, or a selector's `select`.
_LOOP_POLL_FRAMES = frozenset({"_poll", "select"})


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

    A control thread watches where the loop's thread is. A late wake while it sat in its poll is a
    loaded machine waking it late, and is not counted: nothing held it. Anything else, a git call
    or work on the loop, is somewhere other than the poll, and counts however busy the machine is.
    """

    def __init__(self) -> None:
        self.worst = 0.0
        self._on = True
        self._task: "asyncio.Task[None] | None" = None
        self._thread: "threading.Thread | None" = None
        self._loop_thread = threading.get_ident()
        self._loop_samples: List[tuple] = []

    def _loop_is_polling(self) -> bool:
        frame = sys._current_frames().get(self._loop_thread)
        return frame is not None and frame.f_code.co_name in _LOOP_POLL_FRAMES

    def _control(self) -> None:
        while self._on:
            time.sleep(SAMPLE)
            self._loop_samples.append((time.perf_counter(), self._loop_is_polling()))

    def _waiting_to_wake(self, started: float, ended: float) -> bool:
        """Was the loop in its poll throughout, so nothing held it and only waking it ran late?"""
        seen = [polling for at, polling in self._loop_samples if started <= at <= ended]
        return bool(seen) and sum(seen) >= 0.8 * len(seen)

    async def _sample(self) -> None:
        while self._on:
            started = time.perf_counter()
            await asyncio.sleep(SAMPLE)
            ended = time.perf_counter()
            late = ended - started - SAMPLE
            if late > SAMPLE and self._waiting_to_wake(started, ended):
                continue
            self.worst = max(self.worst, late)

    async def __aenter__(self) -> "LagProbe":
        self._thread = threading.Thread(target=self._control, daemon=True)
        self._thread.start()
        self._task = asyncio.create_task(self._sample())
        await asyncio.sleep(0.03)
        self.worst = 0.0
        self._loop_samples.clear()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await asyncio.sleep(0.03)
        self._on = False
        if self._task is not None:
            await self._task
        if self._thread is not None:
            self._thread.join()
