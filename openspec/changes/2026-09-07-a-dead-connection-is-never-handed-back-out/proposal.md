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
   not return; the process ran to a 2-minute external kill.

   **R2 separated the timer from the unwind, because R1 had measured only the symptom**
   (`testbed/scratch/f295/probe_timeout_reason.py`). The timer is not the broken part: with the
   inner task `shield`ed, `TimeoutError` fired at **4.0s, on schedule**, with the statement still
   pending. What does not return is `wait_for`'s own await of the cancellation it then issues — an
   explicit `task.cancel()` had **still not completed 6 seconds later**, and `task.get_stack()`
   came back **empty**, which is where a task parked inside SQLAlchemy's greenlet sits. So the
   stated reason is confirmed rather than inferred: unwinding needs SQLAlchemy to close the
   connection, and closing needs the thread that died.

   This is sharper than "use a longer timeout would not help". It also rules out `asyncio.timeout()`
   and any shorter bound, because none of them changes what the cancellation has to wait for. The
   one construction that *does* return is `shield` + abandon — and that permanently strands a
   checked-out pool record, so a pool with `pool_size` + `max_overflow` slots survives only that
   many occurrences before every later checkout blocks. **Bounding the wait is not a fix on its
   own**, which rules out the most obvious-looking repair.
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
  time (`hub/hub/db/engine.py:34`), with `AsyncAdaptedQueuePool` and no pool events of any kind.
  Nothing in the Hub ever calls `engine.dispose()`.
- `lifespan`'s teardown is `await terminate_all_active_runs()` then `await shutdown_scheduler()`
  (`hub/hub/main.py:357-358`; `:356` is the `yield`). It does **not** settle `_background_runs`, and
  `terminate_all_active_runs` deliberately kills process trees and touches no `Run` row and no
  database connection (`agent_trigger.py:1601-1624`).
- After `lifespan` returns, uvicorn's `Server.run` is `asyncio_run(self.serve(...))`
  (uvicorn 0.41.0, `uvicorn/server.py`), whose runner cancels every remaining task, gathers them,
  and closes the loop. **That is shape B, in production, on every shutdown that catches a run
  mid-write.**
- Nothing else in the Hub closes an event loop while the process keeps running. The one other
  `asyncio.run` is alembic's (`hub/hub/migrations/env.py:78`), and it builds its own engine and
  disposes it in a `finally` (`:74`) — that hole was already closed on 2026-09-06. `init_db()`, the
  only caller of the function that runs it, is itself called exactly once, from `main.py:348`.
- Nothing in production calls `.cancel()` on an `_execute_run` task. `grep -rn "\.cancel()"
  hub/hub/ --include=*.py` returns exactly two live call sites, both Codex app-server reader tasks
  (`codex_appserver.py:868,870`), plus the comment at `agent_trigger.py:2386` that says so.

### What that means for severity, stated plainly

The mechanism is real and reproduced. **The production blast radius `F295` claims is not
established by anything R1 could measure.** The severe half — *reuse* of the dead connection —
needs the process to keep running past a loop close, and in the Hub the only loop close is process
exit. What production actually gets today is an uncaught worker-thread traceback on stderr at
shutdown, on a process that is leaving anyway.

**R2 attacked "leaving anyway" and it held, on a fact R1 did not have.** A raw `aiosqlite`
connection's worker is a **non-daemon** thread (`aiosqlite/core.py:90`, measured `daemon=False`),
which would make a never-disposed engine block `threading._shutdown` and hang the exit outright. It
does not, because SQLAlchemy's aiosqlite dialect sets `connection._thread.daemon = True` at connect
time (`sqlalchemy/dialects/sqlite/aiosqlite.py:412`, SQLAlchemy 2.0.50) — measured `daemon=True`
through an engine of exactly `hub/hub/db/engine.py`'s shape, which then exited in 0.35s with the
engine never disposed. So the Hub's threads are abandoned at exit rather than joined, and the
severity paragraph above stands. It is recorded because it is the first thing a reader will reach
for to argue the impact is worse, and it is the wrong reach.

Where the damage is demonstrated is the **test suite**, which does close a loop per test against
that same process-global engine — `hub/tests/conftest.py:293`'s
`_no_connection_outlives_its_event_loop` exists for precisely this hazard and says so in its
docstring, and `F292`'s history includes a CI run that sat for 3.5 hours before being cancelled by
hand. That fixture cancels background tasks and gathers them before disposing, which settles the
*coroutines*; as the finding says, nothing there can wait for the worker **thread**.

