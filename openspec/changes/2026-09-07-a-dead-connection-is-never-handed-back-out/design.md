# Design — a dead connection is never handed back out

## The mechanism in one paragraph

Every `aiosqlite.Connection` owns one dedicated OS thread that pulls `(future, function)` pairs off
a `SimpleQueue` forever (`aiosqlite/core.py:47-75`). It runs `function()` on that thread and reports
the outcome back with `future.get_loop().call_soon_threadsafe(...)`. If the future's loop has been
closed by the time the call returns, `call_soon_threadsafe` raises `RuntimeError: Event loop is
closed`; the `except BaseException` branch tries to report *that* by making the identical call and
raises again, this time with nothing above it. The thread's `while True` never gets another
iteration and the thread ends. The queue survives, so every later `_execute` still succeeds in
putting work on it — and then awaits a future no one will ever resolve.

The `sqlite3.Connection` underneath is never reached by any `close()`, because closing is itself a
function that has to go through the dead thread.

## Why "cancel it properly" is not the fix

`hub/tests/conftest.py`'s teardown already cancels the background run tasks and `gather`s them
before disposing the engine, and `F295` correctly says that cannot work: `task.cancel()` waits for a
**coroutine** to unwind, and the worker thread is not asyncio-aware and never observes the
cancellation.

R1's shape A shows the stronger version of that: even a *perfectly* awaited cancellation would not
matter, because cancellation is not what kills the thread. A cancelled future is `done()`, and
aiosqlite's `set_result`/`set_exception` both check `done()` first, so the thread's report is a
silent no-op and it survives. The thing that has to be prevented is the **loop closing under an
in-flight call** — which means the fix has to be about *when the loop closes relative to the
connections*, not about how the tasks are cancelled.

That reframing is what makes the shutdown ordering the primary repair rather than a tidy-up.

## Three candidate repairs, measured

### 1. Bound the wait — rejected, and it is important that it was tried

`asyncio.wait_for(..., timeout=6)` around the whole `async with engine.begin(): await
c.execute(...)` did not return. The measurement ran to an external 2-minute kill. Cancelling the
outer task unwinds into SQLAlchemy's connection teardown, which needs the dead thread to close the
connection, so the escape path blocks on the thing it is escaping.

**R2 re-measured this one apart from its symptom** (`testbed/scratch/f295/probe_timeout_reason.py`),
because "it did not return" is equally consistent with the timer being broken, and that would have
made a different repair look promising. It is not the timer. With the statement `shield`ed,
`TimeoutError` fires at 4.0s exactly as asked, with the task still pending; an explicit
`task.cancel()` issued afterwards had **not completed six seconds later**, and `task.get_stack()`
returned an empty list — the task is parked inside SQLAlchemy's greenlet, not at any awaitable the
loop can see. So what never returns is `wait_for`'s await of its own cancellation.

This matters beyond rejecting the option: it means **any** repair that works by giving up on a
statement is unsound here. `asyncio.timeout()` and a smaller bound fail identically, because neither
changes what the cancellation waits for. The single construction that *does* return control is
`shield` plus abandoning the task — and that leaves the pool record checked out forever, converting
an unbounded hang into an unbounded leak that exhausts the pool after `pool_size + max_overflow`
occurrences. The connection has to be made unreachable, not merely abandoned.

### 2. A `checkout` guard that raises `DisconnectionError` — necessary, not sufficient

SQLAlchemy's contract is that a pool `checkout` listener raising `DisconnectionError` causes the
record to be invalidated and the checkout retried on a fresh connection. That is exactly the
semantics wanted. Measured as written, it still hung — because invalidation *closes* the connection
being discarded, and closing goes through the dead thread.

### 3. Neutralise, then raise — the one that recovered

`aiosqlite.Connection.close()` opens with `if self._connection is None: return` (`core.py:199-201`),
so a connection whose `_connection` has been cleared closes instantly and without touching its
thread. Setting `_running = False` alongside it makes any further `_execute` raise
`ValueError("Connection closed")` (`core.py:151-152`) rather than queue work that will never be
answered — a loud failure instead of a silent hang, for anything still holding a reference.

