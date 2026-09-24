## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [ ] 0.1 R2: independently re-derive every statement after `agent_trigger.py`'s entry commit, what each raises, and what the route answers today; enumerate every post-commit `schedule_agent` call in `hub/hub/api/v1` from `grep` and check each against D4; confirm what `run_reconciliation`'s drain does on a raise. Record in design's round log
- [ ] 0.2 R3: a second independent re-derivation; `openspec validate input-the-hub-accepted-is-answered-as-accepted --strict` passes
- [ ] 0.3 The operator records the F349 remainder decision in `spec-queue/DECISIONS.md`

## 1. Tests first — each must fail on today's code unless marked as a control

New `hub/tests/test_accepted_input_is_answered_as_accepted.py`. Patch `hub.turn_scheduler.schedule_agent` where named (the route imports it inside the function, so the module attribute is what it resolves). Set the retry delays to 0.

- [ ] 1.1 `schedule_agent` raises `OperationalError("database is locked")` once and then behaves normally. `POST /agent/trigger` answers **200**, `status == "queued"`, the D1 `waiting_reason`, and a `queue_entry_id` whose row is `queued`. Record that it FAILS today (500)
- [ ] 1.2 Continuing 1.1: after the retry runs, `schedule_agent` has been called a second time for that agent. Fails if the retry is removed (the entry would only be picked up by an unrelated action)
- [ ] 1.3 `schedule_agent` raises on every call. After the three retries, `run_reconciliation.has_deferred_schedules()` is true, and any request through the app drains it (the patched function is called again). Fails if D2's backstop is removed
- [ ] 1.4 `persist_event` raises for `queue_entry_queued` only. The route answers exactly as the unpatched route does for the same staging, and the SSE broadcast still happened. Record that it FAILS today (500)
- [ ] 1.5 A fake `schedule_agent` that marks the entry `delivered` with a `delivered_in_run_id` and then raises. The route answers `status == "running"` with that `run_id`. Record that it FAILS today (500)
- [ ] 1.6 Each of `messages.py:318`, `agents.py:2257`, `questions.py:212`, `inbound_queue.py:253`, and (R2) `accounting.py:78` (two agents queued; the first raises, the second is still scheduled) and `agents.py:2693` (runner rebind): with `schedule_agent` raising, the route answers what it answers when scheduling succeeds, not 500. **(R3)** And separately, for the five that write one, with `persist_event` raising for the route's post-commit event: the route answers as when it succeeds, and `schedule_agent` **is still called** for the agent. Record which FAIL today (all of the persist cases do: the raise skips the schedule)
- [ ] 1.7 `run_reconciliation.drain_deferred_schedules` with `schedule_agent` raising: the pair is not lost (it is retried or re-deferred). Record that it FAILS today
- [ ] 1.8 Controls, PASS before and after: the existing refusal tests for the trigger (a refusal naming this entry still answers its own status and withdraws the entry), and `test_agent_trigger.py`'s queued-behind-other-input cases
- [ ] 1.9 (R2) `persist_event` raises for `queue_entry_queued`, and the scheduler then returns a refusal naming this entry: the route answers the refusal's own status (not 500 / `PendingRollbackError` / `MissingGreenlet`), the entry is withdrawn, and the answer's `conversation_id` is this request's. Fails if the `except` does not roll back or the answer reads ORM attributes after the rollback

## 2. The fix

- [ ] 2.1 `turn_scheduler.py`: `schedule_accepted` and `retry_schedule` per D1 and D2, with the delays as module constants
- [ ] 2.2 `run_reconciliation.py`: a public `defer(agents)`; `_schedule_now` calls `schedule_accepted`
- [ ] 2.3 `agent_trigger.py`: D3 (guarded event, `schedule_accepted`, the delivered re-read)
- [ ] 2.3a (R3) `utils.py`: `persist_accepted_event` per D3a; every post-commit `persist_event` at the seven sites uses it
- [ ] 2.4 The six other call sites (D4)
- [ ] 2.5 Group 1, then `py -3.11 -m pytest hub/tests/ -q`; record counts inline or do not tick
- [ ] 2.6 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`

## 3. Drive it

- [ ] 3.1 On a trial Hub, hold SQLite's write lock from a second connection (`BEGIN IMMEDIATE`) for ~3 s while sending one message to an idle Haiku agent. Record the response (200 `queued`, D1's reason), release the lock, and record the run that starts without any further action
