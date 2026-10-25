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
    longest a sample woke late, in seconds."""

    def __init__(self) -> None:
        self.worst = 0.0
        self._on = True
        self._task: "asyncio.Task[None] | None" = None

    async def _sample(self) -> None:
        while self._on:
            started = time.perf_counter()
            await asyncio.sleep(SAMPLE)
            self.worst = max(self.worst, time.perf_counter() - started - SAMPLE)

    async def __aenter__(self) -> "LagProbe":
        self._task = asyncio.create_task(self._sample())
        await asyncio.sleep(0.03)
        self.worst = 0.0
        return self

    async def __aexit__(self, *exc: object) -> None:
        await asyncio.sleep(0.03)
        self._on = False
        if self._task is not None:
            await self._task
