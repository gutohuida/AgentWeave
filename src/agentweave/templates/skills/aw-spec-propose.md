---
name: aw-spec-propose
description: Propose a new change — creates a full spec (proposal, design, tasks, team) in one step. Tasks are annotated with the most suitable AgentWeave agent and role for each piece of work, ready for delegation.
---

Propose a new change — generate all spec artifacts in one step, role-annotated and ready for the team.

**Project:** {project_name}
**Mode:** {mode}
**Principal:** {principal}
**Agents:** {agents_list}

Artifacts created:
- `proposal.md` — what & why, with involved agents/roles
- `design.md` — how, with role ownership per subsystem
- `tasks.md` — implementation tasks grouped and annotated by role
- `team.md` — ideal team for this spec, gap vs. current session, setup commands

When ready to implement, run `/aw-spec-apply`.

---

## Steps

### 1. Clarify the change

If $ARGUMENTS provides a clear description, derive a kebab-case name (e.g., "add caching layer" → `add-caching-layer`).

If $ARGUMENTS is empty or unclear, use **AskUserQuestion** (open-ended):
> "What change do you want to work on? Describe what you want to build or fix."

**Do not proceed without knowing what to build.**

### 2. Load team context

Read the team state to use throughout artifact generation:

1. Read `.agentweave/session.json` → agent list, mode, principal
2. Read `.agentweave/roles.json` → role assignments per agent

Build a role map:
```
{ "tech_lead": ["agent-a"], "backend_dev": ["agent-a"], "frontend_dev": ["agent-b"], "qa_engineer": ["agent-c"] }
```

If `.agentweave/roles.json` doesn't exist or agents have no roles assigned, note this and continue — tasks will include role suggestions without agent names.

### 3. Check for existing change

If `spec/changes/<name>/` already exists, use **AskUserQuestion**:
> "A change named `<name>` already exists. Continue it or create a new one?"

### 4. Create the change directory

```bash
mkdir -p spec/changes/<name>
```

### 5. Create artifacts in order

Use **TodoWrite** to track progress through the 4 artifacts.

---

#### 5a. `proposal.md`

Create `spec/changes/<name>/proposal.md` using this structure:

```markdown
# Proposal: <Change Name>

## Summary
[1-2 sentence description of what this change does]

## Problem / Motivation
[Why this is needed. What breaks, hurts, or is missing without it?]

## Goals
- [Concrete goal 1]
- [Concrete goal 2]

## Non-Goals
- [What this change explicitly does NOT do]

## Involved Agents

| Agent | Roles | Responsibility |
|-------|-------|----------------|
| <agent> | <roles> | [What they own in this change] |

## Success Criteria
[How will we know this is done and working?]
```

Apply team context: populate the "Involved Agents" table using the role map from step 2. Infer each agent's responsibility based on their roles and the nature of the change.

---

#### 5b. `design.md`

Read `proposal.md` for context, then create `spec/changes/<name>/design.md`:

```markdown
# Design: <Change Name>

## Approach
[High-level technical approach — 2-4 sentences]

## Architecture

[ASCII diagram of the key components and their relationships]

## Role Ownership

| Subsystem / Area | Owner Role | Agent |
|-----------------|------------|-------|
| [subsystem 1]   | [role]     | [agent] |
| [subsystem 2]   | [role]     | [agent] |

## Key Decisions
- **[Decision 1]**: [Chosen approach and why]
- **[Decision 2]**: [Chosen approach and why]

## Dependencies & Sequencing
[Which pieces must be built before others? Note cross-role dependencies.]

## Open Questions
- [ ] [Anything that needs clarification before or during implementation]
```

Use the role map to fill in the "Role Ownership" table. For the sequencing section, explicitly note when one agent must finish before another can start.

---

#### 5c. `tasks.md`

Read `proposal.md` and `design.md` for context, then create `spec/changes/<name>/tasks.md`:

```markdown
# Tasks: <Change Name>

## Progress
0 / <total> tasks complete

---

## <Role 1> — <Agent Name>

- [ ] [Task description]
- [ ] [Task description]

## <Role 2> — <Agent Name>

- [ ] [Task description]
- [ ] [Task description]

---

## Cross-Role Dependencies

- <Agent A> must complete [task] before <Agent B> can start [task]
```

**Rules for tasks:**
- Group tasks by role, with the agent name in the heading
- Each task is a single, concrete unit of work (not "build the whole thing")
- If an agent has multiple roles, group all their tasks together under one heading
- The "Cross-Role Dependencies" section is only needed if ordering matters between agents
- If no roles are assigned, create a single flat list with a `**Suggested role**: <role>` note per task

---

#### 5d. `team.md`

Read `proposal.md` and `design.md` for context, then create `spec/changes/<name>/team.md`.

**Team recommendation is spec-driven, not session-constrained.** Derive the ideal team from the project scope — what does this spec genuinely require? Then compare against the current session to surface gaps.

```markdown
> **Note:** This team recommendation was generated from the spec on <date>.
> Regenerate if the spec scope changes significantly.

# Team: <change-name>

## Recommended Team

| Role | Label | Why Needed |
|------|-------|------------|
| `role_id` | Role Label | One-line reason specific to this spec |

## Role Reasoning

### {Role Label}
[Paragraph grounding this role in a specific decision or scope item from proposal.md or design.md.
Must reference something concrete — not generic role descriptions.]

## Gap Analysis

| Role | Label | Status |
|------|-------|--------|
| `role_id` | Role Label | ✓ {agent_name} / ✗ Missing |
```

Read `.agentweave/roles.json` to populate the Gap Analysis. If it doesn't exist or session has no roles assigned, write:
> Session state was not available. Showing full recommended team without gap diff.

For Setup Commands, include one `agentweave roles add <agent> <role_id>` per missing role. If no roles are missing, write: "Your current session covers all recommended roles."

**Standalone regeneration:** If `team.md` already exists and the user asks to regenerate it, update only `team.md` from the current `proposal.md` — do not modify other artifacts.

---

### 6. Show final summary

```
## Spec Ready: <change-name>

**Location:** spec/changes/<change-name>/

**Artifacts:**
- proposal.md — [one-line summary]
- design.md — [key design decision]
- tasks.md — N tasks across M agents
- team.md — [N roles recommended, M missing from current session]

**Recommended Team:**
- ✓ <agent-a> covers [role1, role2]
- ✗ Missing: [role3] — run `agentweave roles add <agent> <role3>`

Ready to implement. Run `/aw-spec-apply` to start.
```

---

## Guardrails

- Always read dependency artifacts before creating the next one
- Keep the "Involved Agents" table accurate — only include agents actually doing work
- If roles are missing or ambiguous, make reasonable inferences based on task nature
- If context is critically unclear, ask — but prefer reasonable decisions to keep momentum
- Verify each file exists after writing before moving to the next
- Do NOT implement anything — spec creation only
