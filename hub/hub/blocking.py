"""Where the Hub's blocking work runs: git, filesystem scans and process spawns, off the loop.

The Hub serves every request, stream and background job on one event loop, so a `git worktree
add` run inline (about 4 s on a large checkout, 20 s at worst) freezes every screen and every
agent's tool call for its whole duration (`turn-starts-approvals-and-evidence-never-freeze-the-
hub`, D1). `run` moves such a call to a thread and returns its result to the loop, which applies
it to the database.

**Its own threads, not the default executor's** (D2). Each live Claude run holds a thread of the
loop's default executor in a blocking `pty.read` for its whole turn (`agent_trigger._execute_run`),
and `asyncio.to_thread` uses that same pool: `min(32, cpu + 4)` threads, eight on a 4-CPU VDI. Git
sent there would queue behind the streaming runs; here it never waits for one.

**`run_serialized` keeps the one ordering the loop used to give for free** (D5). While worktree
creation, checkout release and the merge into the main branch ran on the loop, no two of them
could overlap: each one ran to completion before the loop could start another. Moving them to
threads would let a turn start add a worktree while an approval removes another or merges into the
main checkout, which nothing ever had to tolerate. So every call that mutates git state is taken
through one lock per loop, held across the thread hop and nothing else; reads stay concurrent, as
they already were where they ran in threads.

The current trace span travels with the call (`contextvars.copy_context`, as `asyncio.to_thread`
does), so a command run here is still recorded under the request or run that caused it.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import functools
import os
import weakref
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")

#: Enough for every streaming run's turn start to run its git at once on a large machine, and
#: still small: each thread mostly waits on a child process. Not derived from the CPU count,
#: because what bounds it is concurrent git processes, not cores.
MAX_WORKERS = int(os.environ.get("AW_BLOCKING_THREADS") or 16)

_executor: Optional[ThreadPoolExecutor] = None
_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


def executor() -> ThreadPoolExecutor:
    """The pool blocking work runs on, made on first use."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="aw-blocking")
    return _executor


async def run(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """`fn(*args, **kwargs)` on the blocking pool, with the caller's context (its trace span)."""
    loop = asyncio.get_running_loop()
    context = contextvars.copy_context()
    call = functools.partial(context.run, fn, *args, **kwargs)
    return await loop.run_in_executor(executor(), call)


#: One thread per live run's blocking read, so this bounds concurrent streaming runs rather than
#: work: generous, since each thread only waits on its child's output.
MAX_STREAM_READERS = int(os.environ.get("AW_STREAM_READER_THREADS") or 256)

_stream_executor: Optional[ThreadPoolExecutor] = None


def stream_executor() -> ThreadPoolExecutor:
    """Where a live run's blocking reads of its process (`pty.read`, `pty.wait`) wait.

    The other half of D2. A Claude run blocks in `read` for its whole turn, and on the default
    executor that was one of `min(32, cpu + 4)` threads gone per live run -- the pool every
    `asyncio.to_thread` in the Hub (about a hundred call sites) shares. Eight runs on a 4-CPU VDI
    exhausted it, and every request that offloads anything waited for a run to end."""
    global _stream_executor
    if _stream_executor is None:
        _stream_executor = ThreadPoolExecutor(
            max_workers=MAX_STREAM_READERS, thread_name_prefix="aw-stream"
        )
    return _stream_executor


async def read_stream(fn: Callable[[], T]) -> T:
    """`fn()` -- a blocking read or wait on a run's process -- on `stream_executor`."""
    return await asyncio.get_running_loop().run_in_executor(stream_executor(), fn)


def mutation_lock() -> asyncio.Lock:
    """The running loop's lock for git work that changes a checkout or a branch (see module
    docstring). Per loop, so a lock bound to a finished loop is never handed to the next one."""
    loop = asyncio.get_running_loop()
    lock = _locks.get(loop)
    if lock is None:
        lock = _locks[loop] = asyncio.Lock()
    return lock


async def run_serialized(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """`run`, one at a time with every other call made through here: worktree creation, release,
    and merges, which ran strictly one after another while they ran on the loop.

    The lock is released when the *thread* finishes, not when the awaiting coroutine does: a
    caller cancelled mid-merge must not let the next merge start while git is still writing."""
    loop = asyncio.get_running_loop()
    lock = mutation_lock()
    await lock.acquire()
    try:
        context = contextvars.copy_context()
        future = executor().submit(context.run, fn, *args, **kwargs)
    except BaseException:
        lock.release()
        raise

    def _release(_done: Any) -> None:
        with contextlib.suppress(RuntimeError):  # the loop is gone, and its lock with it
            loop.call_soon_threadsafe(lock.release)

    future.add_done_callback(_release)
    return await asyncio.wrap_future(future)
