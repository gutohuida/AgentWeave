# AW-Spec Workflow

The AW-Spec workflow provides a structured approach to managing changes in your project through four stages: **explore**, **propose**, **apply**, and **archive**.

## Overview

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Explore  │───▶│ Propose  │───▶│  Apply   │───▶│ Archive  │
│          │    │          │    │          │    │          │
│  Think   │    │  Design  │    │  Build   │    │  Finish  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

| Stage | Purpose | Skill | Output |
|-------|---------|-------|--------|
| **Explore** | Investigate ideas, clarify requirements | `/aw-spec-explore` | Understanding, findings |
| **Propose** | Create structured plan with design and tasks | `/aw-spec-propose` | `proposal.md`, `design.md`, `tasks.md` |
| **Apply** | Implement the planned changes | `/aw-spec-apply` | Working code |
| **Archive** | Finalize and store completed work | `/aw-spec-archive` | Archived change |

## Prerequisites

The AW-Spec workflow skills are available as Claude Code skills when you run `agentweave init`. They are located in `.claude/skills/`.

## Stage 1: Explore

Use explore mode when you want to think through an idea, investigate a problem, or clarify requirements before committing to implementation.

```bash
# Start exploring an idea
/aw-spec-explore

# Or explore a specific topic
/aw-spec-explore "add-user-authentication"
```

**What you can do in explore mode:**

- Ask clarifying questions about the problem space
- Investigate the existing codebase for relevant patterns
- Compare multiple approaches with tradeoff analysis
- Surface risks and unknowns
- Visualize with ASCII diagrams

**Important:** Explore mode is for thinking, not implementing. You can create artifacts (proposals, designs) to capture insights, but don't write application code.

## Stage 2: Propose

Once you have a clear understanding, create a structured proposal with all the artifacts needed for implementation.

```bash
# Create a proposal with a descriptive name
/aw-spec-propose "add-user-authentication"
```

This creates a change directory at `awspec/changes/<name>/` containing:

| Artifact | Purpose |
|----------|---------|
| `proposal.md` | What and why — the business case and scope |
| `design.md` | How — technical design decisions |
| `tasks.md` | Implementation steps with checkboxes |

The proposal stage generates all artifacts in dependency order. You can review and refine them before moving to implementation.

### Change Directory Structure

```
awspec/
└── changes/
    └── add-user-authentication/
        ├── proposal.md         # Scope and rationale
        ├── design.md           # Technical design
        └── tasks.md            # Implementation checklist
```

## Stage 3: Apply

Implement the tasks from your proposal.

```bash
# Apply the current change
/aw-spec-apply

# Apply a specific change
/aw-spec-apply "add-user-authentication"
```

The apply stage:

1. Reads the context files (`proposal.md`, `design.md`, `tasks.md`)
2. Shows your progress ("3/7 tasks complete")
3. Works through each pending task
4. Marks tasks complete as you finish them (`- [ ]` → `- [x]`)

**Task format in `tasks.md`:**

```markdown
## Implementation Tasks

- [x] Set up database schema
- [ ] Create API endpoints
- [ ] Add authentication middleware
```

### Agent Delegation

Tasks can include role hints for automatic delegation:

```markdown
- [ ] Create API endpoints <!-- role: backend_dev -->
- [ ] Design login page <!-- role: ui_designer -->
```

When applying changes with role hints, tasks can be delegated to matching agents in your session.

## Stage 4: Archive

When all tasks are complete, archive the change to keep your workspace clean.

```bash
# Archive the current change
/aw-spec-archive

# Archive a specific change
/aw-spec-archive "add-user-authentication"
```

Archiving:

1. Checks that all artifacts are complete
2. Verifies all tasks are marked done
3. Optionally syncs delta specs to main specs
4. Moves the change to `awspec/changes/archive/YYYY-MM-DD-<name>/`

## Workflow Integration

### From Idea to Implementation

```
User: "I want to add user authentication"

1. /aw-spec-explore
   → "Let's think through the auth approach..."
   → Discuss options: OAuth vs email/password vs magic links
   → Decide on approach

2. /aw-spec-propose "add-user-auth"
   → Creates proposal.md, design.md, tasks.md
   → Review the plan

3. /aw-spec-apply
   → Implements tasks one by one
   → Marks tasks complete

4. /aw-spec-archive
   → Moves completed change to archive
```

### Fluid Workflow

The AW-Spec workflow is not strictly linear. You can:

- Return to explore mode if implementation reveals new complexity
- Update artifacts mid-implementation if design changes
- Pause apply and resume later
- Work on multiple changes in parallel

## Best Practices

### When to Explore

- The problem space is unclear
- You're comparing multiple approaches
- You need to investigate existing code
- Requirements feel vague or conflicting

### When to Propose

- You have a clear understanding of what needs to be built
- The scope is well-defined
- You're ready to commit to an approach

### When to Apply

- All stakeholders have reviewed the proposal
- Design decisions are finalized
- You're ready to implement

### When to Archive

- All tasks are complete
- Code is tested and working
- Changes are merged or deployed

## See Also

- [Context Files](context-files.md) — Understanding the `.agentweave/` directory
- [Session Modes](session-modes.md) — Hierarchical vs peer collaboration
- [CLI Commands Reference](../reference/cli-commands.md) — All available commands
