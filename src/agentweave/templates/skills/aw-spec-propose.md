---
name: aw-spec-propose
description: Propose a new change — creates a full spec (proposal, design, tasks, team) in one step. Synthesizes prior idea and technical discovery notes when present, then annotates tasks with suitable AgentWeave agents and roles.
---

Propose a new change — generate all spec artifacts in one step, grounded in discovery notes when available and ready for the team.

**Project:** {project_name}
**Mode:** {mode}
**Principal:** {principal}
**Agents:** {agents_list}

Artifacts created:
- `proposal.md` — what & why, with involved agents/roles
- `design.md` — how, with role ownership per subsystem
- `tasks.md` — implementation tasks grouped and annotated by role
- `team.md` — ideal team for this spec, gap vs. current session, setup commands

Optional discovery inputs:
- `spec/discovery/<name>/idea.md` — from `/aw-spec-explore`
- `spec/discovery/<name>/technical.md` — from `/aw-spec-technical-explore`

When ready to implement, run `/aw-spec-apply`.

---

## Steps

### 1. Clarify the change

If $ARGUMENTS provides a clear description, derive a kebab-case name (e.g., "add caching layer" → `add-caching-layer`).

If $ARGUMENTS is empty or unclear, use **AskUserQuestion** (open-ended):
> "What change do you want to work on? Describe what you want to build or fix."

**Do not proceed without knowing what to build.**

### 2. Read optional discovery context

Before creating formal artifacts, look for prior exploration notes:

```bash
test -f spec/discovery/<name>/idea.md && cat spec/discovery/<name>/idea.md
test -f spec/discovery/<name>/technical.md && cat spec/discovery/<name>/technical.md
```

If discovery notes exist:
- Treat them as source context for `proposal.md`, `design.md`, `tasks.md`, and `team.md`
- Preserve decisions and open questions unless the current codebase contradicts them
- If the codebase contradicts a discovery note, surface the conflict clearly and either ask the user or record it in `design.md` Open Questions
- Do not silently invent a different architecture, stack, deployment, testing, or agent plan

If discovery notes do not exist:
- Continue with the quick-propose path from the user's request
- Make reasonable assumptions, but call out major assumptions in `design.md`
- Do not require the user to run exploration first

### 3. Load team context and quality config

Read the team state and quality settings to use throughout artifact generation:

1. Read `.agentweave/session.json` → agent list, mode, principal
2. Read `.agentweave/roles.json` → role assignments per agent
3. Read `agentweave.yml` `quality:` section (if it exists) → `review_required`, `docs_threshold`, `echo_chamber_guard`, `docs_path`

Build a role map:
```
{ "tech_lead": ["agent-a"], "backend_dev": ["agent-a"], "frontend_dev": ["agent-b"], "qa_engineer": ["agent-c"] }
```

Build a quality summary to display alongside the team map:
```
Quality: review_required=true | docs_threshold=non_trivial | echo_chamber=enforce | docs_path=code-docs/
```
If no `quality:` section exists, show: `Quality: not configured (governance off)`

If `.agentweave/roles.json` doesn't exist or agents have no roles assigned, note this and continue — tasks will include role suggestions without agent names.

### 4. Check for existing change

If `spec/changes/<name>/` already exists, use **AskUserQuestion**:
> "A change named `<name>` already exists. Continue it or create a new one?"

### 5. Create the change directory

```bash
mkdir -p spec/changes/<name>
```

### 6. Create artifacts in order

Use **TodoWrite** to track progress through the 4 artifacts.

---

#### 5a. `proposal.md`

Create `spec/changes/<name>/proposal.md` using this structure. If `idea.md` exists, use it as the primary source for problem, goals, non-goals, requirements, and success criteria:

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

Read `proposal.md` for context, then create `spec/changes/<name>/design.md`. If `technical.md` exists, use it as the primary source for architecture, integration points, technology decisions, testing strategy, deployment impact, and sequencing:

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

