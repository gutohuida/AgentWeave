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

`aiosqlite.Connection.close()` opens with `if self._connection is None: return` (`core.py:202-203`),
so a connection whose `_connection` has been cleared closes instantly and without touching its
thread. Setting `_running = False` alongside it makes any further `_execute` raise
`ValueError("Connection closed")` (`core.py:152-153`) rather than queue work that will never be
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

**Superseded in part by R3, and the difference matters.** The neutralisation is right; *where it is
performed* was wrong. Doing it inline in the checkout listener protects only the connection that
listener was handed, and leaves `engine.dispose()` — the change's own final shutdown step — able to
hang on a dead connection it never sees. R3 moved it to the `close` pool event, which SQLAlchemy
dispatches before every close of a connection record, and measured that the checkout listener can
then go back to raising alone. See "What R3 established" at the end of this document; `tasks.md`
carries the arrangement that is actually to be implemented.

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

## What R3 established, and what it changed

R3 read the code before the proposal and re-ran the probes rather than quoting them. It did not
overturn the change. It moved the fix, on a measurement neither earlier round made.

### The guard was sited where it does not protect the change's own shutdown step

`await engine.dispose()` — task 2.3, the last thing the new shutdown does — **hangs forever on a
dead-worker connection sitting idle in the pool.** Measured
(`testbed/scratch/f295/probe_r3_dispose_hang.py`): with no listener the process ran to a 40-second
external kill; with the neutralisation moved to a `close` pool-event listener the same dispose
returned in **0.00s**.

`dispose()` never dispatches `checkout`, so a checkout-only guard cannot see the connection it is
about to close. The path is `QueuePool.dispose()` -> `_ConnectionRecord.close()` -> `__close()` ->
`Pool._close_connection()` -> the aiosqlite dialect's `close()`, which is
`self.await_(self._connection.close())` — an await on the thread that ended.

This is the interaction R1 and R2 both missed, and it is not academic: it means the change as
written could convert *a traceback on a process that is leaving anyway* into *a Hub that will not
exit*, which is strictly worse than the defect. It also means `hub/tests/conftest.py`'s per-test
`await _REAL_ENGINE.dispose()` has the same exposure today.

### So the neutralisation moves to the `close` pool event, and the checkout listener only detects

`_ConnectionRecord.invalidate()` dispatches `invalidate`, then calls `__close()`, which dispatches
**`close`** before `Pool._close_connection()` does the closing (SQLAlchemy 2.0.50,
`pool/base.py`). Every path that closes a pooled connection goes through that one event: a
checkout listener's invalidation, `engine.dispose()`, a checkin-time close, and the retry-exhausted
abandon below. One listener there covers all of them.

Measured (`testbed/scratch/f295/probe_r3_close_listener.py`, case A): a checkout listener that
**raises only** — the arrangement `probe_guard1.py` measured as hanging, and which `tasks.md` 1.2
told the implementer never to write — recovers in 0.00s once the `close` listener exists:

```
  checkout: raising DisconnectionError (NO inline neutralise)
  close-event: neutralised a dead-worker connection
RESULT after 0.00s: RECOVERED, select 2 -> 2
```

This is the cleaner arrangement on the repository's own standard, not merely an equivalent one.
The neutralise-then-raise ordering was a fragile pair of adjacent lines with a comment begging not
to reorder them; siting the neutralisation at the event that precedes *every* close removes the
ordering hazard entirely and protects three more paths at the same time.

### R2's open question — "what if the replacement is also dead" — answered

`_ConnectionFairy._checkout` retries a `DisconnectionError`ed checkout with `attempts = 2`, and on
exhaustion calls `fairy.invalidate()` and raises `InvalidRequestError("This connection is closed")`.
That final `invalidate()` closes the connection it is giving up on — a connection the *checkout*
listener never saw, and therefore never neutralised.

Measured (`probe_r3_exhaust.py`, forcing every newly created connection to be born dead): the guard
fires twice, two replacements are created, and then the process **hangs** — it ran to a 45-second
external kill, and a `faulthandler` dump at 15s found the main thread parked in the loop with the
task inside SQLAlchemy's greenlet, exactly where R2's empty `get_stack()` put it. With the `close`
listener in place the same case returns `sqlalchemy.exc.InvalidRequestError: This connection is
closed` **in 0.00s** (`probe_r3_close_listener.py`, case B).

**Reachability, stated so the severity is not inflated:** it is not reachable. The replacement comes
from `_ConnectionRecord.get_connection()` -> `__connect()`, which *creates* a connection; it is
never another connection drawn from the pool, so it cannot be an old dead one, and a freshly
created connection's worker thread has just started. The reason to fix it is not that it happens —
it is that the escape hatch from an unbounded wait must not itself contain one.

### What the surface returns, which nobody had asked

Two answers, both now established rather than assumed:

- **Normal case: nothing.** The recovery is transparent — the statement completes on a fresh
  connection, so an HTTP route returns its normal response and the only trace is the WARNING task
  1.4 asks for.
- **Exhausted case: a 500.** `InvalidRequestError` is a plain exception out of the session; the Hub
  registers exception handlers for `TransitionRefusedError` and `TaskBindingError` only
  (`hub/hub/main.py:406,418`), so nothing catches it and Starlette's default handler answers 500.
  That is the right shape for an unreachable internal failure and needs no route-level work — but
  it is a **500, not a hang**, only once the `close` listener exists. Without it the request never
  answers at all.

