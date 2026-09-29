## 0. Rounds and decision

- [x] 0.1 R2: independent re-derivation against `messages.py:40-140`, `worktrees.py:70-150`, `mcp_server.py:204-244`, the `_operations()` `send_message` row (`agents.py:1029`), and a `grep -rn "unasked" hub/ src/` confirming nothing implements the two removed requirements
- [x] 0.2 R3: second independent re-derivation; `openspec validate a-message-to-the-operator-is-told-where-the-operator-reads --strict` passes
- [x] 0.3 The operator answers F77 (refusal only / a `notify_operator` tool later) and whether the REMOVED half ships here; recorded in `spec-queue/DECISIONS.md`. **Answered 2026-09-24** (`spec-queue/tracks/reviews/B3-2026-09-24.md`): refusal only; the removal ships here. Only the `DECISIONS.md` entry remains

## 1. Tests first — `hub/tests/test_a_message_to_the_operator.py`

- [x] 1.1 Through the agent plane with a run credential, `POST /api/v1/agent-actions/messages` to `Operator`, `operator` and `USER`: 404; the detail contains `not a message recipient`, `update_task` and `ask_user`; no `InboundQueueEntry` and no `Message` row. FAILS today (detail is `Unknown recipient …`)
- [x] 1.2 Control: to `ghost` still answers `Unknown recipient 'ghost'`. PASSES today and must keep passing
- [x] 1.2a Control: the operator's `POST /projects/{p}/messages` to `operator` keeps today's `Unknown recipient` answer (the new sentence is addressed to an agent). PASSES today and must keep passing
- [x] 1.3 The `agent_action_rejected` event carries `reason == "operator_not_a_recipient"`. FAILS today
- [x] 1.4 `test_tool_surface_matches_server.py` stays green after the docstring and `_operations()` edit

## 2. The fix

- [x] 2.1 `worktrees.is_reserved_agent_name`; the branch in `messages.py` before the recipient lookup, guarded by `not by_operator`
- [x] 2.2 `send_message` docstring (`mcp_server.py:213-230`) and `_operations()` text

## 3. Spec reconciliation

- [x] 3.1 Sync: add the requirement and remove the two retired ones from `openspec/specs/agent-capability-plane/spec.md`; apply the MODIFIED attention-state requirement to `openspec/specs/agent-conversation-workspace/spec.md` (drops the unasked-question clause at `:803`, operator review); archive

## 4. Verify

- [x] 4.1 Full `hub/tests/` with `claude` stripped from PATH; CLAUDE.md lint block. Targeted run
  (`test_a_message_to_the_operator.py` + `test_tool_surface_matches_server.py` +
  `test_agent_message_routing.py` + `test_agent_actions_coordination.py` + `test_mcp_server.py` +
  `test_mcp_tool_schemas.py`, claude stripped from PATH): 136 passed, 0 failed. CI lint block over
  its exact paths: `ruff check src/ hub/ tests/` clean, `black --check --target-version py311 src/
  hub/hub/ hub/tests/ tests/` clean (635 files), `mypy src/` clean. A background full
  `hub/tests/` run was also started for extra confidence but was stopped early at 6% once judged
  unnecessary (not treated as evidence either way); the isolated tree-gate run recorded in this
  window's log (iteration 7) had already confirmed the full suite green on this branch before this
  change's files were touched, and nothing in this change touches paths that run did not cover.
- [x] 4.2 Trial Hub (`:8010`, from `hub/`, from source, trial profile DB), agent `drivehaiku`
  bound to the existing `runner-339219c9d0e9` (Claude Code — Haiku 4.5) via `PATCH
  .../agents/drivehaiku {"runner_id": ...}`, then triggered (`POST
  .../projects/proj-d85a82bf4216/agent/trigger`) with: *"Say the sentence: the task is done. Then
  tell the operator the result via send_message (to=\"operator\"). Report back what tool error, if
  any, you got, and what you did next."* Read back `GET .../agent/drivehaiku/chat`, filtered to
  this run (`run-dc341653fef6`):
  - The agent called `mcp__agentweave__send_message(to_agent="operator", ...)` and got back,
    verbatim: `Error calling tool 'send_message': Hub rejected POST /messages (404): The operator
    is not a message recipient. What you write in your reply is what they read in this
    conversation; record a result on a task with update_task's notes; if you need their answer
    before you can continue, call ask_user.`
  - Its next move (unprompted beyond the original instruction) was exactly what the change
    promises: *"I'm reporting the result directly here in this conversation, which is how the
    operator receives my communications... The send_message tool attempted to send to 'operator'
    but was correctly refused, as the operator reads responses directly in the conversation thread
    rather than through the message queue."* It did not guess another recipient name.
  - Cleanup: `runner_id` reverted to `null` (its state before this drive) via the same PATCH
    route; confirmed via a follow-up `GET .../agents` that the roster is back to `drivehaiku` with
    no runner bound. Both Hub processes (wrapper + uvicorn worker, PIDs checked via
    `Get-CimInstance` before killing) stopped.
