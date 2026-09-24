## 0. Rounds and decision

- [x] 0.1 R2: independent re-derivation against `agent_actions.py:279-292`, `tasks.py:1270-1460`, `schemas/tasks.py:120-170`, `mcp_server.py:337-351`, `_operations()` `update_task` row; confirm D2a's rollback question
- [ ] 0.2 R3: second independent re-derivation; `openspec validate an-agent-updates-a-task-with-what-its-tool-carries --strict` passes
- [ ] 0.3 The operator answers F366 (agents may not set the holder / may); recorded in `spec-queue/DECISIONS.md`

## 1. Tests first — `hub/tests/test_an_agent_updates_a_task_with_what_its_tool_carries.py`

Use a run credential bound to the task, as `test_agent_actions_coordination.py` does.

- [ ] 1.1 `PATCH /agent-actions/tasks/{id}` `{"assignee": "someone-else"}` on another agent's `in_progress` task: 403 naming `assignee`; the row's `assignee` unchanged. FAILS today (200, reassigned)
- [ ] 1.2 `{"status": "under_review", "assignee": "<self>"}` on a `completed` task: 403; status still `completed`, no transition row. FAILS today
- [ ] 1.3 `{"priority": "critical", "description": "x"}`: 403 naming both. FAILS today
- [ ] 1.4 `{"status": "in_progress", "notes": "..."}`: 200. Control
- [ ] 1.5 MCP `update_task(task_id, status, requirement_ids=["FR-1"])` sends both to the route and the link is recorded with `actor_kind == "agent"` (`test_mcp_server.py` style request capture plus one route call). FAILS today (the tool has no parameter)
- [ ] 1.6 Operator `PATCH /projects/{p}/tasks/{id}` with `assignee`, `priority`, `description`: 200. Control
- [ ] 1.7 Existing named refusals unchanged: the `divergence_policy`, `escalation_agent` and blocked tests in `test_agent_actions_coordination.py` still pass with their sentences

## 2. The fix

- [ ] 2.1 In `update_task_for_actor`, beside the `loop_id` check: if `not actor.is_operator` and any of `assignee`, `priority`, `description` is in `body.model_fields_set`, raise 403 naming them
- [ ] 2.2 MCP `update_task` gains `requirement_ids: Optional[List[str]] = None`, `spec_document: Optional[str] = None`, sent only when given; docstring; `_operations()` args/fields; `test_tool_surface_matches_server.py` green

## 3. Verify

- [ ] 3.1 Full `hub/tests/` with `claude` stripped from PATH; CLAUDE.md lint block
- [ ] 3.2 Sync the delta and archive
