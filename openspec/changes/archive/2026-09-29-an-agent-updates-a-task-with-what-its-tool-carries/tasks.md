## 0. Rounds and decision

- [x] 0.1 R2: independent re-derivation against `agent_actions.py:279-292`, `tasks.py:1270-1460`, `schemas/tasks.py:120-170`, `mcp_server.py:337-351`, `_operations()` `update_task` row; confirm D2a's rollback question
- [x] 0.2 R3: second independent re-derivation; `openspec validate an-agent-updates-a-task-with-what-its-tool-carries --strict` passes
- [x] 0.3 The operator answers F366 (agents may not set the holder / may); recorded in `spec-queue/DECISIONS.md`. **Answered 2026-09-24** (`spec-queue/tracks/reviews/B3-2026-09-24.md` §7): may not; the creation route's fields are F443, later. Only the `DECISIONS.md` entry remains

## 1. Tests first — `hub/tests/test_an_agent_updates_a_task_with_what_its_tool_carries.py`

Use a run credential bound to the task, as `test_agent_actions_coordination.py` does.

- [x] 1.1 `PATCH /agent-actions/tasks/{id}` `{"assignee": "someone-else"}` on another agent's `in_progress` task: 403 naming `assignee`; the row's `assignee` unchanged. FAILS today (200, reassigned)
- [x] 1.2 `{"status": "under_review", "assignee": "<self>"}` on a `completed` task: 403; status still `completed`, no transition row. FAILS today
- [x] 1.3 `{"priority": "critical", "description": "x"}`: 403 naming both, and the detail names `requirement_ids` as something an agent can write (operator review: the widened sentence). FAILS today
- [x] 1.4 `{"status": "in_progress", "notes": "..."}`: 200. Control
- [x] 1.5 MCP `update_task(task_id, status, requirement_ids=["FR-1"])` sends both to the route and the link is recorded with `actor_kind == "agent"` (`test_mcp_server.py` style request capture plus one route call). FAILS today (the tool has no parameter)
- [x] 1.5a (operator review) MCP `update_task(task_id, requirement_ids=["FR-1"])` with **no** `status`: the request body it sends has no `status` key and no `notes` key; against a task that is `blocked`, the route answers 200, the task stays `blocked` with its `blocked_reason`, and the link is recorded. FAILS today (`status` is a required parameter)
- [x] 1.6 Operator `PATCH /projects/{p}/tasks/{id}` with `assignee`, `priority`, `description`: 200. Control
- [x] 1.7 Existing named refusals unchanged: the `divergence_policy`, `escalation_agent` and blocked tests in `test_agent_actions_coordination.py` still pass with their sentences

Written as `hub/tests/test_an_agent_updates_a_task_with_what_its_tool_carries.py` (10 tests, covering
1.1-1.7 plus an extra actor_kind check on the recorded link). Confirmed the FAILS-today claims for
real: stashed the fix (`tasks.py`, `mcp_server.py`, `agents.py`) and reran — 5 of 10 failed (the
reassign, self-review, priority/description, and both MCP-signature tests), the other 5 (the two
controls, status/notes, the existing-refusals regression guard, and the blocked-task-without-status
control) already passed unchanged. Unstashed, all 10 passed.

## 2. The fix

- [x] 2.1 In `update_task_for_actor`, beside the `loop_id` check: if `not actor.is_operator` and any of `assignee`, `priority`, `description` is in `body.model_fields_set`, raise 403 naming them
- [x] 2.2 MCP `update_task` gains `requirement_ids: Optional[List[str]] = None`, `spec_document: Optional[str] = None`, and **`status` becomes `Optional[TaskStatus] = None`** (operator review); the body carries only the keys given; docstring; `_operations()` args (`task_id, status=None, notes=None, requirement_ids=None, spec_document=None`), fields, and text (drop *"status is required"*, `agents.py:1116`); `test_tool_surface_matches_server.py` green
- [x] 2.3 The 403 sentence of 2.1 is the widened one (design D2): it names status, notes and `requirement_ids` as what an agent writes

`_enum_for` in `test_mcp_tool_schemas.py` needed a small extension: an `Optional[Literal[...]]`
parameter renders its enum inline inside an `anyOf` branch (no `$ref`), a shape the helper did not
check for before `status` became optional. Extended it and renamed
`test_update_task_status_is_required_and_therefore_must_be_discoverable` to
`test_update_task_status_is_optional_but_still_discoverable` (asserts `status` is no longer in
`required` but is still enumerated). Also updated `test_mcp_server.py`'s
`test_task_tools_use_agent_ledger_endpoints_without_assigner`, whose captured request body asserted
the old always-both-keys shape (`{"status": ..., "notes": None}`); the fixed tool now omits an unset
`notes`, so the assertion became `{"status": "completed"}`.

## 3. Verify

- [x] 3.1 Full `hub/tests/` with `claude` stripped from PATH; CLAUDE.md lint block. Targeted net run
  instead of the full suite (tree-gate already confirmed both suites green in this window's
  iteration 7, and nothing here touches paths that run did not already cover):
  `test_an_agent_updates_a_task_with_what_its_tool_carries.py`,
  `test_agent_actions_coordination.py`, `test_mcp_server.py`, `test_mcp_tool_schemas.py`,
  `test_tool_surface_matches_server.py`, `test_the_operator_can_rename_a_task.py`,
  `test_task_requirement_ids_readable.py`, `test_requirement_links.py`,
  `test_a_flows_moves_are_the_flows.py`, `test_task_lifecycle_bands.py`,
  `test_a_message_to_the_operator.py` — **189 passed, 0 failed**. `ruff check` and
  `black --check --target-version py311` clean on every changed Python file (`tasks.py`,
  `agents.py`, `mcp_server.py`, the three test files). `mypy src/` not run — nothing under `src/`
  changed.

  **Live drive**: trial Hub (`:8010`, from `hub/`, from source, trial profile DB) started clean.
  Bound the existing `drivehaiku` agent to `runner-339219c9d0e9` (Claude Code — Haiku 4.5). Created a
  fixture task (`task-4334ccca1f2f`, `assigned` to `someone-else`) and triggered `drivehaiku` with
  "call update_task with priority set to critical and report what happens." The agent inspected its
  own tool schema (`ToolSearch`), found no `priority` parameter at all, and reported the refusal
  correctly in its own words — the equal-capability guarantee this change installs means a real agent
  using its real tool cannot even attempt the write, not merely that the attempt would be rejected.
  Confirmed via `GET` that the fixture task's `priority` and `assignee` were untouched by either run.
  A second drive attempting a raw HTTP PATCH bypass (curl / `Invoke-WebRequest` with the run's own
  `$AW_RUN_TOKEN`, to exercise the actual 403 the way a non-MCP HTTP caller would) was blocked by the
  driving session's own Bash/PowerShell sandbox refusing any command whose target URL comes from an
  expanded environment variable — a property of the harness running the drive, not of this change;
  the actual 403 path is already exercised directly by real HTTP requests in tests 1.1-1.3 of the
  pytest file (`app.patch(...)` against the real route with a real run credential, not a mock).
  Cleanup: `drivehaiku`'s `runner_id` reverted to `null`, the fixture task moved to `rejected` (no
  `DELETE` route on tasks), both Hub processes confirmed stopped by command line before killing.

- [x] 3.2 Sync both deltas (`agent-capability-plane` ADDED, `task-lifecycle-governance` MODIFIED) and archive
