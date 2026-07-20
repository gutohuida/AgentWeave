# AW-Spec Workflow

The AW-Spec workflow provides a structured way to move from an unclear idea to coordinated implementation through five stages: **explore**, **technical explore**, **propose**, **apply**, and **archive**.

## Overview

```text
┌────────────┐    ┌────────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Explore   │───▶│ Technical  │───▶│ Propose  │───▶│  Apply   │───▶│ Archive  │
│   What     │    │ Explore How│    │ Formalize│    │  Build   │    │ Finish   │
└────────────┘    └────────────┘    └──────────┘    └──────────┘    └──────────┘
```

| Stage | Purpose | Skill | Output |
|-------|---------|-------|--------|
| **Explore** | Investigate the idea, problem, workflows, requirements, and risks | `/aw-spec-explore` | Understanding, optional `idea.md` |
| **Technical Explore** | Investigate architecture, stack, deployment, testing, sequencing, and agent plan | `/aw-spec-technical-explore` | Technical direction, optional `technical.md` |
| **Propose** | Create the authoritative, approval-gated specification | `/aw-spec-propose` | `spec.html` (single self-contained doc) |
| **Apply** | Implement the planned changes (only after approval) | `/aw-spec-apply` | Working code |
| **Archive** | Finalize and store completed work | `/aw-spec-archive` | Archived change |

Both exploration stages are optional, but they are useful when the scope is unclear, the implementation is complex, or multiple agents will work on the change.

The Propose stage produces a single authoritative **`spec.html`** — a self-contained HTML
specification that **replaces** the older markdown artifacts (`proposal.md`, `design.md`,
`tasks.md`, `team.md`). It follows spec-driven-development best practices (testable
requirements with IDs, producer/consumer conformance split, Given/When/Then acceptance
criteria, numbered algorithms, explicit non-goals, task→requirement traceability) and
must be **explicitly approved by the user** before implementation begins. See
[`html-spec-conventions.md`](../../src/agentweave/templates/skills/references/html-spec-conventions.md)
for the authoring conventions and the machine-readable metadata contract.

## Prerequisites

The AW-Spec workflow skills are available as Claude Code and Codex skills when you run `agentweave init`. They are generated into `.claude/skills/` and `.agents/skills/`.

## Stage 1: Explore What

Use idea exploration when you want to think through what to build before planning how to build it.

```bash
# Start exploring an idea
/aw-spec-explore

# Or explore a specific topic
/aw-spec-explore "add-user-authentication"
```

What explore mode focuses on:

- The problem or opportunity
- Affected users and workflows
- Requirements that are starting to emerge
- Goals and non-goals
- Product or behavior options
- Risks and unknowns
- Relevant codebase areas

Explore mode is for thinking, not implementation. It should not start by planning agents, roles, frameworks, deployment, or test ownership unless the user explicitly asks.

When useful, capture notes at:

```text
spec/discovery/<name>/idea.md
```

## Stage 2: Explore How

Use technical exploration after the idea is clear enough to discuss implementation strategy.

```bash
/aw-spec-technical-explore "add-user-authentication"
```

Technical exploration focuses on:

- Existing architecture and integration points
- Current technologies and framework constraints
- New technology or dependency decisions, if needed
- Deployment and operational impact
- Test strategy and test timing
- Implementation sequencing
- AgentWeave agent and role ownership
- Review, documentation, and quality gates

For existing projects, technical exploration should reuse the stack, framework, deployment model, and test patterns already present unless there is a strong reason to change them.

For new projects or greenfield areas, technical exploration helps compare stack, persistence, deployment, CI, and test options.

When useful, capture notes at:

```text
spec/discovery/<name>/technical.md
```

## Stage 3: Propose

Once the idea and technical path are clear, generate the authoritative specification.

```bash
/aw-spec-propose "add-user-authentication"
```

If discovery notes exist, `aw-spec-propose` uses them as source context:

```text
spec/discovery/<name>/idea.md
spec/discovery/<name>/technical.md
```

If discovery notes do not exist, propose still works from the user's request.

This creates a change directory at `spec/changes/<name>/` containing a single
self-contained **`spec.html`**:

| Section | Purpose |
|---------|---------|
| Summary / Problem | What and why: business case and motivation |
| Scope & Non-Goals | Explicit in-scope and out-of-scope items |
| Conformance | Producer (allowed inputs) vs. consumer (required behavior) |
| Requirements | Testable `FR-00x` assertions (MUST/SHOULD/MAY) |
| Acceptance Criteria | Given/When/Then, linked to requirement IDs |
| Behavior / Algorithms | Numbered steps for multi-step/conditional behavior |
| Design | How: approach, architecture, decisions, security |
| Team & Ownership | Recommended roles, current-session gaps |
| Tasks | Implementation checklist, each traced to requirement IDs |
| Open Questions | `[NEEDS CLARIFICATION]` markers (must be empty to approve) |
| Approval | Approval status, approver, and date |