**R2 pushed on this too, and it needs qualifying.** Because that fixture disposes the engine after
*every* test, the pooled-reuse precondition is not routinely reachable in the suite either: each
test starts against a pool with nothing carried over. Two paths get past it, both read out of the
code rather than assumed:

- **The settle's own cap skips the dispose.** `conftest.py`'s fixed-point loop ends in a
  `for ... else: raise AssertionError(...)` (`:364-368`) and `await _REAL_ENGINE.dispose()` sits
  *after* it (`:369`). Hitting the pass cap therefore raises before disposing, and the pool —
  connections and all — carries straight into the next test's event loop. The cap is the one
  condition under which the fixture that exists to prevent this hazard stops preventing it.
- **`dispose()` does not close a checked-out connection.** A leaked run task still holding one keeps
  it; it is detached rather than closed, so nothing in the fixture reaches it.

Both are worth stating because they narrow the claim from "the suite demonstrates the damage" to
"the suite demonstrates it on the paths where its own guard fixture does not run". That is still the
larger of the two blast radii, and it is smaller than R1 implied.

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

## Round 2 — what the second reading changed

R2 re-ran every measurement rather than quoting R1's numbers, and re-derived the argument from the
code instead of re-reading R1's reasoning. All four reproductions came out the same: shape A benign
and shape B fatal (`probe_cancel.py`), `AsyncAdaptedQueuePool` with the driver connection and its
thread reachable from a `checkout` listener (`probe_pool.py`), the raise-only guard hanging
(`probe_guard1.py`), and neutralise-then-raise printing `RECOVERED, select 2 -> 2`
(`probe_guard2.py`).

**The load-bearing negative survived.** R1 named it itself: that no production path closes an event
loop while the Hub keeps running. Re-derived independently — `asyncio.run` appears in `hub/hub/`
exactly once outside a comment, in `migrations/env.py:78`; there is no `new_event_loop`, no
`set_event_loop`, no `run_until_complete` and no `anyio`/`trio` anywhere in the package; the only
`asyncio.to_thread`/`run_in_executor` targets are synchronous functions, not loop-openers; and
`init_db()`, which is what drives alembic's loop, has exactly one call site (`main.py:348`). The
negative is now earned twice rather than asserted once.

**Three things changed, and one question R1 left open is now answered.**

1. The timeout measurement was of the symptom, not the reason. It now separates the two, and the
   precise version rules out more repairs than the vague one did (see measurement 1 above).
2. The severity paragraph gained the fact that would otherwise have been used against it: the
   worker threads are daemon threads *because SQLAlchemy makes them so*, not because aiosqlite does.
3. The test-suite half was overstated. The teardown fixture disposes every test, so the hazard is
   reachable there only on the paths where that fixture does not complete — one of which is its own
   pass cap raising before the dispose.
4. **`tasks.md` 2.4 is answered rather than left as a question**, and the answer changes the
   ordering task: the settle must come **after** `shutdown_scheduler()`, not between it and
   `terminate_all_active_runs()`. `JobScheduler.shutdown` calls APScheduler's
   `shutdown(wait=False)` (`hub/hub/scheduler.py:2372`), and `AsyncIOExecutor.shutdown` cancels its
   pending job futures without awaiting them — the comment in APScheduler 3.11.2 says there is no
   way to honour `wait=True`. A scheduled job reaches `_background_runs` through
   `_scheduled_job_runner` → `_fire_job_by_id` → `_do_fire_job` → `turn_scheduler.schedule_agent` →
   `agent_trigger.trigger_agent_directly` → the `create_task` at `agent_trigger.py:1190`, registered
   at `:1230`. Settling before the scheduler is stopped settles a set the scheduler can still refill.

R2 also measured one thing the guard needed and nobody had asked: the reconnect it forces **re-fires
the `connect` listener**, so a replacement connection is configured, not bare — through a listener
of `hub/tests/conftest.py:84`'s shape the replacement came back with `busy_timeout = 30000`
(`probe_guard3.py`). Without that, the guard would have quietly swapped a 30-second busy timeout for
a 5-second one inside the suite, which is precisely the asymmetry `F292` has already cost a day to.

R2 found nothing that invalidates the change. The two requirements and the shape of the fix are
unchanged.

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
