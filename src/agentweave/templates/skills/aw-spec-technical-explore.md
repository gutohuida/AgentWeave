---
name: aw-spec-technical-explore
description: Explore how to build an idea before proposing a spec. Focuses on architecture, existing stack, technology choices, deployment, testing, sequencing, and AgentWeave agent/role execution strategy. Never implements.
---

Enter technical exploration mode. Investigate how the work should be built before turning it into a formal proposal.

**Project:** {project_name}
**Mode:** {mode}
**Principal:** {principal}
**Agents:** {agents_list}

**IMPORTANT: Technical exploration is for planning, not implementing.** You may read files, inspect configuration, run safe read-only commands, and map the codebase, but you must never write application code or implement features. Creating or updating spec/discovery notes is allowed when the user asks to capture the thinking.

This skill answers: **how are we building it?**

For product/problem discovery, use `/aw-spec-explore`.

---

## Spec-Driven Mindset

The output of this stage feeds the **Design** section of the authoritative `spec.html`
that `/aw-spec-propose` generates. Keep it disciplined:

- **HOW belongs here, WHAT/WHY stays in requirements.** Architecture, stack, data model,
  and sequencing live in Design — do not restate or mutate user-facing requirements.
- **Justify every non-obvious decision.** Record the "why", not just the choice, so it
  generalizes and can be challenged later.
- **Mark unresolved technical unknowns** as `[NEEDS CLARIFICATION: question]` rather than
  guessing — the proposal must resolve them before approval.
- **Make testing and sequencing explicit and traceable**, so tasks can later map back to
  requirement IDs.

---

## The Stance

- **Architecture-first** - Understand the current system before choosing a path.
- **Existing-project aware** - If the project already has stack, framework, deployment, or testing decisions, treat them as constraints.
- **Pragmatic** - Prefer integration with existing patterns over introducing new technology.
- **Explicit about tradeoffs** - Make the cost of each technical choice visible.
- **AgentWeave-aware** - Plan which agents and roles should own each piece of work.
- **Test-conscious** - Decide what to test, when to test, and who owns verification.

---

## Start With Project State

Determine whether this is an existing project, a greenfield project, or a greenfield area inside an existing project.

For an existing project, inspect relevant files before making recommendations:

```bash
find . -maxdepth 3 -type f \( -name "package.json" -o -name "pyproject.toml" -o -name "requirements*.txt" -o -name "Dockerfile" -o -name "docker-compose.yml" -o -name "mkdocs.yml" -o -name "README.md" \)
rg "<feature keyword>"
```

Read only what is useful. Look for:
- Language and framework choices
- Dependency and package managers
- Existing module boundaries
- API, CLI, UI, or worker patterns
- Persistence and data model patterns
- Test framework and test layout
- Build, deploy, and CI configuration
- Security and configuration conventions

For a new project or genuinely greenfield area, help compare reasonable stack options instead of pretending choices are already made.

---

## Existing Project Path

When the project already exists:

- Reuse the project's language, framework, package manager, and test framework unless there is a strong reason not to.
- Skip already-settled decisions such as "React vs Vue" or "SQLite vs Postgres" when the codebase already answers them.
- Focus on how the new work integrates with current architecture.
- Identify existing helpers, APIs, stores, commands, models, routes, components, or docs to extend.
- Note constraints from packaging, deployment, auth, logging, migrations, and backwards compatibility.
- Surface any reason a new dependency, service, or architecture pattern might be justified.

Use a structure like:

```text
CURRENT TECHNICAL SHAPE
Language/framework: ...
Data/storage: ...
Tests: ...
Deployment: ...
Relevant modules: ...

INTEGRATION POINTS
1. ...
2. ...

DECISIONS ALREADY MADE BY THE CODEBASE
- ...

DECISIONS STILL NEEDED
- ...
```

---

## Greenfield Path

When the project or subsystem is new:

- Compare suitable languages, frameworks, persistence, deployment, and test approaches.
- Favor the smallest stack that satisfies the requirements.
- Identify operational needs early: hosting, CI, secrets, migrations, observability, backups, and rollback.
- Choose defaults only after explaining the tradeoff.

Use a comparison table when helpful:

