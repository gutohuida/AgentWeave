---
name: aw-setup-roles
description: Assign, add, or remove AgentWeave roles for agents — shows the full 20-role catalog (human-title and AI-native) with purposes, then applies via CLI or agentweave.yml. Use when defining who does what in the project. For full project setup use aw-setup.
---

Manage role assignments for the agents in this project.

**Project:** {project_name} — **agents:** {agents_list} (principal: {principal})

## 1. Role catalog

Human-title roles:

| Role | Purpose |
|---|---|
| `tech_lead` | Architecture decisions, code review, integration |
| `architect` | System design, data models, API contracts |
| `backend_dev` | APIs, database, business logic, server-side |
| `frontend_dev` | UI components, styling, client-side state |
| `fullstack_dev` | Backend and frontend features |
| `qa_engineer` | Tests, quality assurance, edge cases |
| `devops_engineer` | CI/CD, infrastructure, deployment |
| `security_engineer` | Security review, auth/authz, vulnerability audit |
| `data_engineer` | Data pipelines, ETL, analytics |
| `ml_engineer` | ML models, training pipelines, inference |
| `technical_writer` | Documentation, READMEs, API docs |
| `code_reviewer` | Pull request reviews, style enforcement |
| `project_manager` | Task tracking, progress coordination |

AI-native (function-first) roles:

| Role | Purpose |
|---|---|
| `coordinator` | Decompose goal, delegate in parallel, aggregate results |
| `model_router` | Route each task to the best agent/model by difficulty, capability, cost |
| `explorer` | Reconnaissance and grounding; condensed, cited findings |
| `implementer` | Turn a well-specified task into working, tested code |
| `verifier` | Evidence-gated evaluation against tests and specs |
| `guardian` | AI-specific safety review: slopsquatting, injection, scopes, secrets |
| `context_keeper` | Curate shared memory; summarize/compact; fight context rot |

Both sets can be combined, e.g. `[implementer, frontend_dev]`.

## 2. See current assignments

```bash
agentweave roles list         # agents and their roles
agentweave roles available    # the catalog (same list as above)
```

## 3. Assign roles

Imperative (takes effect immediately):

```bash
agentweave roles add <agent> <role>                    # add one
agentweave roles remove <agent> <role>                 # remove one
agentweave roles set <agent> backend_dev,code_reviewer # replace the whole set
```

Declarative (survives re-activation, preferred for permanence) — in `agentweave.yml`:

```yaml
agents:
  {principal}:
    roles: [tech_lead, coordinator]
  kimi:
    roles: [backend_dev]
```

then `agentweave activate`.

## Guidelines

- **Principal** in hierarchical mode: `tech_lead` (human-title style) or `coordinator` (AI-native style).
- Always have a reviewer when `quality.review_required: true`: assign `code_reviewer` or `verifier` to a **different** agent than the implementer (see `aw-setup-security` — `echo_chamber_guard` can enforce this).
- Assign `guardian` or `security_engineer` when security guardrails matter (dependency checks, secrets handling).
- Role guides are written to `.agentweave/roles/<role>.md` when assigned — agents read their guide at session start. Only assigned roles get guide files.
