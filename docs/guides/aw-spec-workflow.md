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
| **Propose** | Create structured plan with design, tasks, and team ownership | `/aw-spec-propose` | `proposal.md`, `design.md`, `tasks.md`, `team.md` |
| **Apply** | Implement the planned changes | `/aw-spec-apply` | Working code |
| **Archive** | Finalize and store completed work | `/aw-spec-archive` | Archived change |

Both exploration stages are optional, but they are useful when the scope is unclear, the implementation is complex, or multiple agents will work on the change.

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

Once the idea and technical path are clear, create a structured proposal with the artifacts needed for implementation.

```bash
/aw-spec-propose "add-user-authentication"
```

If discovery notes exist, `aw-spec-propose` uses them as source context:

```text
spec/discovery/<name>/idea.md
spec/discovery/<name>/technical.md
```

If discovery notes do not exist, propose still works from the user's request.

This creates a change directory at `spec/changes/<name>/` containing:

| Artifact | Purpose |
|----------|---------|
| `proposal.md` | What and why: business case, scope, goals, non-goals |
| `design.md` | How: technical approach, decisions, architecture, risks |
| `tasks.md` | Implementation checklist with role or agent ownership |
| `team.md` | Recommended team, current-session gaps, setup commands |

### Change Directory Structure

```text
spec/
└── changes/
    └── add-user-authentication/
        ├── proposal.md
        ├── design.md
        ├── tasks.md
        └── team.md
```

## Stage 4: Apply

Implement the tasks from your proposal.

```bash
# Apply the current change
/aw-spec-apply

# Apply a specific change
/aw-spec-apply "add-user-authentication"
```

The apply stage:

1. Reads the formal spec artifacts (`proposal.md`, `design.md`, `tasks.md`)
2. Shows progress, such as `3/7 tasks complete`
3. Works through each pending task
4. Marks tasks complete as they finish (`- [ ]` to `- [x]`)
5. Delegates work to matching agents when appropriate and confirmed by the user

Earlier discovery notes are supporting context. The formal proposal, design, and tasks are the source of truth during implementation.

### Agent Delegation

Tasks can include role or agent ownership:

```markdown
## Backend Developer - claude

- [ ] Create API endpoints

## Frontend Developer - kimi

- [ ] Build login page UI
```

When applying changes with role ownership, tasks can be delegated to matching agents in your session.

## Stage 5: Archive

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
3. Optionally syncs delta specs to the main spec library
4. Moves the change to `spec/changes/archive/YYYY-MM-DD-<name>/`

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
   -> Creates proposal.md, design.md, tasks.md, and team.md
   -> Uses discovery notes if present

4. /aw-spec-apply
   -> Implements tasks one by one or delegates them
   -> Marks tasks complete

5. /aw-spec-archive
   -> Moves completed change to archive
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

- The proposal and design are reviewed enough to implement
- Tasks are concrete
- Ownership and sequencing are clear

### When to Archive

- All tasks are complete
- Code is tested and working
- Changes are merged or ready to preserve as completed work

## See Also

- [Context Files](context-files.md) - Understanding the `.agentweave/` directory
- [Session Modes](session-modes.md) - Hierarchical vs peer collaboration
- [CLI Commands Reference](../reference/cli-commands.md) - All available commands
