## Why

`F295` (severity A, `scripts/drive/FINDINGS.md:21313`) reports that a cancelled or superseded run's
background task can leave a permanently dead aiosqlite worker thread behind, and that any later
reuse of that connection hangs forever with no timeout. The second half is true and worse than the
finding says. **The first half names the wrong trigger, and R1 measured that rather than reasoning
about it.**

### What was measured

`testbed/scratch/f295/probe_cancel.py`, two shapes of the same story, run under `py -3.11` against
the installed `aiosqlite 0.22.1`:

| | coroutine cancelled | event loop closed under the in-flight call | worker thread after | connection reused |
|---|---|---|---|---|
| **A** | yes | **no** — loop stays alive | **alive** | **succeeds** |
| **B** | yes | **yes** | **dead** | **hangs** |

Shape A is the shape `F295` describes as the defect, and it is benign. `aiosqlite`'s worker thread
reports its result with `future.get_loop().call_soon_threadsafe(set_result, future, result)`
(`aiosqlite/core.py:66`), and `set_result` is `if not fut.done(): fut.set_result(...)` (`:32-34`) —
a cancelled future is already `done()`, so the report is a no-op and the thread goes back to
`tx.get()`. Cancellation on its own leaves nothing broken.

Shape B is the real precondition: the loop that created the future has to be **closed** by the time
the synchronous call returns. Then `call_soon_threadsafe` raises `RuntimeError: Event loop is
closed`, the `except BaseException` branch at `:73-75` makes the identical call to report *that*
failure and raises again, uncaught — and `_connection_worker_thread` terminates. The finding's
description of this half is exact, down to the doubled traceback.

So the accurate statement of the defect is: **a pooled database connection can outlive the event
loop that last queued work on it, and there is nothing anywhere that notices.** Cancellation is how
a run gets abandoned mid-write; it is not what kills the connection.

### The reuse half is worse than "hangs forever"

Measured at the SQLAlchemy layer, not just the driver (`testbed/scratch/f295/probe_guard*.py`,
`AsyncAdaptedQueuePool`, `sqlite+aiosqlite:///` file URL):

1. **Reusing a dead-thread connection hangs, and a timeout does not rescue you.** Wrapping the whole
   `async with engine.begin() as c: await c.execute(...)` in `asyncio.wait_for(..., timeout=6)` did
   not return at 6 seconds; the process ran to a 2-minute external kill. Cancelling the outer task
   unwinds into SQLAlchemy's connection teardown, which issues *another* aiosqlite call on the same
   dead thread — so the escape path needs the thing that is broken. **Bounding the wait is not a
   fix on its own**, which rules out the most obvious-looking repair.
2. **The obvious guard does not work either.** A `checkout` listener that raises
   `DisconnectionError` when `dbapi_connection._connection._thread.is_alive()` is false still hung:
   SQLAlchemy's invalidation path *closes* the connection it is discarding, and closing means
   queueing work for the dead thread.
3. **The guard works when it neutralises the connection before raising.** Setting the aiosqlite
   `Connection`'s `_running = False` and `_connection = None` makes `close()` a documented no-op
   (`aiosqlite/core.py:199-201`), so invalidation cannot touch the thread. Then:

   ```
   worker alive after kill: False
   RECOVERED, select 2 -> 2
   ```

   The pool discarded the dead record, opened a fresh connection, and the statement ran. This is the
   only arrangement of the three that recovered.

### Where the Hub actually stands today

Read out of the code, not assumed:

- The engine is **module-level and process-global** — `engine = create_async_engine(...)` at import
  time (`hub/hub/db/engine.py:33`), with `AsyncAdaptedQueuePool` and no pool events of any kind.
  Nothing in the Hub ever calls `engine.dispose()`.
- `lifespan`'s teardown is `await terminate_all_active_runs()` then `await shutdown_scheduler()`
  (`hub/hub/main.py:356-358`). It does **not** settle `_background_runs`, and
  `terminate_all_active_runs` deliberately kills process trees and touches no `Run` row and no
  database connection (`agent_trigger.py:1601-1624`).
