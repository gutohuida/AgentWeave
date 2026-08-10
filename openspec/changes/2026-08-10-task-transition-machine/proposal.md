## Why

A task's status is whatever the last writer said it was. `hub/hub/api/v1/tasks.py:183-184` applies
`task.status = body.status` with no check that the move is legal, who is asking, or what the task
was doing before — and `hub/hub/mcp_server.py:251` exposes that as `update_task(task_id, status)`
to every bound agent. **An agent can move its own work from `in_progress` straight to `approved` in
one tool call**, skipping `completed` and `under_review` entirely, and nothing in the record shows
that the author and the approver were the same run.

Nor can the record show it. `Task.updated_by_run_id` (`hub/hub/db/models.py:529`) is a single
mutable column, overwritten on every write at `hub/hub/api/v1/tasks.py:194`. The run that completed
a task and the run that approved it occupy the same field, so the second erases the first. This is
not a check that can be bolted onto the existing columns — the schema cannot express the question.

Now, because the roadmap
(`openspec/explorations/2026-08-10-specification-and-surface-program-roadmap.md`) puts the
completion gates of B3 and B4 *inside* this transition service. Built after them, the gates have
nowhere to land and get bolted to the same unconditional assignment. It is also the one part of
the retired coordinator change that is worth shipping entirely on its own: it needs no
specification format, no evidence model, and no model call.

## What Changes

- **A transition machine.** The eight statuses in `src/agentweave/constants.py:280` and
  `hub/hub/schemas/tasks.py:15` are today two flat lists with no notion of adjacency. A single
  declared map of legal moves replaces "any status to any status". An illegal move is refused with
  a typed error naming the current status and what is reachable from it.
- **An append-only transition record.** A new table stores one immutable row per accepted
  transition: task, from-status, to-status, the responsible run (nullable for operator action),
  the actor kind, and when. `Task.status` remains the materialised current value; the history
  stops being destroyed on write.
- **Author/reviewer separation.** A run that moved a task into `completed` cannot be the run that
  moves it to `approved`. The distinction is already available at both call sites —
  `hub/hub/api/v1/agent_actions.py:234` passes `actor.run_id`, `hub/hub/api/v1/tasks.py:214`
  passes `None` for the operator — so the rule reads the new history rather than inventing an
  identity concept.
- **Entry statuses at creation.** A codebase scan on 2026-08-10 found the machine could be walked
  around entirely: `hub/hub/api/v1/tasks.py:70` sets `status=body.status` on create, and
  `AgentTaskCreate.status` (`hub/hub/api/v1/agent_actions.py:71`) accepts any of the eight — so an
  agent over direct HTTP can create a task **already `approved`** and never make a transition at
  all. Creation is restricted to the entry statuses `pending` and `assigned`.
- **Equal capability on create, closed by narrowing.** MCP's `create_task`
  (`hub/hub/mcp_server.py:206`) does not expose `status` while direct HTTP does — an asymmetry the
  `agent-capability-plane` spec already forbids, since MCP must be "a thin adapter over that
  contract with the same operations". The entry-status rule resolves it by constraining HTTP rather
  than widening MCP.
- **The operator is not bound by the machine's review rules.** A human answering for the project
  may approve their own work; the record simply says an operator did it. Refusing that would make
  a single-operator project unusable.
- **A minimal operator status control.** The same scan found the task board is **read-only** —
  `useUpdateTask` exists in `hub/ui/src/api/tasks.ts:34` with **no callers**, and every button in
  `TasksBoard.tsx`/`TaskCard.tsx` is a filter or an expander. Without a control, the operator-only
  edges below would exist in the API and be unreachable in the product. `TaskCard` gains an action
  offering exactly the transitions legal for the operator from the task's current status.
- **BREAKING (agent-facing):** `update_task` calls that skip lifecycle stages, or that approve the
  caller's own work, begin failing. This is the point of the change. No external install base
  exists to protect (product direction, 2026-08-02).

## Capabilities

### New Capabilities

- `task-lifecycle-governance`: which status transitions are legal, who may perform them, how an
  illegal one is refused, and the durable append-only record of every accepted transition —
  including the author/reviewer separation that makes self-approval impossible for an agent.

### Modified Capabilities

- `agent-capability-plane`: the requirement *"Every agent-caused effect retains run attribution"*
  currently asserts only that a record *"identifies the run responsible for that update"* — a
  guarantee the single mutable column satisfies while losing every prior run. Strengthened for
  task status: attribution becomes an append-only sequence rather than a last-writer field, so a
  completed-then-approved task names both runs.

## Impact

**Schema.** One new table and its migration (head is currently `0051_add_queue_entry_spec_document`).
Per `CLAUDE.md`, the migration must guard for a missing table, and the head assertions in
`hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py` must be bumped.

**Backend.** `hub/hub/api/v1/tasks.py` (`update_task_for_actor`, the single choke point both call
paths already share), a new transition-service module, `hub/hub/db/models.py`, and the task
schemas. `hub/hub/mcp_server.py` needs the new typed failure to survive the adapter without being
converted into a success — it is spawned standalone and may import only stdlib + fastmcp, so
anything it restates needs its agreement test.

**Status lists.** `src/agentweave/constants.py:280` and `hub/hub/schemas/tasks.py:15` declare the
same eight statuses independently. The transition map should not become a third copy.

**UI.** One slice only: a status action on `hub/ui/src/components/tasks/TaskCard.tsx`, wired to the
already-written and currently-unused `useUpdateTask`. How the board *renders* lifecycle and
transition history remains Program A/B5.

**Not touched.** No spec format, no evidence model, no AI.

## Non-Goals

- **Evidence and completion gates.** Whether a task has *earned* `completed` is B3/B4. This change
  builds the service those gates plug into and takes no position on their content.
- **Requirement traceability.** `Task.requirements` stays the JSON column it is today; replacing it
  with task↔requirement links is B3.
- **Rendering.** No task-board or timeline surface for the new history. The operator status control
  is a control, not a history view.
- **Assignment governance.** Any actor can currently set `assignee` on any task through
  `TaskUpdate`, and nothing checks entitlement. Recorded as a known gap, deliberately excluded:
  meaningful assignment rules need the run→task binding explored in
  `openspec/explorations/2026-08-10-enforcing-the-development-cycle.md`, and belong with it.
- **The CLI's second task store.** `src/agentweave/task.py` is a file-based store with its own
  `TaskStatus` and a `complete()` that forces `status="completed"`. It is unreachable from the Hub
  and has no functional consumer — only the public re-export at `src/agentweave/__init__.py:25` and
  `tests/test_task.py` — but it ships in the published package and contradicts this model.
  Investigating and most likely deleting it is its own change (operator decision, 2026-08-10).
- **Task deletion.** There is no DELETE route (`hub/hub/api/v1/tasks.py`), so a task created in
  error is permanent and `rejected` is its only disposal route. Noted, not addressed.
- **Reworking run identity.** `AgentActor` and run-bound authentication are used as they stand.
- **Retrofitting history for existing tasks.** Tasks predating the change begin their recorded
  history at their next transition; the migration invents no rows it cannot know.
- **Operator restrictions.** The machine constrains agents. Operator moves are recorded, and
  validated for legality, but not subject to author/reviewer separation.