Task completion state and the approval status live **inside** `spec.html` as
machine-readable metadata (`aw-spec-status`) and per-task `data-status` attributes.

### Approval Gate

`spec.html` starts as `draft`. Propose ends by asking the user to **approve** the
specification. Only on explicit approval does its status flip to `approved`. Implementation
(`/aw-spec-apply`) is **blocked** until the spec is approved.

### Change Directory Structure

```text
spec/
└── changes/
    └── add-user-authentication/
        └── spec.html
```

## Stage 4: Apply

Implement the tasks from your **approved** specification.

```bash
# Apply the current change
/aw-spec-apply

# Apply a specific change
/aw-spec-apply "add-user-authentication"
```

The apply stage:

1. **Enforces the approval gate** — refuses to run unless `spec.html` has
   `aw-spec-status="approved"`
2. Reads the authoritative `spec.html` (requirements, design, tasks)
3. Shows progress, such as `3/7 tasks complete`
4. Works through each pending task (TDD: tests first), scoped to its requirement IDs
5. Marks tasks complete **inside `spec.html`** by flipping each task's `data-status` to
   `done` and checking its checkbox, then updating the progress counter
6. Delegates work to matching agents when appropriate and confirmed by the user

Earlier discovery notes are supporting context. The approved `spec.html` is the source of
truth during implementation.

### Agent Delegation

Each task in `spec.html` carries role and agent ownership as data attributes:

```html
<li class="task" data-task-id="T1" data-status="pending"
    data-role="backend_dev" data-agent="claude" data-requirements="FR-1">
  <input type="checkbox" disabled>
  <span class="task-desc">Create the token-refresh endpoint.</span>
</li>
```

When applying changes with role ownership, tasks can be delegated to matching agents in
your session.

## Stage 5: Archive

When all tasks are complete, archive the change to keep your workspace clean.

```bash
# Archive the current change
/aw-spec-archive

# Archive a specific change
/aw-spec-archive "add-user-authentication"
```

Archiving:

1. Verifies the spec was approved (`aw-spec-status="approved"`)
2. Verifies every task in `spec.html` has `data-status="done"`
3. Optionally syncs delta specs to the main spec library
4. Moves the change (including `spec.html`) to `spec/changes/archive/YYYY-MM-DD-<name>/`

## Workflow Integration

### From Idea to Implementation

```text
User: "I want to add user authentication"

1. /aw-spec-explore "add-user-authentication"
   -> Understand auth goals, user flows, non-goals, and risks
   -> Optionally capture spec/discovery/add-user-authentication/idea.md

2. /aw-spec-technical-explore "add-user-authentication"
   -> Inspect current auth, API, UI, storage, tests, deployment, and agents
   -> Optionally capture spec/discovery/add-user-authentication/technical.md

3. /aw-spec-propose "add-user-authentication"
   -> Generates the authoritative spec/changes/add-user-authentication/spec.html
   -> Uses discovery notes if present
   -> Ends by asking the user to APPROVE the spec (status: draft -> approved)

4. /aw-spec-apply
   -> Blocked until the spec is approved
   -> Implements tasks one by one or delegates them
   -> Marks tasks complete inside spec.html (data-status="done")

5. /aw-spec-archive
   -> Verifies approval + all tasks done, then moves the change to archive
```

### Lightweight Path

For small changes, you can skip exploration and propose directly:

```bash
/aw-spec-propose "fix-status-output"
/aw-spec-apply
/aw-spec-archive
```

The exploration stages are tools for reducing ambiguity, not mandatory gates.

### Fluid Workflow

The AW-Spec workflow is not strictly linear. You can:

- Return to idea exploration if implementation reveals product ambiguity
- Return to technical exploration if implementation reveals architectural complexity
- Update artifacts mid-implementation if design changes
- Pause apply and resume later
- Work on multiple changes in parallel

## Best Practices

### When to Explore What

- The problem space is unclear
- Requirements feel vague or conflicting
- You need to understand current workflows
- You are comparing product or behavior options

### When to Explore How

- The implementation touches multiple systems
- You need to inspect existing architecture
- You need to choose or validate technologies
- Deployment, migrations, tests, or agent handoffs matter

### When to Propose

- The scope is well-defined
- The technical direction is clear enough
- You are ready to formalize design, tasks, and ownership

### When to Apply

- The `spec.html` has been **approved** by the user (required — apply is blocked otherwise)
- Tasks are concrete and traced to requirement IDs
- Ownership and sequencing are clear

### When to Archive

- All tasks are complete
- Code is tested and working
- Changes are merged or ready to preserve as completed work

## See Also

- [Context Files](context-files.md) - Understanding the `.agentweave/` directory
- [Session Modes](session-modes.md) - Hierarchical vs peer collaboration
- [CLI Commands Reference](../reference/cli-commands.md) - All available commands
