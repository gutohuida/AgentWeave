---
name: aw-spec-apply
description: Implement tasks from a spec change. Shows progress grouped by agent/role, works through tasks one by one, and optionally delegates remaining tasks to other agents via AgentWeave.
---

Implement tasks from a spec change.

**Project:** {project_name}
**Mode:** {mode}
**Principal:** {principal}
**Agents:** {agents_list}

---

## Steps

### 1. Select the change

If $ARGUMENTS specifies a change name, use it. Otherwise:
- Scan `spec/changes/` for active changes (not in `archive/`)
- Auto-select if only one exists
- If multiple exist, list them and use **AskUserQuestion** to let the user choose

Announce: "Applying change: `<name>`"

### 2. Read context and quality config

Read all spec artifacts:
1. `spec/changes/<name>/proposal.md` — understand the goal and involved agents
2. `spec/changes/<name>/design.md` — understand the architecture and role ownership
3. `spec/changes/<name>/tasks.md` — get the task list with role assignments

Read quality settings from `agentweave.yml` `quality:` section (if present):
- `review_required`, `docs_threshold`, `docs_path`, `echo_chamber_guard`

Display the active quality settings alongside the progress summary so they are visible throughout implementation.

### 3. Show current state

Display a progress summary:

```
## Change: <name>

Progress: N/M tasks complete

### Remaining Tasks

#### <Role> — <Agent>
- [ ] Task A
- [ ] Task B

#### <Role> — <Agent>
- [ ] Task C
```

If all tasks are complete, congratulate and suggest `/aw-spec-archive`.

### 4. Identify tasks for this agent

The principal agent for this session is **{principal}**. Focus on tasks assigned to `{principal}` first.

Check if any tasks are assigned to other agents (`{agents_list}`). If so, note them separately — those will be delegated, not implemented here.

### 5. Implement tasks

For each pending task assigned to `{principal}`:

1. Announce: "Working on: [task description]"
2. **Write tests first** (TDD) — before implementing, write the test spec for what this task must do
3. Implement the change — keep it minimal and scoped to this task
4. **Produce decision doc before marking complete** (if `docs_threshold` applies to this task):
   - Resolve path: `<docs_path>/<task-id>.md` or `.agentweave/code-docs/<task-id>.md`
   - Use the `code_decision.md` template — fill in `requirement` from the task description, list modified files and AI-generated files
   - Do not mark the task complete until the doc exists
5. Mark complete in `tasks.md`: `- [ ]` → `- [x]`
6. Update the progress counter in the `## Progress` line
7. Announce: "Done: [task description]"
8. Continue to the next task

**Pause if:**
- Task is ambiguous → ask for clarification before proceeding
- Implementation reveals a design issue → suggest updating `design.md`, then continue
- Error or blocker → report clearly and wait for guidance
- User interrupts

### 6. Delegate tasks to other agents (optional)

After finishing tasks for `{principal}`, check if unfinished tasks exist for other agents (`{agents_list}`).

If other agents have tasks and the session is active, ask:
> "Tasks remain for [other agents]. Delegate them now?"

If yes, for each agent with pending tasks:
```bash
agentweave quick --to <agent> "Continue spec change '<name>'. Run /aw-spec-apply to work on your tasks. Spec is at spec/changes/<name>/
Quality: docs_threshold=<value> | review_required=<true/false> | docs_path=<path>"
```

Include the active quality settings so the receiving agent knows what is expected of them.

Report: which agents were notified and how many tasks each has.

### 7. Final status

```
## Apply Session Complete

**Change:** <name>
**Progress:** N/M tasks complete

### Completed This Session
- [x] Task 1
- [x] Task 2

### Delegated
- <agent-b>: 3 tasks (frontend_dev)
- <agent-c>: 2 tasks (qa_engineer)

### Remaining (this agent)
- (none) / [list if any blocked tasks remain]

All your tasks complete! Other agents have been notified.
Run /aw-spec-archive when all tasks across all agents are done.
```

---

## Guardrails

- Read all context files before starting implementation
- Only implement tasks — do not change artifacts unless updating a task checkbox or fixing a design issue discovered during implementation
- Keep code changes minimal and scoped to each task
- Update the task checkbox immediately after completing each task
- Update the `## Progress` counter in `tasks.md` as you go
- Pause on errors, blockers, or unclear requirements — don't guess
- Delegate to other agents only with explicit user confirmation
