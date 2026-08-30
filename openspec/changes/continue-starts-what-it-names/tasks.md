## 1. Reproduce the defect as a failing test first

- [x] 1.1 Add `hub/tests/test_a_start_is_reported_to_its_own_input.py`. Build the mismatch deliberately: one agent, two open conversations, a queued entry on conversation B with the **lower** `sequence`, a second entry on conversation A.
- [x] 1.2 `POST …/conversations/{A}/continue`, then assert the run that appears is bound to **B** — query `Run` by `conversation_id`, never by recency, so the assertion cannot pass on a stale row.
- [x] 1.3 Assert the current answer: `started: true`, `conversation_id == A`, no field naming B. Write the failure message so it says which conversation actually started.
- [x] 1.4 Run the file against unmodified code and confirm it passes — a reproduction that does not pass first is not a reproduction.

## 2. Report the start against the input it is about

- [x] 2.1 In `continue_conversation` (`hub/hub/api/v1/checkpoints.py:254-277`) derive `started` from `result.response is not None and result.response.conversation_id == conversation_id`, mirroring `agent_trigger.py:1353`. Do not add fields to `ScheduleResult`; do not touch `turn_scheduler.py`.
- [x] 2.2 Add `started_conversation_id` to the response, from `result.response.conversation_id` when a turn began and `None` otherwise.
- [x] 2.3 For the mismatch case, ask whether the addressed conversation has queued input — `queued_entries(session, project_id, agent, conversation_id)`, the parameter's first caller — and set one of two distinct `waiting_reason`s: it has input, waiting behind other input; or it had nothing queued. Both distinct in wording from the scheduler's own `"queue is empty"`, which is about the agent, so a reader or a test cannot confuse the three.
- [x] 2.4 Add a test pinning that `POST /agent/trigger` still satisfies the same requirement (`agent_trigger.py:1344-1358`), so the two conversation-addressed routes cannot drift apart again. This is the test that would have caught the defect.
- [x] 2.5 Extend the route docstring: the addressed conversation is what `started` is about, the started conversation is reported separately, and the turn is the agent's.

## 3. Flip the reproduction into a guard

- [x] 3.1 Rewrite task 1.3's assertion to the required behaviour: `started: false`, `conversation_id == A`, `started_conversation_id == B`, `waiting_reason` set.
- [x] 3.2 Assert A's queue entry is **still queued** after the call — the waiting answer is only true if the input really is still waiting.
- [x] 3.3 Add the equal case: the addressed conversation is the one that starts, `started: true`, `started_conversation_id == conversation_id`.
- [x] 3.4 Add the nothing-started case: `started: false`, `started_conversation_id is None`, `waiting_reason` set.
- [x] 3.5 Add **F131's own reproduction** as its own case — the addressed conversation has nothing queued while another conversation's entry starts. Assert `started: false`, `started_conversation_id == B`, and a reason saying nothing was queued rather than that input is waiting. This is the case rounds 1 and 2 collapsed into the one above.

## 4. Correct the cutover diagnostic

- [ ] 4.1 In `checkpoint_cutover.py:136-145`, record the case that is currently **silent**: a turn started for a different conversation, so `waiting_reason` is `None`, the branch is skipped, and nothing says the successor did not start. Log it, naming both the successor and the conversation that ran.
- [ ] 4.2 In the existing truthy branch, name the conversation the `waiting_reason` belongs to rather than attributing it to `successor.id` unconditionally. Keep both as logs — `cutover_to_successor` reports no auto-continue outcome (`checkpoints.py:305-312`) and this change does not add one.
- [ ] 4.3 Add a comment recording why it is here: same rule as the route above, and the diagnostic scenario of the new requirement is the only thing covering `auto_continue`, which no shipped requirement governs.
- [ ] 4.4 Add a test with `caplog` for both branches — the silent one is the reason this task group exists, so it is the one that must fail before the fix.

## 5. Tell the operator

- [ ] 5.1 Add `started_conversation_id?: string | null` to `ContinueResult` (`hub/ui/src/api/checkpoints.ts:90-95`).
- [ ] 5.2 Give `handleContinue` (`AgentOutputPanel.tsx:742-756`) its third case, rendering the server's `waiting_reason` rather than composing its own sentence — the backend already distinguishes waiting-behind-input from nothing-queued, and duplicating that judgement client-side is how the two drift. Started and equal → `'Continuing…'`; not started with a `started_conversation_id` → the reason plus the conversation that began; not started without one → the existing reason text.
- [ ] 5.3 Leave the `hasQueuedWork` button gate (`:337-340`, `:1064`) unchanged, and comment why it is not the fix: it reads client-side state in which another conversation's older entry does not appear.
- [ ] 5.4 Add or extend a UI test covering the three notices, keyed on the response fields rather than on rendering timing.

## 6. Reconcile the drive harness

- [ ] 6.1 Update `scripts/drive/t_continue_branches.py` — its F131 assertions are written in the direction the product currently behaves and will now fail. Rewrite them to the fixed direction and note in the file that the flip was the fix.
- [ ] 6.2 Check `t_continue_burns_attempts.py`, `t_row15_cutover.py` and `t_sweep_conversations.py` for reads of the continue response, and update any that treat `started` as "a turn began for the agent".

## 7. Verify and record

- [ ] 7.1 `py -3.11 -m pytest hub/tests/test_a_start_is_reported_to_its_own_input.py -v` green, then the full `hub/tests/` suite. The baseline to compare against is **3555 passed / 84 skipped / 1 xpassed / 0 failed** in 13:38, measured on `a533c68` on 2026-08-29 — the F109 flake did not fire, so a single failure is a regression until shown otherwise, not a shrug.
- [x] 7.2 Confirm `test_continue_does_not_consume_the_work_it_offers_to_start` (`hub/tests/test_a_delivery_attempt_means_a_delivery.py:118-134`) still passes: it asserts `started is False` under a no-runner trigger with one conversation, which holds under the new derivation because `response` is `None`. Checked in round 3; verify rather than assume.
- [ ] 7.3 `py -3.11 -m ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`, `py -3.11 -m mypy src/`, `cd hub/ui && npm run lint`.
- [ ] 7.4 `cd hub/ui && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`; commit `hub/ui/src` and `hub/hub/static/ui` together.
- [ ] 7.5 Drive it live against the 8010 trial Hub with a cheap runner: two conversations, the older entry on the one not addressed, press Continue, confirm the answer says waiting and names what ran, and confirm the addressed conversation's entry is still queued. Nothing closes on unit tests alone.
- [ ] 7.6 Mark F131 fixed in `scripts/drive/FINDINGS.md`, recording both corrections this change established — that F131's own reproduction is unreachable from the shipped UI while the older-entry path is, and that the rule was already shipped for refusals and merely unwritten for starts.
- [ ] 7.7 `openspec validate --strict`, sync the delta into `openspec/specs/agent-conversation-workspace/spec.md`, and archive the change.