## Discovery Inputs
- `idea.md`: [used / not present]
- `technical.md`: [used / not present]
- Conflicts with current codebase: [none / describe]

## Security Considerations
- [Permissions: any new IAM roles, CORS settings, or file permissions introduced?]
- [Sensitive data flows: does this feature touch user data, credentials, or external APIs?]
- [New dependencies: list packages being introduced — verify they exist on the real registry]
- [Input handling: any new paths where external input reaches sensitive operations?]

## Dependencies & Sequencing
[Which pieces must be built before others? Note cross-role dependencies.]

## Open Questions
- [ ] [Anything that needs clarification before or during implementation]
```

Use the role map to fill in the "Role Ownership" table. For the sequencing section, explicitly note when one agent must finish before another can start.

---

#### 5c. `tasks.md`

Read `proposal.md` and `design.md` for context, then create `spec/changes/<name>/tasks.md`. If discovery notes included a development flow or test timing, reflect that sequencing in the task order:

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

**Quality governance — when `quality:` settings are active, structure each implementation group as:**
```
## QA Engineer — <agent>  (if qa_engineer role is assigned)
- [ ] Write test spec for <feature> (before implementation)

## <Impl Role> — <agent>
- [ ] Implement <feature>
- [ ] Produce decision doc at <docs_path>/<task-id>.md  ← only if docs_threshold applies

## Code Reviewer — <agent>  (MUST be different agent than implementer)
- [ ] Review: <feature> (use /aw-verify <task-id>)
```

If no agent has `code_reviewer` role and `review_required: true`, add to the review task:
> ⚠ No reviewer assigned — add via: `agentweave roles add <agent> code_reviewer`

This structure enforces echo-chamber separation at spec time: the review task is assigned to a different agent than the implementation task.

---

#### 5d. `team.md`

Read `proposal.md` and `design.md` for context, then create `spec/changes/<name>/team.md`. If `technical.md` includes an AgentWeave execution strategy, use it as the starting point and compare it against the current session state.

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

**Quality governance — flag `code_reviewer` as a blocker when `review_required: true`:**
In the Gap Analysis table, if `code_reviewer` is missing and `review_required: true` is set, mark it as:
```
| `code_reviewer` | Code Reviewer | ⚠ Quality gate blocker — review_required is enabled but no reviewer is assigned |
```
And add to Setup Commands: `agentweave roles add <agent> code_reviewer  ← required before tasks can be approved`

**Standalone regeneration:** If `team.md` already exists and the user asks to regenerate it, update only `team.md` from the current `proposal.md` — do not modify other artifacts.

---

### 7. Show final summary

```
## Spec Ready: <change-name>

**Location:** spec/changes/<change-name>/

**Artifacts:**
- proposal.md — [one-line summary]
- design.md — [key design decision]
- tasks.md — N tasks across M agents
- team.md — [N roles recommended, M missing from current session]

**Discovery Inputs:**
- idea.md: used / not present
- technical.md: used / not present
- conflicts: none / listed in design.md

**Recommended Team:**
- ✓ <agent-a> covers [role1, role2]
- ✗ Missing: [role3] — run `agentweave roles add <agent> <role3>`

Ready to implement. Run `/aw-spec-apply` to start.
```

---

## Guardrails

- Always read dependency artifacts before creating the next one
- Read `spec/discovery/<name>/idea.md` and `spec/discovery/<name>/technical.md` when they exist
- Proceed without discovery artifacts when they do not exist
- Surface conflicts between discovery notes and current codebase facts instead of silently overriding either
- Keep the "Involved Agents" table accurate — only include agents actually doing work
- If roles are missing or ambiguous, make reasonable inferences based on task nature
- If context is critically unclear, ask — but prefer reasonable decisions to keep momentum
- Verify each file exists after writing before moving to the next
- Do NOT implement anything — spec creation only
