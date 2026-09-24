## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2 (2026-09-24, recorded in design.md's round log and `spec-queue/tracks/B12.md`): re-derive the proposal against `hub/ui/src/components/agents/NewConversationSurface.tsx:62-121`,
  `hub/hub/api/v1/spec.py:1419-1467`, `hub/hub/spec_service.py:115-280`,
  `hub/hub/spec_lifecycle.py:170-222`, and `hub/hub/api/v1/agent_trigger.py:180-250,1405-1671`.
  In particular:
  - list every refusal `trigger_agent` can raise, and put each one on one side of D1's creation
    point;
  - check whether a dispatch refusal that is *not* F108's (`request_level` false) can still reach
    the caller as an error. If one can, D2's table is missing a row;
  - check whether the spec list's default view hides archived documents, because that bears on
    D-B12-1;
  - challenge D3 against `spec-document-authority` `:1891`'s "rather than a separate deletion
    path".
- [x] 0.2 R3 (2026-09-24): a second independent re-derivation. `openspec validate
  a-refused-first-send-leaves-no-exploration-behind --strict` passes. Added `rerender_phase` to the
  retire (2.2, 1.2) and D3's reachability argument.
- [x] 0.2a Operator review (2026-09-24, Opus adversarial review): D-B12-1 (archive, never delete) and D-B12-2 (refuse) approved. Fixes applied to 1.3, 1.6, 2.3; 1.10, 1.11, 1.12 and 2.5 added (design, *Operator review* and D6)
- [ ] 0.3 The operator answers D-B12-1 and D-B12-2 in `spec-queue/DECISIONS.md` and approves the
  change in `APPROVALS.md`.

## 1. Tests first — each must fail on today's code unless marked as a control

Route tests go in a new `hub/tests/test_a_refused_first_send_leaves_no_exploration.py`. Use the
trigger fixtures from `hub/tests/test_failed_run_returns_input.py`, and a git-less project
workspace under `tmp_path` so the `spec/` files can be listed.

- [ ] 1.1 An archived agent, with `start_exploration: true`: the answer is 409 with the archived
  sentence. `spec_documents` has no row for the project, and `spec/` holds no `.html`. Record that it
  FAILS today, with a 422 for the unknown field. The failure's *reason* moves in group 2; before
  that, reproduce the orphan with the two-request sequence the composer sends today (1.1b).
