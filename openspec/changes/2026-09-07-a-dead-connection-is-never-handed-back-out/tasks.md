# Tasks — a dead connection is never handed back out

Implementation is a night window's. Nothing here is complete on the strength of this plan existing;
only verified implementation closes a task. Written by R1, revised by R2 (2.1 and 2.4 reordered,
2.4 answered, 3.7 and 3.8 added and the mutation-check renumbered to 3.9), revised again by R3
(**1.2 replaced** — the neutralisation moves off the checkout listener onto the `close` pool event;
1.5 added; 2.3 gains its reason; 3.3 rewritten; 3.10 and 3.11 added; mutation-check renumbered to
3.12). There is no 3.9 — R2's mutation-check held that number and R3 moved it to 3.12; no task was
lost, and the file holds 24.

**Every `testbed/scratch/f295/probe_*.py` named below was deleted on 2026-09-07** when the testbed
was cleared, which task 4.3 had anticipated. They are quoted as the record of a measurement, per
4.3, and nothing here requires reading one — 3.1 now states its kill mechanism inline rather than
pointing at `probe_guard_lib.py`, and 1.1's attribute path was re-confirmed on 2026-09-08 by reading
the installed library. Repaired by the second review, 2026-09-08.

## 1. The checkout guard

- [ ] 1.1 Add a `checkout` pool listener on the Hub's engine in `hub/hub/db/engine.py`, next to the
  `create_async_engine(...)` call at `:34`. Reach the driver connection as
  `dbapi_connection._connection` and its thread as `._thread` — both were confirmed reachable from
  a `checkout` listener against `AsyncAdaptedQueuePool` and `AsyncAdapt_aiosqlite_connection`
  (measured by `probe_pool.py`, deleted with the testbed on 2026-09-07; **re-confirmed 2026-09-08 by
  reading the installed aiosqlite 0.22.1** — `_thread` is assigned at `core.py:90`, `_running` at
  `:85`). Use `getattr` with a `None` default for both, and return
  without doing anything if either is absent, so a non-aiosqlite driver is untouched.
- [ ] 1.2 **The checkout listener only detects. It raises `sqlalchemy.exc.DisconnectionError` and
  does nothing else.** R1 and R2 had it neutralise the connection inline first, on the measurement
  that raising alone hangs (`probe_guard_lib.py`) — true, and the wrong conclusion. Raising alone
  hangs *because nothing neutralises the connection on the way to its close*, and the checkout
  listener is only one of the four places that close happens. Put the neutralisation at 1.5 instead
  and this listener becomes a short predicate with no ordering to get wrong. Measured:
  `probe_r3_close_listener.py` case A, raise-only checkout plus the 1.5 listener,
  `RESULT after 0.00s: RECOVERED, select 2 -> 2`.
- [ ] 1.3 Comment both listeners with the aiosqlite version they were measured against (0.22.1), the
  two private attributes they depend on, and the two-line justification for each — `close()` returns
  immediately when `_connection is None` (`aiosqlite/core.py:202-203`), and `_execute` raises
  `ValueError("Connection closed")` when `_running` is false (`:152-153`), which turns any remaining
  holder's silent hang into a loud failure. Say in the `close` listener's comment *why it is on
  `close` and not inline in the checkout listener*, naming `dispose()`, or it will be moved back.
- [ ] 1.4 Log the discard at WARNING with enough to act on: that a connection's driver worker had
  ended and a fresh connection was opened. This is the only place the condition is ever observable,
  and a silent transparent recovery would hide a live defect somewhere else.