### The test-suite half, narrowed again — one of R2's two paths is measured false

R2 named two paths past `conftest.py`'s teardown to a carried-over pool. The second one —
*`dispose()` does not close a checked-out connection* — is true and is **not** a route to the reuse
hazard. `Engine.dispose()` ends with `self.pool = self.pool.recreate()`, so a connection checked
out at that moment belongs to a pool the engine no longer references and can never be handed out by
the engine again. Measured (`probe_r3_dispose_pool.py`): pool replaced `True`, the connection still
open with a live worker, and after three subsequent checkouts `old connection reappeared from the
engine's pool: False`.

That path leaks a file handle, which is `F292`'s subject, not this change's. The suite's only route
to the reuse hazard is the one R2 found first: the settle's pass cap raising at `:364-368` before
the `dispose()` at `:369`. **One path, not two.** It is still unrun — running it needs an edit to
`hub/tests/conftest.py`, which the day window may not make.

The fact was already in this repository: `conftest.py:138-146` records the pool *replacement*,
measured 2026-09-05, as the reason `pool.checkedout()` cannot see a leaked connection. R2 read the
opposite consequence out of the same behaviour.

### A dead worker is the whole hazard — carrying a connection across loops is not

Measured (`probe_r3_idle_carryover.py`), and neither earlier round asked: a connection left **idle**
in the pool while its creating loop is closed, then used from a second loop, **completes normally**
— `loop2 select -> 2`, guard fired 0 times, worker alive.

The reason is in the driver: `aiosqlite.Connection._execute` builds its future with
`asyncio.get_event_loop().create_future()` — the *calling* loop's — and `self._tx` is a
`queue.SimpleQueue`, which is loop-independent (`aiosqlite/core.py`, 0.22.1). Nothing in a
connection is bound to the loop that created it except a call that is in flight.

Two consequences:

- The guard's condition is **necessary and sufficient**, which is a better position than the change
  claimed for it. "A connection outlived its event loop" is survivable; "its worker thread ended" is
  not, and that is exactly what is tested.
- `conftest.py:293`'s docstring gives the mechanism as *"a pooled connection checked out by the next
  test is bound to a loop that no longer exists"*. As stated that is not sufficient to fail. The 62
  failures it records are real and are not re-explained here — R3 did not measure what caused them,
  and this change does not need to know. Recorded as an open question, not a correction.

### Nothing had ever run against the product's own engine object; now it has

`probe_r3_hub_engine.py` imports `hub.db.engine` with `DATABASE_URL` pointed at a throwaway file,
attaches a pragma listener of `conftest.py:84`'s shape and the F292 checkout/checkin registry
listeners in conftest's order, then the detector and the `close` neutraliser, and kills a pooled
worker:

```
pool class: AsyncAdaptedQueuePool
checkout connection type: AsyncAdapt_aiosqlite_connection -> inner: Connection -> thread: Thread-1 (_connection_worker_thread)
worker alive after kill: False
RECOVERED in 0.01s, select 2 -> 2
replacement busy_timeout: 30000
listener fires: {'checkout': 1, 'close': 1} | f292 registry entries left: 0
dispose returned in 0.00s
```

So on the engine product code actually builds: the pool class, the attribute path 1.1 depends on,
the recovery, R2's `busy_timeout` result, and — new — that the F292 registry is left consistent by
a checkout that raises (the aborted attempt never reaches conftest's listener, because engine.py's
listener is registered first and raises first; the successful retry records normally).

**This is still not a running Hub.** It is the product's engine in a bare process, with no requests,
no scheduler and no background runs. The gap `F296` came out of is narrowed, not closed.

### The shipped `app-lifecycle` spec, checked in full

All six shipped requirements read against the two ADDED ones. **No contradiction.** The nearest
neighbour is *Status, stop, and reset act on the local instance*, and it agrees. Recorded as a
finding of nothing, which is a real outcome.

What the reading did surface is a **reachability gap, not a contradiction**, and it is about the
surface rather than the spec. `agentweave stop` on Windows runs `taskkill /PID <pid> /F`
(`src/agentweave/cli.py:534-535`) with no signal first, despite the function's docstring saying
"graceful SIGTERM, then forced" — the POSIX branch does send SIGTERM, the win32 branch does not.
Measured with a uvicorn app whose lifespan writes a marker on teardown
(`probe_r3_taskkill_app.py`): after `taskkill /F` the marker is absent and the log has no
"Shutting down" line. So on the operator's own platform the new shutdown sequence never runs on the
product's own stop path; it is reachable via `docker compose down`, `--no-detach` plus Ctrl+C, and
a reload.

Two things follow. The requirement now says so — it governs a shutdown that runs at all — and
making `agentweave stop` graceful is **out of scope here**, filed separately as `F297`, because it
is a CLI defect against a shipped requirement (*"active runs across projects are terminated through
normal shutdown"*) and not part of this change.

### What R3 did not do

- Did not run `conftest.py`'s cap-skips-dispose path. It needs an edit to the test harness that this
  window may not make. It remains the one unmeasured link under the proposal's "where the damage is
  demonstrated" paragraph.
- Did not run anything against a live Hub process. See above for how far the gap was narrowed.
- Did not re-measure `probe_guard1.py`'s hang. It is superseded: the arrangement it condemns is now
  measured to *work* when the `close` listener exists, which is a stronger statement than repeating
  that it fails without one.
- Did not investigate what actually caused the 62 failures behind `conftest.py:293`. Named as an
  open question above.
