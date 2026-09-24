## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [ ] 0.1 R2: independently re-derive every place a permission decision is reached and whether the Hub observes it (the Claude approver's `_report_decision`, the operator card, Codex's approval loop, `acceptEdits` and full access, which have no approver); confirm both execution paths' `finally` blocks reach the flush on every ending. Record in design's round log
- [ ] 0.2 R3: a second independent re-derivation; `openspec validate a-run-records-that-its-calls-were-allowed --strict` passes
- [ ] 0.3 The operator records the F389 decision in `spec-queue/DECISIONS.md` (count, or accept the gap)

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 New `hub/tests/test_permission_tally.py`: a run, three `POST /permission-decisions` with `allowed: true` under its credential, then the run's flush. `Run.permission_decisions == {"allowed": 3, "refused": 0}`. Record that it FAILS today (no column)
- [ ] 1.2 Same file: a run with no decisions, flushed: `permission_decisions` is `None`
- [ ] 1.3 Same file: after one allowed decision and **no** flush (the Hub died), the row already reads `allowed >= 1`
- [ ] 1.4 Same file: an allowed decision writes no `event_logs` row; a refused one still writes exactly one `permission_denied` (control on the event half)
- [ ] 1.5 Same file: an operator-refused call (its card already `denied`) counts as refused and still records no second event
- [ ] 1.6 Same file: `permission_tally.note` with the database patched to raise leaves the route's answer at 202
- [ ] 1.7 `hub/tests/test_codex_appserver_run_turn.py`: `on_decision` is called once per decision with the final verdict, including an operator-asked one, and only **after** `session.respond` for that request (assert the order on the fake session). Fails today (no `on_decision`)
- [ ] 1.8 Migration test: upgrade adds the nullable column; existing rows read `NULL`
- [ ] 1.9 `test_permission_tally.py`: **the response does not wait for the count.** Call `record_permission_decision` directly with a `BackgroundTasks` instance and `permission_tally.write_counts` patched to an `AsyncMock`: the handler returns 202 with `write_counts` **not** awaited, and the `BackgroundTasks` holds exactly one scheduled `write_counts(run_id)` for a first allowed decision (none for a second one). Then, through the ASGI client, a `write_counts` patched to raise still answers 202 with the unchanged body. Record that it FAILS today (the handler takes no `BackgroundTasks`, and nothing is counted)
- [ ] 1.10 `test_permission_tally.py`: **a late first-sight write cannot lower the exact flush.** Note twelve allowed decisions and flush (row reads `{"allowed": 12, "refused": 0}`); then run a stale first-sight write carrying `{"allowed": 1, "refused": 0}` for the same run: the row still reads 12. A `note()` for that run after the flush is dropped (`note` returns `False`, no entry is re-created). Record that it FAILS today

## 2. The fix

- [ ] 2.1 `db/models.py` `Run.permission_decisions` and the migration (next free revision; `.claude/rules/db-migrations.md`)
- [ ] 2.2 `hub/hub/permission_tally.py` (D2): in-memory `note`, monotonic `max`-per-key `write_counts` in its own session, `flush` that marks the run closed
- [ ] 2.3 `agent_actions.py` `record_permission_decision`: takes `background_tasks: BackgroundTasks`; `note` for every decision (before the `_operator_already_refused` early return); a first sight schedules `write_counts` on `background_tasks`, never awaits it; the refusal event unchanged. Correct the docstring at `:987`: the caller (`mcp_server._report_decision`) **does** wait for this answer, up to its 10-second `urlopen` timeout, before the decision reaches Claude, and discards only the body; so nothing slow may run in the handler
- [ ] 2.4 `codex_appserver.py` `on_decision`, awaited after `session.respond`; `agent_trigger.py` wires it (a first sight goes to `asyncio.create_task`, held in a set) and flushes in both `finally` blocks
- [ ] 2.5 The run response schema returns the field
- [ ] 2.6 Group 1, then `py -3.11 -m pytest hub/tests/ -q`; record counts inline or do not tick
- [ ] 2.7 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`

## 3. Drive it

- [ ] 3.1 On a trial Hub, one Haiku turn under "Workspace only" that runs two in-workspace commands, and one that is asked to write outside: read each run's `permission_decisions`
