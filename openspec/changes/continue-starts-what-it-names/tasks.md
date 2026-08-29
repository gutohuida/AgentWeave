## 1. Reproduce the defect as a failing test first

- [ ] 1.1 Add `hub/tests/test_continue_starts_what_it_names.py`. Build the mismatch deliberately: one agent, two open conversations, a queued entry on conversation B with the **lower** `sequence`, a second on conversation A. Assert the current behaviour so the test is a reproduction before it is a guard.
- [ ] 1.2 In that test, `POST …/conversations/{A}/continue` and assert the run that appears is bound to **B**, proving the substitution rather than assuming it. Query `Run` by `conversation_id`, not by recency.
- [ ] 1.3 Assert the response today reports `started: true` with `conversation_id == A` and carries no field naming B. This is the assertion that must flip in section 3; write it so its failure message says which conversation actually started.
- [ ] 1.4 Run the new file and confirm it passes against unmodified code — a reproduction that does not pass first is not a reproduction.

## 2. Carry the started identity out of the scheduler

- [ ] 2.1 Add `started_conversation_id: Optional[str] = None` and `started_entry_ids: Tuple[str, ...] = ()` to `ScheduleResult` (`hub/hub/turn_scheduler.py:51-56`), with a docstring paragraph stating the same reason `TurnRefusal.entry_ids` gives at `:39-43` — the turn is built from the agent's whole queue, so the caller cannot infer which conversation ran.
- [ ] 2.2 Populate both on the success path only, from `conversation.id` and `[entry.id for entry in selected]`, at the construction site that returns the successful `ScheduleResult`. Do not touch `queued_entries`, `controlling`, the `selected` filter, `can_start`, or the hop-budget logic.
- [ ] 2.3 Add a test asserting every early-return `ScheduleResult` — running, empty queue, hop budget, no conversation, conversation unavailable, empty selection — still carries `started_conversation_id is None` and `started_entry_ids == ()`. Six branches, enumerated by name, so a seventh added later fails the count.
- [ ] 2.4 Confirm no other `schedule_agent` caller reads the new fields: the fourteen agent-addressed sites listed in design.md stay untouched.

## 3. Answer with what started

- [ ] 3.1 In `continue_conversation` (`hub/hub/api/v1/checkpoints.py:254-277`), add `started_conversation_id` to the returned dict, sourced from the `ScheduleResult`. Leave `agent`, `conversation_id`, `started` and `waiting_reason` exactly as they are.
- [ ] 3.2 Extend the route's docstring to say that the addressed conversation is echoed and the started one is reported separately, and why the two can differ.
- [ ] 3.3 Flip task 1.3's assertion to the required behaviour: `conversation_id == A`, `started_conversation_id == B`, `started: true`. Add the matching case where the addressed conversation *is* the one that starts and both fields are equal.
- [ ] 3.4 Add the nothing-started case: no eligible entry, `started: false`, `started_conversation_id is None`, `waiting_reason` set.

## 4. Tell the operator

- [ ] 4.1 Add `started_conversation_id?: string | null` to `ContinueResult` (`hub/ui/src/api/checkpoints.ts:90-95`).
- [ ] 4.2 Give `handleContinue` (`hub/ui/src/components/agents/AgentOutputPanel.tsx:742-756`) its third case: started and `started_conversation_id === currentConversationId` → `'Continuing…'`; started and different → a notice stating another conversation began, naming it; not started → the existing reason text.
- [ ] 4.3 Leave the `hasQueuedWork` button gate (`:337-340`, `:1064`) unchanged, and add a comment recording why it is not the fix — it reads client-side state that another conversation's older entry does not appear in.
- [ ] 4.4 Add or extend a UI test covering the three notices, keyed on the returned `started_conversation_id` rather than on rendering timing.

## 5. Reconcile the drive harness

- [ ] 5.1 Update `scripts/drive/t_continue_branches.py` — its F131 assertions are deliberately written in the direction the product currently behaves and will now fail. Rewrite them to the fixed direction and note in the file that the flip was the fix.
- [ ] 5.2 Re-check `scripts/drive/t_continue_burns_attempts.py`, `t_row15_cutover.py` and `t_sweep_conversations.py` for reads of the continue response, and update any that assume `conversation_id` describes what ran.

## 6. Verify and record

- [ ] 6.1 `py -3.11 -m pytest hub/tests/test_continue_starts_what_it_names.py -v` green, then the full `hub/tests/` suite; compare the failure list against the known F109 flake rather than assuming.
- [ ] 6.2 `py -3.11 -m ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`, `py -3.11 -m mypy src/`, and `cd hub/ui && npm run lint`.
- [ ] 6.3 `cd hub/ui && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`; commit `hub/ui/src` and `hub/hub/static/ui` together.
- [ ] 6.4 Drive it live against the 8010 trial Hub with a cheap runner: two conversations, the older entry on the one not addressed, press Continue, and confirm the response and the notice both name the conversation that ran. Nothing closes on the strength of the unit tests alone.
- [ ] 6.5 Mark F131 fixed in `scripts/drive/FINDINGS.md`, and record there the correction this change established — that F131's own reproduction is not reachable from the shipped UI, while the older-entry path is.
- [ ] 6.6 Sync the new `conversation-turn-start` capability into `openspec/specs/` and archive the change.
