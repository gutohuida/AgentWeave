---
name: aw-spec-team
description: Generate a team recommendation for a spec change — ideal roles, reasoning grounded in the spec, gap analysis vs. current session, and setup commands to fill the gaps.
---

Generate a `team.md` for spec change **{change_name}**.

**Project:** {project_name}
**Mode:** {mode}
**Principal:** {principal}
**Agents:** {agents_list}

---

## Steps

### 1. Read the spec context

Read the following files for this change:
- `spec/changes/{change_name}/proposal.md` — scope, goals, non-goals
- `spec/changes/{change_name}/design.md` — if it exists, subsystems and ownership

If `proposal.md` does not exist, stop and tell the user: "No proposal found for `{change_name}`. Run `/aw-spec-propose` first."

### 2. Read current session state

1. Read `.agentweave/session.json` → current agents
2. Read `.agentweave/roles.json` → role assignments per agent

Build the current role map:
```
{ "tech_lead": ["claude"], "backend_dev": ["kimi"], ... }
```

If these files don't exist or are empty, note it — the Gap Analysis section will degrade gracefully.

### 3. Derive the ideal team from the spec

From the proposal and design, identify which roles this project genuinely needs. Reason from the spec outward — **not** from what's currently in the session.

For each needed role, ask: "What does this spec require that makes this role necessary?"

Use these role IDs (from `.agentweave/roles.json` or the built-in list):

| Role ID | Label | Typical trigger |
|---|---|---|
| `tech_lead` | Tech Lead | Cross-cutting architectural decisions, integration |
| `architect` | Architect | New system design, data models, API contracts |
| `backend_dev` | Backend Developer | APIs, database, business logic |
| `frontend_dev` | Frontend Developer | UI components, client-side state |
| `fullstack_dev` | Full Stack Developer | End-to-end features without role separation |
| `qa_engineer` | QA / Test Engineer | Test strategy, edge cases, quality gates |
| `devops_engineer` | DevOps Engineer | CI/CD, infrastructure, deployment |
| `security_engineer` | Security Engineer | Auth/authz, security review |
| `data_engineer` | Data Engineer | Pipelines, ETL, analytics |
| `ml_engineer` | ML / AI Engineer | Models, training, inference |
| `technical_writer` | Technical Writer | Docs, READMEs, API docs |
| `code_reviewer` | Code Reviewer | PR reviews, style enforcement |
| `project_manager` | Project Manager | Coordination, tracking |

Only include roles that the spec genuinely warrants. Don't pad the list.

### 4. Write `team.md`

Create `spec/changes/{change_name}/team.md` with this exact structure:

```markdown
> **Note:** This team recommendation was generated from the spec on {date}.
> Regenerate if the spec scope changes significantly.

# Team: {change_name}

## Recommended Team

| Role | Label | Why Needed |
|------|-------|------------|
| `role_id` | Role Label | One-line reason specific to this spec |

## Role Reasoning

### {Role Label}
[Paragraph grounding this role in a specific decision from the proposal or design.
Reference the actual scope — not generic role descriptions.]

### {Role Label}
[...]

## Gap Analysis

| Role | Label | Status |
|------|-------|--------|
| `role_id` | Role Label | ✓ {agent_name} / ✗ Missing |

> Session state: read from `.agentweave/roles.json`

*If session state was unavailable:*
> Session state was not available. Showing full recommended team without gap diff.

## Setup Commands

```bash
# Add missing agents — adjust agent names to match your tooling
agentweave roles add <agent> <role_id>
```

*Only include commands for missing roles from the gap analysis.*
*If no roles are missing, write: "Your current session covers all recommended roles."*
```

### 5. Show summary

After writing, display:

```
## Team Recommendation: {change_name}

Recommended roles: [list]
Current session covers: [list of ✓ roles]
Missing: [list of ✗ roles, or "none"]

Written to spec/changes/{change_name}/team.md
```

---

## Guardrails

- Derive roles from the spec, not from what's already in the session
- Don't recommend roles the spec doesn't warrant — quality over coverage
- If session state is unavailable, skip gap diff and note it clearly
- Role reasoning must reference something specific from the proposal or design — not generic boilerplate
- Do NOT modify any other spec artifacts