- After `lifespan` returns, uvicorn's `Server.run` is `asyncio_run(self.serve(...))`
  (uvicorn 0.41.0, `uvicorn/server.py`), whose runner cancels every remaining task, gathers them,
  and closes the loop. **That is shape B, in production, on every shutdown that catches a run
  mid-write.**
- Nothing else in the Hub closes an event loop while the process keeps running. The one other
  `asyncio.run` is alembic's (`hub/hub/migrations/env.py:78`), and it builds its own engine and
  disposes it in a `finally` (`:73`) — that hole was already closed on 2026-09-06.
- Nothing in production calls `.cancel()` on an `_execute_run` task. `grep -rn "\.cancel()"
  hub/hub/ --include=*.py` returns exactly two live call sites, both Codex app-server reader tasks
  (`codex_appserver.py:868,870`), plus the comment at `agent_trigger.py:2386` that says so.

### What that means for severity, stated plainly

The mechanism is real and reproduced. **The production blast radius `F295` claims is not
established by anything R1 could measure.** The severe half — *reuse* of the dead connection —
needs the process to keep running past a loop close, and in the Hub the only loop close is process
exit. What production actually gets today is an uncaught worker-thread traceback on stderr at
shutdown, on a process that is leaving anyway.

Where the damage is demonstrated is the **test suite**, which does close a loop per test against
that same process-global engine — `hub/tests/conftest.py:293`'s
`_no_connection_outlives_its_event_loop` exists for precisely this hazard and says so in its
docstring, and `F292`'s history includes a CI run that sat for 3.5 hours before being cancelled by
hand. That fixture cancels background tasks and gathers them before disposing, which settles the
*coroutines*; as the finding says, nothing there can wait for the worker **thread**.

This change is worth making at either severity, because the fix for the small production case and
the fix for the large test case are the same two changes, and the second of them is product code.
**Whether `F295` stays an A is a judgement for R2/R3 and for the review page, not something R1
should quietly restate.**

## What changes

Two requirements, both in `app-lifecycle`, both ADDED.

- **Shutting the instance down releases its database before its event loop closes.** `lifespan`'s
  teardown settles the background run tasks it started and disposes the engine, in that order,
  while the loop is still running. This removes the only production occurrence of the precondition
  rather than coping with its consequences. It also makes the shutdown do what the codebase already
  believes it does: `terminate_all_active_runs`'s docstring calls this "a clean Hub shutdown".
- **A connection whose driver worker is gone is replaced, not reused.** A pool `checkout` guard on
  the Hub's engine that neutralises and discards such a connection, so that the pool opens a fresh
  one instead of handing out one that can only hang. This is defence that holds wherever the
  precondition arises — including the test suite, and including any future in-process loop nobody
  has thought of yet — and, per the measurements above, it is the *only* one of the three obvious
  repairs that actually recovers.

The guard's neutralise-then-raise ordering is not an implementation detail to be discovered later:
without it the guard hangs exactly as the unguarded path does. It is stated in `tasks.md` and
justified in `design.md`.

## What this deliberately does not change

- **`F292` is not resolved here.** It is a test-flake finding of the same class and it stays open.
  This change plausibly removes one of its mechanisms, and R1 makes no claim that it removes all of
  them. `DIRECTION.md` 2026-09-07 says not to conflate the two, and the deciding question — whether
  to spend a night slot on `F292` — is `DAY-2`, still unanswered.
- **No timeout is added to database work.** Measurement 1 above shows a timeout does not return
  from the hang it is meant to bound, so adding one would buy a false sense of a floor. If a
  bounded wait is wanted later it needs its own change and its own evidence.
- **The busy-timeout asymmetry is left alone.** Production runs on the sqlite3 default (5s);
  `hub/tests/conftest.py`'s pragma listener sets 30s, and alembic's engine was raised to 30s on
  2026-09-06. R1 noticed this while reading and it is not this change's business — recorded here so
  the next reader does not think it was missed.
- **No change to `aiosqlite`.** The double-raise at `core.py:73-75` is arguably an upstream bug, and
  this repository does not fix its dependencies; the guard is written so that an upstream fix would
  make it dead code rather than wrong code.