- [ ] 1.5 **Neutralise on the `close` pool event, which is the one place every close passes
  through.** Add a second listener, `@event.listens_for(engine.sync_engine, "close")`, that applies
  the same dead-worker test as 1.1 and, when it holds, sets `_running = False` and
  `_connection = None` before returning. SQLAlchemy dispatches `close` from
  `_ConnectionRecord.__close()` — reached by `invalidate()` (what 1.2's raise triggers), by
  `QueuePool.dispose()` (**what task 2.3 calls at shutdown**), by a checkin-time close, and by the
  abandon at the end of `_ConnectionFairy._checkout`. A checkout-only guard covers exactly the first
  of those. Measured, all in `testbed/scratch/f295/`:
  - `probe_r3_dispose_hang.py bare` — `await engine.dispose()` on a dead-worker connection idle in
    the pool **never returns** (40-second external kill); `probe_r3_dispose_hang.py close` — the
    same dispose returns in **0.00s**. Without this listener, task 2.3 can hang the shutdown it is
    part of, which is worse than the defect this change fixes.
  - `probe_r3_close_listener.py B` — with the retries exhausted, `fairy.invalidate()` closes a
    connection the checkout listener never saw. Without this listener that hangs (45-second kill);
    with it the caller gets `InvalidRequestError: This connection is closed` in 0.00s.

## 2. Shutdown ordering

- [ ] 2.1 In `hub/hub/main.py`'s `lifespan` teardown (`:357-358`; `:356` is the `yield`), **after
  both `terminate_all_active_runs()` and `shutdown_scheduler()`** — see 2.4, which is now answered
  and is what fixes the position — settle `agent_trigger._background_runs` to a fixed point: cancel
  the current members, `gather(..., return_exceptions=True)`, `difference_update` what this pass
  settled (**not** `clear()`), and loop while the set refills.
- [ ] 2.2 Bound the loop and **do not raise on the bound.** `hub/tests/conftest.py:349-370` is the
  reference implementation and raises `AssertionError` on its cap, which is right for a test and
  wrong here: an instance asked to stop must stop. Log at WARNING with the count of leftovers and
  continue to 2.3.
- [ ] 2.3 `await engine.dispose()` after the settle, while the loop is still running. Disposing
  before the settle is the failure `conftest.py:317-330` documents having already made — it takes
  the connection away from a run that is still using it. **This step depends on 1.5**: measured, a
  dispose with a dead-worker connection in the pool never returns. Do not ship 2.3 without 1.5.
- [x] 2.4 **Answered by R2 — it can, so 2.1's settle goes after it.** The scheduler reaches
  `_background_runs` by a real path: `_scheduled_job_runner` (`hub/hub/scheduler.py:2307`) ->
  `_fire_job_by_id` -> `_do_fire_job` -> `turn_scheduler.schedule_agent` ->
  `agent_trigger.trigger_agent_directly` -> the `create_task` at `agent_trigger.py:1190`, registered
  at `:1230`. And `JobScheduler.shutdown` (`scheduler.py:2369-2373`) stops APScheduler with
  `shutdown(wait=False)`; in APScheduler 3.11.2 `AsyncIOExecutor.shutdown` cancels its pending job
  futures without awaiting them and says in a comment that it cannot honour `wait=True`. So the
  settle placed before `shutdown_scheduler()` settles a set the scheduler can refill behind it, and
  placed after it also gives those just-issued cancellations their first `await` to land on. This
  box is ticked because it is a question, not an implementation step — nothing about it is done.

## 3. Tests

- [ ] 3.1 A test for the guard that kills a worker thread by the **real mechanism** rather than by
  monkeypatching `is_alive`. The mechanism is stated here in full because
  `testbed/scratch/f295/probe_guard_lib.py`, which the earlier rounds pointed at for it, was deleted
  with the testbed on 2026-09-07: open a second event loop, create a future on it, close that loop,
  then `put` a `(future, function)` pair onto the connection's `_tx` queue. The worker runs
  `function()`, tries to report the result with `future.get_loop().call_soon_threadsafe(...)` on the
  closed loop, raises `RuntimeError: Event loop is closed`, raises again reporting *that* the same
  way, and its `while True` ends (`aiosqlite/core.py:47-75`). Join the thread to confirm. A test that
  fakes the thread's deadness proves the listener reads a boolean, not that the recovery works.
- [ ] 3.2 The same test asserts the *recovery*, not just the raise: a statement issued after the
  kill returns a value from a new connection. Give it a real timeout, because the failure mode is a
  hang and an unbounded test hang in CI is the very thing `F292` costs hours to.
- [ ] 3.3 A test that pins 1.5 — with the `close` listener removed, the guarded checkout does not
  recover. Write it as a bounded wait that must **not** time out, and confirm it fails when 1.5 is
  removed while 1.2 stays. Do not leave a hanging variant enabled in the suite. (This replaces R1's
  ordering test, which pinned an arrangement that no longer exists.)
- [ ] 3.4 A test that a healthy checkout is untouched: no reconnection, no WARNING.
- [ ] 3.5 A test that shutdown settles a background run before disposing. Assert the ordering
  directly — a run task registered in `_background_runs` is not pending when `dispose` is called —
  rather than asserting only that shutdown completed, which is true with the bug.
- [ ] 3.6 A test that the settle's bound logs and completes rather than raising, driven by a task
  that re-registers a successor every pass.
- [ ] 3.7 A test that the replacement connection is **configured, not bare** — that the forced
  reconnect re-fires the engine's `connect` listeners. R2 measured this holds
  (`testbed/scratch/f295/probe_guard3.py`: `busy_timeout = 30000` on the replacement, through a
  listener of `hub/tests/conftest.py:84`'s shape), and it is worth a test precisely because the
  failure would be silent: a guard that quietly hands back a connection on SQLite's 5s default busy
  timeout instead of the suite's 30s is a new flake class, not a fix.
- [ ] 3.8 Make `hub/tests/conftest.py`'s teardown dispose in a `try`/`finally`, or otherwise
  unconditionally. Today the settle's `for ... else: raise AssertionError(...)` (`:364-368`) sits
  *before* `await _REAL_ENGINE.dispose()` (`:369`), so hitting the pass cap skips the dispose and
  carries the whole pool into the next test's event loop — the fixture that exists to stop a
  connection outliving its loop stops doing so exactly when something has already gone wrong. Found
  by R2 reading the fixture, **not run**. This is a test-harness change and is **not** a claim to
  resolve `F292`; see `proposal.md`'s "What this deliberately does not change".
- [ ] 3.10 **A test that `engine.dispose()` returns when a pooled connection's worker is dead.**
  This is the one that would have caught R1's and R2's siting mistake, and it is about the shutdown
  half as much as the guard half: kill the worker of a connection sitting idle in the pool by the
  real mechanism (3.1's), then `await engine.dispose()` under a bounded wait that must not time out.
  Confirm it hangs with 1.5 removed — `probe_r3_dispose_hang.py` is the reproduction in miniature.
- [ ] 3.11 A test that the exhausted-retry path raises rather than hangs: force every replacement to
  be born dead (a `connect` listener that kills the new worker), assert
  `sqlalchemy.exc.InvalidRequestError` under a bounded wait. Mark it in a comment as covering an
  unreachable state deliberately — the replacement is always `__connect()`-fresh in reality — so
  that a later reader does not delete it as dead weight or, worse, treat it as evidence the state
  occurs.
- [ ] 3.12 **Mutation-check every one of these before believing them.** The night of 2026-09-06 shipped
  eight unit tests of which the day could only account for seven; the standard this repository now
  holds is that a test names which artefact failed when the fix is reverted. Record the count in the
  night's log the way `n3-units` did.

## 4. Reconcile and record

- [ ] 4.1 Run the CI-gating commands over the CI-gating paths:
  `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`,
  `mypy src/`, `pytest hub/tests/ -v` under `py -3.11`.
- [ ] 4.2 Amend `F295` in `scripts/drive/FINDINGS.md` with R1's correction to its trigger — that
  cancellation with a live loop is benign and loop closure is the precondition — and with what R2
  and R3 concluded about its severity. R3's two additions to that account: the production
  consequence is narrower again, because `agentweave stop` on Windows force-kills and runs no
  lifespan teardown at all (filed separately as `F297`); and the hazard is *the dead worker thread*
  rather than *the outlived loop*, since an idle pooled connection carried into a second loop was
  measured to work normally. R2 reproduced R1's mechanism independently and did not overturn
  the severity question; it narrowed the test-suite half (the teardown fixture disposes every test,
  so the hazard is reachable there only where that fixture does not complete) and confirmed the
  production half is bounded by process exit, on a measurement R1 did not have — SQLAlchemy, not
  aiosqlite, is what makes the worker threads daemon threads. Do not rewrite the finding's history; append, as the file's
  convention is.
- [ ] 4.3 Delete `testbed/scratch/f295/` or leave it, but do not commit it — it is scratch by
  construction and the measurements it produced are quoted in `proposal.md` and `design.md`, which
  are what the record needs.
- [ ] 4.4 `openspec-sync-specs` then `openspec-archive-change` once the above is verified.