- [ ] 1.1b Reproduction of F330 on today's code: `POST /project/documents`, then `POST
  /agent/trigger` to an archived agent. Assert that exactly one orphan row and one file exist. This
  is a characterisation test. Keep it, inverted, as the regression in 1.1 once the composer no
  longer sends the first request.
- [ ] 1.2 A dispatch refusal naming the entry (F108), sent with `start_exploration`. R2: a new operator conversation carries no
  review, and D1 now refuses `start_exploration` with `review_task_id`, so stage a refusal that
  needs neither: an agent name with no `Agent` row (`agent_trigger.py:676-687`, which the route
  does not check) or a runner with no execution adapter (`:731-738`). The answer is that
  refusal's status. The entry is `withdrawn`. The document is `archived`, its `created` event is
  still present, its last event is a `phase` event whose reason is the refusal's detail, and a
  `spec_updated` event was broadcast, and the file's rendered status reads archived (R3: fails
  if `rerender_phase` is left out). Record that it FAILS before group 2.
- [ ] 1.2b The same, with `withdraw_refused_entry` patched to return `False` (the scheduler got
  there first). The document is still archived. Fails if the retire call is nested under the
  withdraw's `True` branch.
- [ ] 1.3 An accepted send: 200. `spec_document` in the response names a row in `exploring` and a
  file that exists. The queue entry's `spec_document` is that path, and the dispatched turn's
  context carries the spec notice (`spec_turn_notice`). A `spec_updated` event with
  `{"path": <that path>, "phase": "exploring"}` was broadcast after the commit (operator review:
  `POST /project/documents` broadcasts it at `spec.py:1467`, and the new route must too; capture
  `sse_manager.broadcast` as existing trigger tests do). Record that it FAILS before group 2.
- [ ] 1.4 Retry: three refused sends (archived agent), then unarchive, then one accepted. Exactly
  one row and one file exist.
- [ ] 1.5 Naming exhausted: patch `spec_service.mint_document_path` to raise
  `NamingExhaustedError`. The answer is 409 with `code == "naming_exhausted"`, and no conversation
  row and no entry exist.
- [ ] 1.6 Commit failure: patch the session's commit at the route's commit point to raise once.
  The answer is **503** with `code == "send_not_saved"` and a sentence (operator review; today a
  bare 500). No file remains under `spec/`, **and the minted `spec/changes/<placeholder>/`
  directory is gone too** (`write_document` created it, `spec_documents.py:163`), while `spec/` and
  `spec/changes/` themselves still exist. No conversation row and no entry exist.
- [ ] 1.7 D3's guard, unit-level on `retire_refused_exploration`:
  - (a) a document with an extra content event after creation is left in `exploring`, and the
    function returns `False`;
  - (b) a document moved to `proposed` is left in `proposed`;
  - (c) a document named by a task's `spec_document_id` is left alone (`transition`'s own
    `archive_would_orphan_work` guard; the function returns `False` rather than raising);
  - (d) a fresh one is archived, and its row, its events and its file all still exist.
  Each of (a) and (b) must fail if its condition is deleted from the function (mutation-check it
  once). No test may observe a deleted `spec_document_events` row.
- [ ] 1.8 `start_exploration` with `spec_document` gives 400, and so do `conversation_id`,
  `session_mode="resume"` and `review_task_id` (D1).
- [ ] 1.9 vitest, `hub/ui/src/__tests__/newConversationSurface.test.tsx`: armed send makes **one**
  fetch, to `/agent/trigger`, with `start_exploration: true` and no `/project/documents` call.
  `onStarted` gets the response's `spec_document`. Replace *"still starts the conversation when the
  document cannot be created"* with *"a refused armed send keeps the text and opens nothing"*. Keep
  *"creates no document when exploration was not declared"* as a control, and assert that
  `start_exploration` is `false` or absent.

- [ ] 1.10 (D6, the concurrent loser) Patch `spec_service.mint_document_path` to return one fixed
  path `P`. Patch the route session's commit to raise once, and wrap its `rollback` so that, once,
  after the real rollback returns, it runs a competing `spec_service.start_exploration` for `P` in a
  **separate** `async_session_factory()` session with a different title, and commits it (the winner
  of the gap D6 names). The armed send answers 503. Assert: the winner's row exists at `P`, and the
  file at `P` still exists and holds the winner's bytes, not this request's. Fails if the cleanup
  unlinks `P` unconditionally.
- [ ] 1.11 (D2, operator review) `write_document` patched to raise `OSError("disk full")`, then
  `ProjectPathError`: each answers **409** with `code == "exploration_write_failed"` and a message
  containing *"the exploration's file could not be written"*. No row, no conversation, no entry, no
  file, and no minted directory. Record that each is a 500 today (after group 2's field exists).
- [ ] 1.12 (D6, unit-level on `discard_unrecorded_exploration`) (a) the file's bytes differ from
  `written`: kept; (b) a committed row holds the path: kept; (c) `written` is `None` (the write never
  returned): nothing removed; (d) all three conditions hold: file removed and its now-empty
  directory pruned; (e) as (d) but the directory holds another file: file removed, directory kept;
  (f) never removes `spec/` or `spec/changes/` itself. Mutation-check (a) and (b) once each.

## 2. The fix — commit A (Python only)

- [ ] 2.1 `spec_service.start_exploration(...)`: move `spec.py:1429-1462`'s mint, create and save
  sequence into it, and call it from `POST /project/documents`. Behaviour is unchanged there. The
  existing document-creation tests are the control.
- [ ] 2.2 `spec_service.retire_refused_exploration(...)`, per design D3: archive through
  `spec_lifecycle.transition`, then `rerender_phase`, then commit and broadcast, as `POST
  /documents/phase` does. Never delete.
- [ ] 2.3 `TriggerAgentRequest.start_exploration` and `TriggerAgentResponse.spec_document`. In
  `trigger_agent`, implement the 400 conflicts, the creation immediately before `new_entry`, the
  compensated commit, and the retire call in the F108 branch whatever `withdraw_refused_entry` returns. Also set
  `spec_document` on every 200 response, including the one built from `scheduled.response`.
  Operator review: broadcast `spec_updated {"path": path, "phase": "exploring"}` right after the
  commit (`agent_trigger.py:1587`), beside `queue_entry_queued`; answer `OSError`/`ProjectPathError`
  from the write with 409 `exploration_write_failed`, the `uq_spec_documents_project_path`
  `IntegrityError` with 409 `document_exists`, and a failed commit of an armed send with 503
  `send_not_saved`, each with a sentence (design D2). Every failure after the write rolls back and
  then calls task 2.5's cleanup.
- [ ] 2.5 (D6) `spec_service.discard_unrecorded_exploration(session, workspace, project_id, path,
  written)`: after the rollback, unlink the file only if `written` is set, the file's content equals
  it, and `spec_lifecycle.get_document` finds no row for the path; then prune the parent directory
  with `_prune_if_empty`'s rule (`spec_documents.py:189-204`), made a public helper of
  `spec_documents` rather than copied. Log and swallow `OSError`.
- [ ] 2.4 Run group 1's Python tests, with `claude` stripped from PATH, then the lint block.
  Commit and push.

## 3. The fix — commit B (UI bundle), only after `:8000` has restarted past commit A

- [ ] 3.1 Confirm with the operator that `:8000` has restarted past commit A. Do not restart it
  yourself.
- [ ] 3.2 `NewConversationSurface.tsx` per design D4. `make ui`. Commit `hub/ui/src` and
  `hub/hub/static/ui` together.

## 4. Verify

- [ ] 4.1 Trial Hub `:8010`: archive an agent, arm explore, send three times, and list `spec/` and
  `GET /project/documents`. There are no new documents in the current tree or under `spec/`. Unarchive and send once, and exactly one
  document exists and opens in the side panel. Record the output in design.md's round log.
- [ ] 4.2 Close F330 in `FINDINGS.md` and regenerate the backlog. Note that the eight existing
  LoopEngine orphans are not removed by this change; the operator can archive them.