With both set before the `DisconnectionError` is raised:

```
worker alive after kill: False
RECOVERED, select 2 -> 2
```

The pool discarded the record, connected again, and the statement ran.

**This reaches into aiosqlite's private attributes, and that is a real cost.** Two things make it
acceptable rather than merely expedient:

- it is confined to one listener in `hub/hub/db/engine.py`, next to the engine it guards, with the
  version it was measured against named in a comment (`aiosqlite 0.22.1`);
- the attributes are read-and-set, not reimplemented — the semantics being borrowed are the ones
  aiosqlite's own `close()` and `_execute` already branch on, so a rename upstream breaks the guard
  visibly at the `getattr`, and the guard is written to no-op when the shape it expects is absent
  rather than to crash a healthy checkout.

The alternative — vendoring a corrected `_connection_worker_thread` — was considered and is worse:
it would put a fork of a dependency's core loop in product code, and it would not help a connection
whose thread died before the fork was installed.

## Why the shutdown ordering is worth doing anyway

The guard alone would leave production creating a dead thread on every shutdown that catches a run
mid-write, and reporting it as an uncaught traceback the operator has no way to act on. Nothing
downstream breaks, because the process is exiting — but "nothing breaks" is not the same as "the
shutdown is clean", and `terminate_all_active_runs`'s own docstring claims the latter.

Settling the background tasks and disposing the engine **while the loop is still running** is also
the only ordering under which aiosqlite can shut its threads down the way it is designed to:
`Connection.close()` runs the real `sqlite3` close on the worker thread and then awaits the stop
sentinel. That needs a live loop. After the loop closes there is no correct way to do it, only
`__del__`'s best-effort `stop()` (`core.py:96-113`), which the library documents as *"the event loop
may have already been closed"* and which cannot close the sqlite3 handle.

Order matters and is stated in the requirement rather than left to the implementer:

1. terminate the run processes (what `lifespan` already does first),
2. stop the scheduler, so nothing new can be scheduled into the set about to be settled,
3. settle the background run tasks, so nothing is mid-write when the connections go,
4. dispose the engine.

**Step 2 is R2's, and it is not cosmetic.** R1 left it open as `tasks.md` 2.4. The scheduler can put
a run into `_background_runs`: an APScheduler job runs `_scheduled_job_runner` -> `_fire_job_by_id`
-> `_do_fire_job` -> `turn_scheduler.schedule_agent` -> `agent_trigger.trigger_agent_directly`,
which is the `create_task` at `agent_trigger.py:1190` registered at `:1230`. And
`JobScheduler.shutdown` stops it with `shutdown(wait=False)` (`hub/hub/scheduler.py:2372`), which in
APScheduler 3.11.2 cancels the executor's pending job futures and does not await them —
`AsyncIOExecutor.shutdown` carries the comment *"There is no way to honor wait=True without
converting this method into a coroutine method"*. Two consequences that point the same way: settling
before the scheduler is stopped settles a set that can be refilled behind the settle, and the
cancellations the scheduler just issued only land at the settle's first `await`, which is exactly
where you want them.

Doing 3 before 2 is the mistake `conftest.py:317-330` documents having already made once — disposing
underneath an in-flight run takes away the connection it needs to finish, so it never finishes.

## The bounded-settle problem, inherited

`hub/tests/conftest.py:349-370` learned the hard way that settling `_background_runs` is not one
pass: since `F286`, a run whose tail raises hands its input back and releases the queue, and that
release can schedule the same agent again through `turn_scheduler.redrain_queued_agents`, which
registers a **new** task in the set while the `gather` is still running. The fixture loops to a
fixed point with a pass cap and fails loudly on the cap.

Shutdown needs the same shape and one deliberate difference: **shutdown must not raise.** A Hub that
refuses to exit because a run kept rescheduling is worse than one that logs the leftovers and goes.
So: loop to a fixed point, cap the passes, and on the cap log at WARNING with the count and carry
on to the dispose. The cap is a backstop, not the expected path — the product bounds the respawn
chain at `DELIVERY_ATTEMPT_LIMIT` (3).

