# Proposal — an agent updates a task with what its tool carries

**Round 1, 2026-09-24** (bundle B3, decision D10, F366). Finding **F366 (C)**, re-verified on HEAD
`404c7d5`. **Nothing here is implemented yet.**

## Why

The agent plane's task update, `PATCH /api/v1/agent-actions/tasks/{id}`
(`hub/hub/api/v1/agent_actions.py:279-292`), takes the **operator's** `TaskUpdate`
(`hub/hub/schemas/tasks.py:120-151`) and hands it to `update_task_for_actor` with a run actor. The MCP
`update_task` tool — a thin adapter over that route — carries only `status` and `notes`
(`hub/hub/mcp_server.py:337-351`), and the tool surface tells HTTP-path agents the same two fields
(`_operations()`, `agents.py:1110-1117`).

So an agent reaching the route directly can write fields its tool never offers:

| field | refused for an agent today? | where |
|---|---|---|
| `assignee` | **no** — written for any actor | `tasks.py:1301-1318` |
| `priority`, `description` | **no** | `tasks.py:1408-1411` |
| `requirement_ids`, `spec_document` | **no** — and the link records `kind="agent"`, so this path was designed for agents | `tasks.py:1430-1446` |
| `divergence_policy`, `escalation_agent` | yes, 403 | `tasks.py:1414-1424` |
| `blocked_reason` (with `status: blocked`) | yes, 403 naming `ask_user` | `tasks.py:1319-1340` |
| `loop_id` | yes, 403 for everyone | `tasks.py:1286-1295` |

The costly one is `assignee`: an agent can unassign another agent's work, or name itself on a finished
task in the same request that moves it to `under_review` (F366). `agent-capability-plane` requires the
two access paths to have **equal capability** — *"HTTP and MCP access have equal capability"*, whose
last paragraph calls a rule held by one path and not the other *"a defect rather than a division of
labour"*.

## What Changes

- **Operator-only on the agent plane:** `assignee`, `priority`, `description` join `divergence_policy`
  and `escalation_agent`. A run actor naming any of them is refused **403 before anything is written**,
  with one sentence naming the fields and what an agent can do instead (*"An agent moves its task with
  status and notes, and links it to the requirements it serves with requirement_ids; who holds a
  task, its priority and its description are the operator's."*).
- **Given to the tool instead of taken from the route:** `requirement_ids` and `spec_document` are added
  to MCP `update_task` and to its `_operations()` row, because the route already records an agent's
  link as the agent's and linking work to requirements is agent work. The tool's `status` becomes
  optional, so linking needs no status restatement (operator review 2026-09-24).
- `task-lifecycle-governance`'s paragraph saying the agents' route accepts an assignee, and its
  same-request reviewer scenario, are restated for the operator only (MODIFIED delta).
- Not in scope: the fields an agent sets when it **creates** a task (F443, operator 2026-09-24).
- The existing refusals keep their own sentences.

## Capabilities

### Modified Capabilities

- `agent-capability-plane` — adds a requirement stating which task fields an agent may write.
- `task-lifecycle-governance` — the author-as-holder requirement no longer says the agents' route
  accepts an assignee; naming a reviewer in the same request is the operator's.

## Impact

Backend only: `tasks.py` (`update_task_for_actor`), `mcp_server.py`, `agents.py` (`_operations`). No
migration, no UI. No existing test sends `assignee`, `priority` or `description` through the agent
plane (`grep` of `hub/tests` for `agent-actions/tasks` PATCH bodies).
