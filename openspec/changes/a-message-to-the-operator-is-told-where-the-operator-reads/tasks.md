## 0. Rounds and decision

- [x] 0.1 R2: independent re-derivation against `messages.py:40-140`, `worktrees.py:70-150`, `mcp_server.py:204-244`, the `_operations()` `send_message` row (`agents.py:1029`), and a `grep -rn "unasked" hub/ src/` confirming nothing implements the two removed requirements
- [ ] 0.2 R3: second independent re-derivation; `openspec validate a-message-to-the-operator-is-told-where-the-operator-reads --strict` passes
- [ ] 0.3 The operator answers F77 (refusal only / a `notify_operator` tool later) and whether the REMOVED half ships here; recorded in `spec-queue/DECISIONS.md`

## 1. Tests first — `hub/tests/test_a_message_to_the_operator.py`

- [ ] 1.1 Through the agent plane with a run credential, `POST /api/v1/agent-actions/messages` to `Operator`, `operator` and `USER`: 404; the detail contains `not a message recipient`, `update_task` and `ask_user`; no `InboundQueueEntry` and no `Message` row. FAILS today (detail is `Unknown recipient …`)
- [ ] 1.2 Control: to `ghost` still answers `Unknown recipient 'ghost'`. PASSES today and must keep passing
- [ ] 1.3 The `agent_action_rejected` event carries `reason == "operator_not_a_recipient"`. FAILS today
- [ ] 1.4 `test_tool_surface_matches_server.py` stays green after the docstring and `_operations()` edit

## 2. The fix

- [ ] 2.1 `worktrees.is_reserved_agent_name`; the branch in `messages.py` before the recipient lookup
- [ ] 2.2 `send_message` docstring (`mcp_server.py:213-230`) and `_operations()` text

## 3. Spec reconciliation

- [ ] 3.1 Sync: add the requirement and remove the two retired ones from `openspec/specs/agent-capability-plane/spec.md`; archive

## 4. Verify

- [ ] 4.1 Full `hub/tests/` with `claude` stripped from PATH; CLAUDE.md lint block
- [ ] 4.2 Trial Hub, one Haiku agent told "tell the operator the result via send_message": record the tool error verbatim and what the agent did next
