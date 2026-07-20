---
name: aw-spec-apply
description: Implement tasks from an approved HTML specification (spec.html). Enforces a hard approval gate — refuses to run unless the spec is marked approved — reads tasks from the HTML, and tracks completion by toggling task state inside spec.html.
---

Implement tasks from a change's **approved** specification. The authoritative artifact is
a single self-contained `spec.html` (it replaced the old markdown artifacts). Treat it as
the source of truth during implementation.

**Project:** {project_name}
**Mode:** {mode}
**Principal:** {principal}
**Agents:** {agents_list}

**Machine-readable contract:** the metadata and task attributes this skill parses are
defined in `html-spec-conventions.md` (bundled beside this skill). Read it if you are
unsure how to locate the approval status or a task's state.

---

## Steps

### 1. Select the change

If $ARGUMENTS specifies a change name, use it. Otherwise:
- Scan `spec/changes/` for active changes (directories with a `spec.html`, not under `archive/`)
- Auto-select if only one exists
- If multiple exist, list them and use **AskUserQuestion** to let the user choose

Announce: "Applying change: `<name>`"

### 2. Enforce the approval gate (HARD — do this before anything else)

Read `spec/changes/<name>/spec.html` and inspect the approval metadata:

```bash
grep -o 'name="aw-spec-status" content="[^"]*"' spec/changes/<name>/spec.html
```

- If `aw-spec-status` is **not** `approved`, **STOP**. Do not implement anything. Report:
  ```
  ## Blocked: spec not approved

  spec/changes/<name>/spec.html has status "<status>".
  Implementation is blocked until the user approves the specification.

  Run /aw-spec-propose to review and approve it, then re-run /aw-spec-apply.
  ```
  Do not offer to override, and do not flip the status yourself. Approval is the user's decision.
- Only if `aw-spec-status="approved"` may you continue.

### 3. Read context and quality config

From `spec.html`, read the full spec: Summary, Requirements (`FR-*`), Acceptance Criteria,
Behavior/Algorithms, Design (approach, decisions, security), Team, and the Tasks section
with each task's `data-task-id`, `data-status`, `data-role`, `data-agent`, and
`data-requirements`.

If the Design section references discovery inputs in `spec/discovery/<name>/`, use them
only as supporting context — the approved `spec.html` wins on any conflict.

Read quality settings from `agentweave.yml` `quality:` (if present): `review_required`,
`docs_threshold`, `docs_path`, `echo_chamber_guard`. Display them alongside progress so
they stay visible.

### 4. Show current state

Count tasks from `spec.html` (`li.task` elements) and show progress:

```
## Change: <name>   (status: approved)

Progress: N/M tasks complete
Quality: review_required=<...> | docs_threshold=<...> | docs_path=<...>

### Remaining Tasks
#### <Role> — <Agent>
- [ ] (T3) Task description   → satisfies FR-2
- [ ] (T4) Task description   → satisfies FR-5
```

If all tasks already have `data-status="done"`, congratulate and suggest `/aw-spec-archive`.

### 5. Identify tasks for this agent

The principal for this session is **{principal}**. Focus first on tasks whose
`data-agent="{principal}"` (or unassigned tasks matching {principal}'s roles).

Tasks assigned to other agents (`{agents_list}`) are candidates for delegation, not for
implementation here.

### 6. Implement tasks

For each pending task (`data-status="pending"`) owned by `{principal}`:

1. Announce: "Working on: (Tn) [description] — satisfies [requirement IDs]"
2. **Write tests first** (TDD) — write the test spec for the acceptance criteria this
   task's requirements demand, before implementing.
3. Implement the change — minimal and scoped to this task and its requirement IDs.
4. **Produce a decision doc before marking complete** (if `docs_threshold` applies):
   - Resolve path `<docs_path>/<task-id>.md` or `.agentweave/code-docs/<task-id>.md`
   - Use the `code_decision.md` template; fill `requirement` from the task's requirement
     IDs and description; list modified and AI-generated files.
   - Do not mark complete until the doc exists.
5. **Mark the task done inside `spec.html`** — for this task's `<li class="task">`:
   - set `data-status="done"`
   - check its checkbox (`<input type="checkbox" disabled>` → add `checked`)
   Then update the `.progress` element: bump `data-done` and the visible "N / M tasks complete".
6. Announce: "Done: (Tn) [description]"
7. Continue to the next task.

**Pause if:**
- A task is ambiguous or its requirement is unclear → ask before proceeding.
- Implementation reveals a spec issue → suggest updating `spec.html` (Design/Requirements),
  get confirmation, then continue. If a change is material, note it may warrant re-approval.
- Error or blocker → report clearly and wait.
- The user interrupts.

### 7. Delegate tasks to other agents (optional)

After finishing `{principal}`'s tasks, check for pending tasks owned by other agents
(`{agents_list}`). If any exist and the session is active, ask:
> "Tasks remain for [other agents]. Delegate them now?"

If yes, for each agent with pending tasks:
```bash
agentweave quick --to <agent> "Continue spec change '<name>'. Run /aw-spec-apply to work on your tasks. Spec is at spec/changes/<name>/spec.html (approved).
Quality: docs_threshold=<value> | review_required=<true/false> | docs_path=<path>"
```

Report which agents were notified and how many tasks each has.

### 8. Final status

```
## Apply Session Complete

**Change:** <name>   (status: approved)
**Progress:** N/M tasks complete

### Completed This Session
- [x] (T1) ...
- [x] (T2) ...

### Delegated
- <agent-b>: 3 tasks (frontend_dev)

### Remaining (this agent)
- (none) / [list blocked tasks]

Run /aw-spec-archive when all tasks across all agents are done.
```

---

## Guardrails

- **Never implement unless `aw-spec-status="approved"`.** The gate is hard.
- Never flip the approval status yourself — approval is the user's decision in `/aw-spec-propose`.
- Read the whole `spec.html` before starting; treat it as authoritative over discovery notes.
- Only implement tasks — the only edits to `spec.html` are toggling task `data-status`/checkbox
  and the progress counter, or a confirmed spec fix.
- Keep code changes minimal and scoped to each task and its requirement IDs.
- Update task state in `spec.html` immediately after each task completes.
- Pause on errors, blockers, or unclear requirements — don't guess.
- Delegate to other agents only with explicit user confirmation.
