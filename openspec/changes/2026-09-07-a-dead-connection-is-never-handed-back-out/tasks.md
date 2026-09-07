# Tasks — a dead connection is never handed back out

Implementation is a night window's. Nothing here is complete on the strength of this plan existing;
only verified implementation closes a task. Written by R1, revised by R2 (2.1 and 2.4 reordered,
2.4 answered, 3.7 and 3.8 added and the mutation-check renumbered to 3.9); R3 has not reviewed
it yet.

## 1. The checkout guard

- [ ] 1.1 Add a `checkout` pool listener on the Hub's engine in `hub/hub/db/engine.py`, next to the
  `create_async_engine(...)` call at `:34`. Reach the driver connection as
  `dbapi_connection._connection` and its thread as `._thread` — both were confirmed reachable from
  a `checkout` listener against `AsyncAdaptedQueuePool` and `AsyncAdapt_aiosqlite_connection`
  (`testbed/scratch/f295/probe_pool.py`). Use `getattr` with a `None` default for both, and return
  without doing anything if either is absent, so a non-aiosqlite driver is untouched.
- [ ] 1.2 **Neutralise before raising, and do not reorder these two lines.** Set the driver
  connection's `_running = False` and `_connection = None`, *then* raise
  `sqlalchemy.exc.DisconnectionError`. Raising alone hangs: SQLAlchemy's invalidation path closes
  the connection it is discarding, and closing queues work for the thread that has already died.
  Measured both ways in `testbed/scratch/f295/probe_guard_lib.py` (hangs) and `probe_guard2.py`
  (`RECOVERED, select 2 -> 2`). A test has to pin this ordering or it will be "simplified" back.
- [ ] 1.3 Comment the listener with the aiosqlite version it was measured against (0.22.1), the two
  private attributes it depends on, and the two-line justification for each — `close()` returns
  immediately when `_connection is None` (`aiosqlite/core.py:199-201`), and `_execute` raises
  `ValueError("Connection closed")` when `_running` is false (`:151-152`), which turns any remaining
  holder's silent hang into a loud failure.
- [ ] 1.4 Log the discard at WARNING with enough to act on: that a connection's driver worker had
  ended and a fresh connection was opened. This is the only place the condition is ever observable,
  and a silent transparent recovery would hide a live defect somewhere else.

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
  the connection away from a run that is still using it.
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
  monkeypatching `is_alive` — queue a `(future, function)` pair whose future belongs to a closed
  loop, which is what `testbed/scratch/f295/probe_guard_lib.py:kill_worker` does, then join the
  thread. A test that fakes the thread's deadness proves the listener reads a boolean, not that the
  recovery works.
- [ ] 3.2 The same test asserts the *recovery*, not just the raise: a statement issued after the
  kill returns a value from a new connection. Give it a real timeout, because the failure mode is a
  hang and an unbounded test hang in CI is the very thing `F292` costs hours to.
- [ ] 3.3 A test that pins 1.2's ordering — with the neutralisation removed, the guarded checkout
  hangs. Write it as a bounded wait that must **not** time out, and confirm it fails when the two
  lines are removed. Do not leave a hanging variant enabled in the suite.
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
- [ ] 3.9 **Mutation-check every one of these before believing them.** The night of 2026-09-06 shipped
  eight unit tests of which the day could only account for seven; the standard this repository now
  holds is that a test names which artefact failed when the fix is reverted. Record the count in the
  night's log the way `n3-units` did.

## 4. Reconcile and record

- [ ] 4.1 Run the CI-gating commands over the CI-gating paths:
  `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`,
  `mypy src/`, `pytest hub/tests/ -v` under `py -3.11`.
- [ ] 4.2 Amend `F295` in `scripts/drive/FINDINGS.md` with R1's correction to its trigger — that
  cancellation with a live loop is benign and loop closure is the precondition — and with whatever
  R2/R3 conclude about its severity. R2 reproduced R1's mechanism independently and did not overturn
  the severity question; it narrowed the test-suite half (the teardown fixture disposes every test,
  so the hazard is reachable there only where that fixture does not complete) and confirmed the
  production half is bounded by process exit, on a measurement R1 did not have — SQLAlchemy, not
  aiosqlite, is what makes the worker threads daemon threads. Do not rewrite the finding's history; append, as the file's
  convention is.
- [ ] 4.3 Delete `testbed/scratch/f295/` or leave it, but do not commit it — it is scratch by
  construction and the measurements it produced are quoted in `proposal.md` and `design.md`, which
  are what the record needs.
- [ ] 4.4 `openspec-sync-specs` then `openspec-archive-change` once the above is verified.