```markdown
| Option | Fit | Cost | Risk |
|---|---|---|---|
| Option A | ... | ... | ... |
| Option B | ... | ... | ... |
```

---

## Testing Strategy

Make testing explicit:

- What should be tested before implementation?
- What unit tests are needed?
- What integration or API tests are needed?
- What UI or browser checks are needed?
- What manual verification is still necessary?
- Which tests should run during implementation, before review, and before archive?

For each major work area, identify:

```text
Area: <area>
Test first: yes/no
Automated tests: <test files or commands>
Manual checks: <if needed>
Owner: <role or agent>
```

---

## Deployment And Operations

Investigate deployment only to the depth the change needs:

- Is this CLI-only, backend, frontend, docs, worker, or multi-service work?
- Does it need migrations or persisted data changes?
- Does it require new environment variables, secrets, ports, jobs, queues, or external APIs?
- Does the build or Docker setup need to change?
- What is the rollback path?
- What must be documented for operators or users?

---

## AgentWeave Execution Strategy

This is the stage where AgentWeave context matters.

Read these files if they exist:

```bash
cat .agentweave/session.json
cat .agentweave/roles.json
sed -n '/^quality:/,$p' agentweave.yml
```

Use them to map the development cycle:

- Which roles does the work require?
- Which available agents already cover those roles?
- Which roles are missing?
- Which work can happen in parallel?
- Which tasks must happen sequentially?
- Who owns tests, implementation, review, docs, deployment, and verification?
- If quality settings exist, how do `review_required`, `docs_threshold`, `docs_path`, and `echo_chamber_guard` affect the plan?

Do not invent unnecessary roles. Recommend only what the scope warrants.

Example:

```markdown
## Agent Plan

| Area | Role | Agent | Notes |
|---|---|---|---|
| API changes | `backend_dev` | claude | Must land before UI wiring |
| UI wiring | `frontend_dev` | kimi | Can begin after API contract exists |
| Tests/review | `qa_engineer` / `code_reviewer` | gemini | Separate from implementer if quality requires |

## Development Flow

1. Backend defines contract and tests.
2. Frontend wires UI against contract.
3. QA runs integration checks.
4. Reviewer verifies implementation and docs.
```

---

## Capturing Technical Notes

When technical decisions crystallize, offer to capture them as:

```text
spec/discovery/<slug>/technical.md
```

Use this structure:

```markdown
# Technical Discovery: <Topic>

Generated: <date>

## Project State
[Existing project, greenfield project, or greenfield area]

## Existing Architecture / Stack
[Languages, frameworks, storage, deployment, tests, relevant modules]

## Integration Points
- [File/module/API/component/command]

## Decisions Already Made
- [Decision inherited from the codebase]

## Decisions For This Change
- **[Decision]**: [choice and rationale — always record the "why"]

## Testing Strategy
- [What to test, when, and with which commands]

## Deployment / Operations
- [Deployment, migrations, secrets, rollback, docs]

## AgentWeave Execution Strategy
- [Agents, roles, sequencing, review, quality settings]

## Open Questions
- [ ] [NEEDS CLARIFICATION: unresolved technical question the proposal must answer]

## Risks / Unknowns
- [Risk or unresolved technical question]

## Ready For Proposal
- [What `/aw-spec-propose` should carry into the spec.html Design, Tasks, and Team sections]
```

Always offer before writing notes. If the user does not want artifacts, provide a concise technical summary instead.

---

## Ending Technical Exploration

When the technical path is clear, summarize:

```markdown
## Technical Direction

**Architecture**: [approach]
**Stack/dependencies**: [reuse/additions]
**Testing**: [when and how]
**Deployment**: [impact]
**Agent plan**: [roles/agents/sequencing]
**Open questions**: [if any]

Next: run `/aw-spec-propose` to formalize this into an authoritative, approval-gated `spec.html` (requirements, design, tasks, and team in one document).
```

---

## Guardrails

- Never write application code or implement features.
- Do not revisit existing technology choices unless the change truly requires it.
- Do not recommend new dependencies without a concrete reason.
- Do not ignore current architecture, tests, deployment, or quality settings.
- Do not block if AgentWeave session files are absent; recommend ideal roles from the technical scope.
- Do offer to capture technical notes, but never auto-capture decisions without the user's consent.
