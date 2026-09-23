# Design — an event is announced only once its write is committed

No operator decision is involved. The one design choice (D1) is recorded with its alternatives so
R2/R3 can re-derive it. Built on HEAD `ce086b6` (= `404c7d5` for every `hub/` file).

## D1 — defer the announcement to the session's commit

Options considered:

| Option | What it does | What it breaks / costs |
|---|---|---|
| **A. Deferred to commit (chosen)** | `defer_broadcast(session, project_id, kind, payload)` appends to `session.info["aw_pending_broadcasts"]`. A listener on SQLAlchemy's `Session` `after_commit` publishes the list when the **root** transaction commits; `after_transaction_end` on the root clears it (after a commit, a rollback, or a close without commit). | Nothing. One new helper; the site that stages keeps its "the caller commits" contract. |
| B. Return the fact to callers | `resolve_divergences_for_task` returns the count and every caller of `apply_transition` broadcasts after it commits. | `apply_transition` has callers in routes and the scheduler; each would need to remember. The next `commit=False` announcement repeats the defect. |
| C. Stop broadcasting the kind live | Keep the event row only; the feed shows it on history reload. | Loses a live signal for a true resolution, and leaves the general shape (announce-before-commit) unguarded. |
| D. `create_task(broadcast(...))` from the listener | Schedules the async broadcast. | Reorders the frame after frames the route sends later; tests become timing-dependent. |

**Measured, not assumed** (R1, SQLAlchemy 2.0.50, `aiosqlite`, `async_sessionmaker(expire_on_commit=False)`
as `hub/hub/db/engine.py:163` builds it; scratch script outside the repo):

```
commit                       -> after_commit, after_transaction_end(root)       [same thread as the loop]
rollback                     -> after_rollback, after_transaction_end(root), after_soft_rollback
close without commit         -> after_transaction_end(root)   (no after_rollback)
begin_nested() released      -> after_commit with session.in_nested_transaction() == True
root commit after a savepoint-> after_commit with session.in_nested_transaction() == False
```

So the listener **must** skip `after_commit` while `session.in_nested_transaction()` is true (the
Hub uses no `begin_nested` today — `grep begin_nested hub/hub` is empty — but the guard is one line
and a savepoint release must not publish a transaction that can still roll back). And clearing must
hang off `after_transaction_end` for the root, not `after_rollback`, because a session closed
without commit fires no `after_rollback`. The listener runs on the event loop's thread (the greenlet
bridge), so `asyncio.Queue.put_nowait` inside it is safe.

## D2 — one synchronous funnel

`SSEManager.broadcast` has no `await` in its body (`sse.py:71-103`). Its body moves into a sync
`SSEManager.publish(project_id, event_type, data)`; `broadcast` becomes `self.publish(...)`. The
commit listener calls `publish`. Every frame therefore passes one point, which the tests spy on.

**The trap this closes.** `hub/tests/test_a_refused_review_leaves_nothing_behind.py:828-835` spies
on `sse_manager.broadcast`. After this change the deferred path does not go through `broadcast`, so
an assertion "`run_divergence_resolved` not in broadcasts" written against that spy would pass on
the fixed code **and on a version that still published at staging time through `publish`**. The
new tests spy on `publish`, and a control (task 1.2) proves the same spy sees the true resolution.

**What `session.commit()` returns when the listener raises.** An exception in an `after_commit`
listener propagates out of `commit()` *after* the database commit has landed, so a route would
answer 500 for a write that happened. `JSONServerSentEvent(...)` serialises in its constructor
(`sse_starlette/event.py`, `json.dumps(..., allow_nan=False)`), so a bad payload can raise there.
The listener therefore wraps each publish in `try/except Exception` and logs it
(`logger.exception`), and goes on to the next pending announcement. The route returns what it
would have returned. Test 1.5 pins this.

## D3 — order against the route's own broadcast

The operator's `PATCH /tasks/{id}` to `under_review` resolves divergences inside
`apply_transition`, commits, then broadcasts `task_updated` (`_commit_and_render`, `hub/hub/api/v1/tasks.py:1456-1472`: commit at `:1470`, broadcast at `:1472`). Today
the wire order is `run_divergence_resolved`, `task_updated` (staging-time broadcast first). With
D1 the listener fires inside `commit()`, which the route awaits before its own broadcast, so the
order is unchanged. Test 1.3 asserts that order from the real route, and would fail if it reversed.

## D4 — guard the shape, not just the site

`hub/tests/test_an_event_is_announced_after_commit.py::test_no_staged_event_is_broadcast_before_commit`
walks `hub/hub` with `ast`: in any function that calls `persist_event(..., commit=False)`, a call to
`sse_manager.broadcast` / `.publish` is a failure naming the file and line. `defer_broadcast` is the
allowed form. On today's tree it fails on `run_divergence.py:104` (and only there — R1's scan).

## Out of scope, noticed

- `new_session_request` (`hub/hub/api/v1/agents.py:3039-3040`) broadcasts before its own
  `persist_event` commits. Nothing is rolled back on that path (the message was committed at
  `:3036`), so it is not F335's shape. Not changed.

## Open questions

None for the operator.
