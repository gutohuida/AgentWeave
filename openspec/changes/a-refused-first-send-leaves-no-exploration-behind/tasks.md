## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [ ] 0.1 R2: re-derive the proposal against `hub/ui/src/components/agents/NewConversationSurface.tsx:62-121`,
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
- [ ] 0.2 R3: a second independent re-derivation. `openspec validate
  a-refused-first-send-leaves-no-exploration-behind --strict` passes.
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
- [ ] 1.2 A dispatch refusal naming the entry (F108). Stage a review request that
  `trigger_agent_directly` refuses with `request_level=True` **after** the route's own checks pass;
  `test_a_refusal_names_a_remedy_that_works.py` has one. Send it with `start_exploration`. The
  answer is that refusal's status. The entry is `withdrawn`. No document row, event row or file
  remains, and a `spec_updated` event was broadcast. Record that it FAILS before group 2.
- [ ] 1.3 An accepted send: 200. `spec_document` in the response names a row in `exploring` and a
  file that exists. The queue entry's `spec_document` is that path, and the dispatched turn's
  context carries the spec notice (`spec_turn_notice`). Record that it FAILS before group 2.
- [ ] 1.4 Retry: three refused sends (archived agent), then unarchive, then one accepted. Exactly
  one row and one file exist.
- [ ] 1.5 Naming exhausted: patch `spec_service.mint_document_path` to raise
  `NamingExhaustedError`. The answer is 409 with `code == "naming_exhausted"`, and no conversation
  row and no entry exist.
- [ ] 1.6 Commit failure: patch the session's commit at the route's commit point to raise once.
  The request errors, and no file remains under `spec/`.
- [ ] 1.7 D3's guard, unit-level on `discard_unused_exploration`:
  - (a) a document with an extra content event after creation is kept, and the function returns
    `False`;
  - (b) a document moved to `proposed` is kept;
  - (c) a document named by a task's `spec_document_id` is kept;
  - (d) a fresh one is removed: file, events and row.
  Each of (a), (b) and (c) must fail if its condition is deleted from the function (mutation-check
  it once).
- [ ] 1.8 `start_exploration` with `spec_document` gives 400. With `conversation_id` it also gives
  400.
- [ ] 1.9 vitest, `hub/ui/src/__tests__/newConversationSurface.test.tsx`: armed send makes **one**
  fetch, to `/agent/trigger`, with `start_exploration: true` and no `/project/documents` call.
  `onStarted` gets the response's `spec_document`. Replace *"still starts the conversation when the
  document cannot be created"* with *"a refused armed send keeps the text and opens nothing"*. Keep
  *"creates no document when exploration was not declared"* as a control, and assert that
  `start_exploration` is `false` or absent.

## 2. The fix — commit A (Python only)

- [ ] 2.1 `spec_service.start_exploration(...)`: move `spec.py:1429-1462`'s mint, create and save
  sequence into it, and call it from `POST /project/documents`. Behaviour is unchanged there. The
  existing document-creation tests are the control.
- [ ] 2.2 `spec_service.discard_unused_exploration(...)`, per design D3.
- [ ] 2.3 `TriggerAgentRequest.start_exploration` and `TriggerAgentResponse.spec_document`. In
  `trigger_agent`, implement the 400 conflicts, the creation immediately before `new_entry`, the
  compensated commit, and the discard after `withdraw_refused_entry` returns `True`. Also set
  `spec_document` on every 200 response, including the one built from `scheduled.response`.
- [ ] 2.4 Run group 1's Python tests, with `claude` stripped from PATH, then the lint block.
  Commit and push.

## 3. The fix — commit B (UI bundle), only after `:8000` has restarted past commit A

- [ ] 3.1 Confirm with the operator that `:8000` has restarted past commit A. Do not restart it
  yourself.
- [ ] 3.2 `NewConversationSurface.tsx` per design D4. `make ui`. Commit `hub/ui/src` and
  `hub/hub/static/ui` together.

## 4. Verify

- [ ] 4.1 Trial Hub `:8010`: archive an agent, arm explore, send three times, and list `spec/` and
  `GET /project/documents`. There are no new documents. Unarchive and send once, and exactly one
  document exists and opens in the side panel. Record the output in design.md's round log.
- [ ] 4.2 Close F330 in `FINDINGS.md` and regenerate the backlog. Note that the eight existing
  LoopEngine orphans are not removed by this change; the operator can archive them.
