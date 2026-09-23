## 0. Rounds — no task below may start until R2 and R3 are recorded in `spec-queue/tracks/B9.md`

- [x] 0.1 R2 (2026-09-24, recorded in `spec-queue/tracks/B9.md`; SQLAlchemy measurement re-run and matched): re-derive D1-D4 from the code without reading R1's argument first: `hub/hub/sse.py`, `hub/hub/run_divergence.py:66-107`, `hub/hub/task_transition_service.py:700-800`, every `persist_event(..., commit=False)` site, and the SQLAlchemy event order (re-run the measurement in design D1 in a scratch script outside the repo)
- [ ] 0.2 R3: a second independent re-derivation; `openspec validate an-event-is-announced-only-once-its-write-is-committed --strict` passes
- [ ] 0.3 Operator approval in `spec-queue/APPROVALS.md`

## 1. Tests first — each must fail on today's code unless marked as a control

New file `hub/tests/test_an_event_is_announced_after_commit.py`. Spy on `SSEManager.publish` (design D2); on today's code, where `publish` does not exist, the spy is on `broadcast` and the test records which.

- [ ] 1.1 (F335) Reuse `_divergence_leg` from `hub/tests/test_a_refused_review_leaves_nothing_behind.py` (a completed task with an open divergence, then a review refused at delivery through `schedule_agent`). Assert `"run_divergence_resolved"` is **not** among the frames published, the divergence's `resolved_at` is `None`, and 0 `run_divergence_resolved` event rows exist. Record that it FAILS today (F335's measurement: `['run_divergence_resolved']`)
- [ ] 1.2 Control, PASSES today and must keep passing: the same fixture, but the review is **not** refused. Exactly one `run_divergence_resolved` frame is published, carrying `{"task_id", "count": 1}`, and one event row exists. This is what makes 1.1 non-vacuous: the same spy sees a true resolution
- [ ] 1.3 (D3) The operator route. A completed task with one open divergence; `PATCH /projects/{p}/tasks/{id}` to `under_review` with the publish spy on. The frames in order are `run_divergence_resolved` then `task_updated`, and the test asserts the index of the first is less than the index of the second (it fails if the listener published after the route's own broadcast). PASSES today; must keep passing
- [ ] 1.4 (D1) Unit, on a bare `async_session_factory()` session: `defer_broadcast` then `rollback()` publishes nothing; `defer_broadcast` then closing the session without commit publishes nothing, and a later commit on a **new** session publishes nothing (the list did not leak); `defer_broadcast` then `commit()` publishes once; a second `commit()` on the same session publishes nothing more. FAILS today (the helper does not exist)
- [ ] 1.5 (D2) A deferred announcement whose payload cannot be serialised (`{"x": float("nan")}`), followed by a good one, then `commit()`: `commit()` does not raise, the row committed, the good frame is published, and the failure is logged. FAILS today (the helper does not exist)
- [ ] 1.6 (D4) `test_no_staged_event_is_broadcast_before_commit`: the AST guard. FAILS today on `hub/hub/run_divergence.py:104`, and on nothing else
- [ ] 1.7 Control: `hub/tests/test_sse.py`, `hub/tests/test_operator_events.py` and `hub/tests/test_a_refused_review_leaves_nothing_behind.py` pass before and after; record the counts

## 2. The fix

- [ ] 2.1 (D2) `hub/hub/sse.py`: move `broadcast`'s body into a sync `publish`; `broadcast` calls it. Keep the docstring's project-stamping contract on `publish`
- [ ] 2.2 (D1) `hub/hub/sse.py`: add `defer_broadcast(session, project_id, event_type, data)` and two module-level listeners on `sqlalchemy.orm.Session`: `after_commit` (skip when `session.in_nested_transaction()`; pop the pending list; `publish` each inside `try/except Exception` with `logger.exception`) and `after_transaction_end` (when `transaction.parent is None`, drop any pending list). Import-time registration, so every session the Hub opens is covered
- [ ] 2.3 `hub/hub/run_divergence.py:104`: replace the `await sse_manager.broadcast(...)` with `defer_broadcast(session, ...)`. Rewrite the docstring's `:82-83` sentence to say why the announcement waits for the caller's commit, naming F335
- [ ] 2.4 Update the note in `test_a_refused_review_does_not_close_an_open_divergence`'s docstring (`test_a_refused_review_leaves_nothing_behind.py:868-872`), which records the escaped broadcast as an accepted residual: it is closed by this change
- [ ] 2.5 Run group 1 (all pass), then `py -3.11 -m pytest hub/tests -q`; record the count. `ruff check hub/`, `black --check --target-version py311 hub/hub hub/tests`

## 3. Close out

- [ ] 3.1 Mark F335 fixed in `scripts/drive/FINDINGS.md` with the commit, and note that F251's coupling is released
- [ ] 3.2 Reconcile the requirement into `openspec/specs/local-project-workspace/spec.md` on archive
