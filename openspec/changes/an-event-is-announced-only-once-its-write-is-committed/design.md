# Design — an event is announced only once its write is committed

No operator decision is involved. The one design choice (D1) is recorded with its alternatives so
R2/R3 can re-derive it. Built on HEAD `ce086b6` (= `404c7d5` for every `hub/` file).

## Operator review, 2026-09-24

The Opus adversarial review found three gaps; all are fixed here (citations re-checked at HEAD
`c1c0fa4`). The operator's B9-Q1 (no runtime allowlist; generated type) and B9-Q2 (the F251 bundle
waits for the `:8000` restart) are confirmed and live in the other two changes.

1. **Rule 1 missed wrapper helpers.** It matched only `sse_manager.broadcast` / `.publish`, so a
   function staging an event row could announce through `_broadcast_run_lifecycle`
   (`hub/hub/api/v1/agent_trigger.py:1881`) or `_broadcast_conversation`
   (`hub/hub/api/v1/agent_chat.py:466`) unseen. Rule 1 now flags any call whose name contains
   `broadcast` (plus `.publish`), except `defer_broadcast` (D4). Re-scanned at HEAD: still fails on
   `run_divergence.py:104` only. Task 1.6 gains an inline-snippet negative control like 1.6b's.
2. **Test 1.4's leak check could not fail.** `session.info` belongs to one session instance, so a
   commit on a *new* session publishes nothing whatever the code does. It now closes the **same**
   `AsyncSession`, commits on it again, and asserts nothing is published.
3. **A late defer in a helper is silent.** Rule 2 sees only a function's own commit; a helper that
   defers after its caller's last commit loses the frame without error. `defer_broadcast`'s
   docstring says so (D1), and task 2.2b requires every new caller to have a test spying on
   `SSEManager.publish`.

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

**`defer_broadcast`'s docstring states its one silent failure (Opus review).** A deferred
announcement is published only by a *later* root commit of the same session. A helper that defers
after its caller's last commit — the caller commits, then calls the helper, then the request ends —
has its list cleared by `after_transaction_end` when `get_session` closes the session, and the
frame is never sent, with no error and no log. D4 rule 2 catches that only when the defer and the
commit sit in the same function; across a call boundary nothing static does. The docstring
therefore says: *stage this before the commit that makes the write durable; if no commit of this
session follows, nothing is published and nothing reports it — so every caller's tests spy on
`SSEManager.publish` and assert the frame arrives.* Task 2.2b makes that test a requirement.

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
walks `hub/hub` with `ast`. Two rules, each failure naming the file and line:

1. In any function that calls `persist_event(..., commit=False)`, a call whose name (the `Name` id,
   or the `Attribute`'s attr) **contains `broadcast`**, or is `.publish`, fails — except
   `defer_broadcast` — **even one placed after that function's own commit**. Matching the substring
   rather than `sse_manager.broadcast` alone is the Opus review's fix: the Hub announces through
   wrappers such as `_broadcast_run_lifecycle` (`api/v1/agent_trigger.py:1881`, which persists and
   broadcasts) and `_broadcast_conversation` (`api/v1/agent_chat.py:466`), and a receiver-name
   match would pass a staged-then-announced path through either. The rule is kept broad
   on purpose (R3): "a function that stages an event row announces through `defer_broadcast`" is one
   sentence a reader can hold; "…unless the broadcast follows a commit in source order" is a
   heuristic that branches defeat. On today's tree it fails on `run_divergence.py:104` only (R1's
   and R3's scans, and the review's re-scan with the substring rule at HEAD `c1c0fa4`: the other
   staging function, `release_task_workspace` in `task_transition_service.py`, calls nothing named
   `*broadcast*`).
2. In a function that calls `defer_broadcast` **and** awaits a `.commit()` of its own, every
   `defer_broadcast` call must come before that function's last `.commit()` call in source order.
   **R3 found the trap this closes:** converting a post-commit `await sse_manager.broadcast(...)` to
   `defer_broadcast(...)` *in place* stages it after the last commit; `get_session` then closes the
   session without committing (`db/engine.py:166-168`), `after_transaction_end` clears the list, and
   the frame is **silently never sent**. `update_job`'s trailing `job_updated`
   (`api/v1/jobs.py:1167`, after `_hand_job_to_scheduler`) is exactly that shape. A function with no
   commit of its own (it leaves the commit to its caller, like `resolve_divergences_for_task`) is
   exempt from rule 2. Rule 2 is conservative: a commit hidden inside a callee
   (`persist_event(commit=True)`, `_hand_job_to_scheduler`) does not count, so a defer placed
   before one of those still fails and must move above the function's own `session.commit()`.

**The failure messages are the instructions for whoever lands second.** Rule 1's message reads:
*"`<file>:<line>` broadcasts in a function that stages an event row with
`persist_event(commit=False)`. Replace it with `defer_broadcast(session, project_id, kind,
payload)` placed before this function's `session.commit()`, in the order the frames go out today,
and spy on `SSEManager.publish` in its tests — a `broadcast` spy no longer sees it."* Rule 2's:
*"`<file>:<line>` defers an announcement after this function's last commit; nothing will publish
it. Move it above the commit."*

**Collision with B10 (R3).** `a-loop-is-stopped-archived-and-delegated-from-its-own-tab` (B10,
design D3/D3a/D3b) moves the event rows of `update_job`, `archive_job`, `archive_loop` and
`set_loop_control` into their transactions with `commit=False`. Each of those functions then
broadcasts after its commit (`job_updated`, `loop_edit_staged`, `job_archived`, `loop_archived`,
`loop_control_changed`, and B10's new `loop_stopped` sites), which rule 1 flags. That is intended:
- **B10 lands first:** this change's task 1.6 fails on those four functions as well, and task 2.4b
  converts them (staged above each function's own commit, in today's wire order).
- **This change lands first:** B10's task 2.2c converts them, and this guard tells it how.

Either way no kind is added (`loop_stopped` and `loop_archived` are already broadcast,
`scheduler.py:3187`, `loops.py:184`), and the frames still go out after the commit they report. No
test spies on those functions' broadcasts today (`grep broadcast hub/tests/test_jobs.py` finds only
a docstring), so the conversion breaks no existing spy. `a-loops-outstanding-mail-is-mail-not-yet-delivered`
(B10) adds no broadcast and does not collide.

## Out of scope, noticed

- `new_session_request` (`hub/hub/api/v1/agents.py:3039-3040`) broadcasts before its own
  `persist_event` commits. Nothing is rolled back on that path (the message was committed at
  `:3036`), so it is not F335's shape. Not changed.

## When it takes effect on `:8000` (R3)

This change is Hub code only. The operator's `:8000` runs this checkout but only picks up Hub code
when the operator restarts it, so until then `:8000` still sends the false frame. Today that is
invisible (the app drops the kind, F251). It becomes visible only when
`every-event-the-hub-sends-reaches-the-app`'s **bundle** reaches `:8000` — and a committed bundle
reaches it on the next page reload, with no restart. That change carries the gate (its task 0.5,
question B9-Q2).

## Open questions

None for the operator in this change (B9-Q2 lives in `every-event-the-hub-sends-reaches-the-app`).