Whether the two implementations should share one helper is left to the implementer. R1's view is
that they should not yet: the test fixture must fail loudly and the shutdown must not, which is the
whole of the difference, and a shared helper parameterised on "raise or log" is a worse thing to
read than two short loops. Recorded so the decision is visible rather than accidental.

## What R1 did not establish

- **That the reuse hazard is reachable in production.** R1 looked for an in-process event loop that
  closes while the Hub keeps running and found exactly one candidate, alembic's, which disposes its
  own engine in a `finally`. Absence of a path found is not absence of a path. R2 and R3 should
  attack this directly — it is the load-bearing claim behind the severity paragraph in
  `proposal.md`, and it is the kind of negative that is easy to assert and hard to earn.

  **R2 attacked it and it held.** Re-derived from the code without leaning on R1's list:
  `asyncio.run` occurs in `hub/hub/` once outside comments (`migrations/env.py:78`);
  `new_event_loop`, `set_event_loop` and `run_until_complete` occur nowhere in the package; there is
  no `anyio` and no `trio`; every `run_in_executor` / `asyncio.to_thread` target is a synchronous
  callable rather than a loop-opener; and `init_db()` — the only thing that drives alembic's loop —
  is called once, from `main.py:348`. R3 should still not take this as settled: it is a negative,
  and two rounds finding nothing is weaker evidence than one round finding something.
- **That this removes `F292`.** Plausible, unmeasured, and deliberately not claimed.
- **What the guard costs on a healthy checkout.** It is two `getattr`s and an `is_alive()` per
  checkout; `Thread.is_alive()` is a lock-free flag read. Not benchmarked. If it ever shows up, the
  guard can be narrowed to connections that have been idle in the pool, but R1 does not propose
  starting there — a guard that only sometimes looks is a guard nobody can reason about.
- **Behaviour on any driver but aiosqlite.** The guard is written to no-op when the connection does
  not present aiosqlite's shape, so a Postgres deployment is unaffected; that is by construction and
  has not been run.

## What R2 established, and what it still did not

Established, by measurement:

- The worker threads are daemon threads **because SQLAlchemy sets them so**
  (`sqlalchemy/dialects/sqlite/aiosqlite.py:412`), not because aiosqlite does — raw aiosqlite gives
  `daemon=False` (`aiosqlite/core.py:90`). An engine of `hub/hub/db/engine.py`'s exact shape, never
  disposed, exits in 0.35s. This is why the production consequence really is "a traceback on a
  process that is leaving anyway", and it is the fact that would have decided it either way.
- The forced reconnect **re-fires the `connect` listener**, so a replacement connection is
  configured rather than bare: through a listener of `hub/tests/conftest.py:84`'s shape the
  replacement came back reporting `busy_timeout = 30000` (`probe_guard3.py`). Nobody had asked; had
  it come out the other way the guard would have silently downgraded the suite's busy timeout to
  SQLite's 5s default, which is the asymmetry `F292` has already cost a day to.
- The scheduler ordering question (`tasks.md` 2.4) — answered above.

Still not established, and R3 should treat these as open:

- **That the guard fires anywhere the suite would notice.** `hub/tests/conftest.py`'s teardown
  disposes the engine after every test, so a pooled connection does not normally reach a second loop
  at all. R2 found one code path that gets past it — the settle's pass cap raises at `:364-368`
  *before* the `dispose()` at `:369` — but did not run it. Whether the guard is load-bearing for the
  suite or only a backstop is unmeasured, and the proposal's "where the damage is demonstrated"
  paragraph rests on it.
- **What happens if the replacement connection is also dead.** SQLAlchemy retries a
  `DisconnectionError`ed checkout and the retry is bounded, but R2 did not construct the case.
- **Anything about the Hub under load.** Every measurement in this document is a standalone script.
  Not one of them ran against a Hub process — the same gap `F296` came out of.
