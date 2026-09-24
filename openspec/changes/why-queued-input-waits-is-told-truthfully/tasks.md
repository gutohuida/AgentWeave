## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R1 (bundle B1, 2026-09-24): proposal, design, deltas, tasks, test guide; F361 and F289 re-verified by reading at `404c7d5`, F289's changed shape (F288 fixed 2026-09-23) recorded
- [x] 0.2 R2 (2026-09-24): done — design.md round log and Collisions. Original brief: re-derive against `hub/hub/api/v1/messages.py`, `agent_actions.py:201-224`, `schemas/messages.py`, `mcp_server.py:203-244` (and `ask_user`: D1's open check), `api/v1/inbound_queue.py:97-205`, `agent_trigger.py:960-1005`, `run_task_binding.resolve_bound_task`. Check that no consumer of `MessageResponse` (the UI's `api/messages.ts` and the SSE `message_created` payload, `_msg_dict`) breaks on two added optional fields
- [x] 0.3 R3 (2026-09-24): done — see design.md round log; `openspec validate why-queued-input-waits-is-told-truthfully --strict` passes
- [ ] 0.4 Operator approval (APPROVALS.md), including D2's departure from ROUNDS.md's sketch

## 1. Tests first — each fails on today's code unless marked as a control

New file `hub/tests/test_why_queued_input_waits_is_told_truthfully.py`.

- [ ] 1.1 (D1) An agent run at `turn_depth == hop_budget` posts `POST /agent-actions/messages` (bound run credential, as `test_agent_actions_coordination.py` stages it). The 201 body has `held_by_hop_budget: true` and a `delivery_note` containing the depth, the budget, and `continues the chain`; it does not contain `send it again`. FAILS today (no such fields)
- [ ] 1.2 (D1) Control: the same run at `turn_depth < hop_budget` → `held_by_hop_budget` is `null` or `false` and `delivery_note` is `null`. The body is otherwise identical to today's
- [ ] 1.3 (D1) `GET /messages?history=true` lists the held message with `held_by_hop_budget: null` (the list does not claim `false`)
- [ ] 1.4 (D1) `mcp_server.send_message` with `_hub_request` patched to return 1.1's body → the reply carries `held_by_hop_budget: True` and the note, and still `success: True` and `message_id`. With 1.2's body → exactly `{"success": True, "message_id": …}`. The first FAILS today
- [ ] 1.5 (D2) The held entry's `waiting_reason` is `None` after the send (pins D2, so a later "fix" that writes it has to change this test on purpose)
- [ ] 1.6 (D3, F289) `test_task_turn_collision.py`'s F97 staging, then end the holder's run **without** re-draining (patch the run-end re-drain out). `GET /queue/{challenger}/status` does not contain `is already running a turn`; it starts with `the last delivery attempt was refused:`. FAILS today (the stored sentence is returned bare)
- [ ] 1.7 (D3) Control: the F97 test (`test_task_turn_collision.py:495-550`) passes unchanged: holder still running → reason names the holder and the task
- [ ] 1.8 (D4) An entry with a stored non-D8 refusal (e.g. the review-commit sentence) and nothing live → reason is `the last delivery attempt was refused: <sentence>`. FAILS today
- [ ] 1.8b (D3, R2) The controlling entry is a **review** entry and a stored D8 sentence exists from an earlier work entry: the route does not run the holder check and answers D4's labelled fallback
- [ ] 1.9 (D3) `takes_task_workspace` patched to raise → the route answers 200 with D4's reason, not 500

## 2. Implementation

- [ ] 2.0 (R2) Precondition: B11's F133 shared turn-selection function exists (`controlling`, `selected`, `initiator` from entries, budget and cap). If it does not, stop: it lands first
- [ ] 2.1 (D1) `messages.py`: `create_message_for_actor` returns `(msg, held)`; one `held_note(...)` builder; both routes build `MessageResponse` with the two fields
- [ ] 2.2 (D1) `schemas/messages.py`: the two optional fields
- [ ] 2.3 (D1) `mcp_server.send_message`: add both keys when held. Read `.claude/rules/mcp-server.md` first; no import added
- [ ] 2.4 (D3) Move the D8 sentence into `checkout_held_sentence(holder, task_id)` (in `run_task_binding` or `worktrees`, whichever both callers already import without a cycle); `agent_trigger` uses it; `get_queue_status` adds the live check
- [ ] 2.5 (D4) The labelled fallback
- [ ] 2.6 Run the new file, `test_task_turn_collision.py`, `test_inbound_queue.py`, `test_agent_trigger.py`, `test_delivery_attempts.py`, `test_a_start_is_reported_to_its_own_input.py`, `test_hop_budget_bound.py` and every test naming `send_message` **with `claude` stripped from PATH**; then the CLAUDE.md lint block; then the full `hub/tests/`
