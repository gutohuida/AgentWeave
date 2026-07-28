---
name: aw-spec-propose
description: Propose a change by generating a single authoritative, self-contained HTML specification (spec.html) that fully replaces the old markdown artifacts. Applies spec-driven-development best practices (testable requirements with IDs, producer/consumer conformance, numbered algorithms, explicit non-goals, task→requirement traceability) and ends with an explicit user approval gate.
---

Propose a change by producing **one authoritative specification document** — a
self-contained `spec.html` — grounded in discovery notes when available, and gated on
**explicit user approval** before any implementation begins.

**Project:** {project_name}
**Mode:** {mode}
**Principal:** {principal}
**Agents:** {agents_list}

`spec.html` is the normative source of truth for the change. It **replaces** the older
`proposal.md`, `design.md`, `tasks.md`, and `team.md` markdown artifacts — do not create
those. Tests, API/data contracts, fixtures, migrations, configuration, and operational
artifacts remain supporting evidence; a passing test suite alone does not prove complete coverage.

Optional discovery inputs:
- `spec/discovery/<name>/idea.md` — from `/aw-spec-explore`
- `spec/discovery/<name>/technical.md` — from `/aw-spec-technical-explore`

**Authoring reference (read this first):** the full conventions and an annotated HTML
skeleton live next to this skill at `html-spec-conventions.md`. Read it before writing
`spec.html`. It defines the machine-readable contract that `/aw-spec-apply` and
`/aw-spec-archive` depend on.

**Manifest reference:** `spec-manifest-conventions.md` (also bundled beside this skill)
defines `spec/index.json`, the document manifest this skill updates in step 7a.

When the spec is approved, run `/aw-spec-apply`.

---

## Guiding principles (spec-driven development)

Apply these throughout — they are what make a spec safe for an agent to execute:

1. **Separate WHAT/WHY from HOW.** Requirements and acceptance criteria describe
   user-facing behavior and constraints; keep tech-stack/architecture in the Design
   section so requirements stay stable across implementation changes.
2. **Requirements are testable assertions** with stable IDs and modal verbs
   (MUST/SHOULD/MAY) or EARS (`WHEN <condition/event> THE SYSTEM SHALL <response>` — the
   form Kiro's own documentation uses). No vague prose. Give every requirement an element
   `id` so tasks and acceptance criteria can link to it.
3. **Acceptance criteria are Given/When/Then**, one per behavior, binary pass/fail,
   with measurable success criteria.
4. **Multi-step or conditional behavior is a numbered algorithm**, never a paragraph.
5. **State explicit non-goals** — do not rely on omission.
6. **Justify non-obvious rules** — a rule with a stated "why" generalizes to edge cases.
7. **Separate producer requirements** (allowed inputs) **from consumer requirements**
   (required behavior).
8. **Trace every task to requirement IDs** via `data-requirements`.
9. **Label non-normative content** (notes, examples, warnings) distinctly.
10. **Mark unresolved ambiguity** as `[NEEDS CLARIFICATION: …]` and resolve it with the
    user before approval — never guess.
11. **State evidence and limits.** Identify the executable/operational evidence checked,
    what it validates, and material coverage gaps or conflicts that remain open.
12. **Make the lifecycle explicit.** Say whether the change updates a living project spec,
    creates a flow-forward record, or needs a defined reconciliation after implementation.
13. **Decompose an epic before specifying it.** Keep durable system context and shared
    contracts outside the child spec. For multiple independent outcomes, create a shallow
    roadmap whose stable rows state intent, in/deferred boundary, dependencies, status, and
    child-spec link; then propose one vertical capability at a time, never frontend/API/database slices.

---

## Steps

### 1. Clarify the change

If $ARGUMENTS provides a clear description, derive a kebab-case name (e.g., "add caching
layer" → `add-caching-layer`).

If $ARGUMENTS is empty or unclear, use **AskUserQuestion** (open-ended):
> "What change do you want to work on? Describe what you want to build or fix."

**Do not proceed without knowing what to build.**

### 1b. Run a decomposition pass for an epic

Before creating `spec.html`, decide whether the request is one independently demonstrable
capability. If it includes multiple outcomes, contexts, or implementation phases that cannot
be approved and tested together, stop short of authoring a child spec and create or update
`spec/roadmaps/<epic-name>.html` — a roadmap is a spec document too: same self-contained HTML
conventions, with `<meta name="aw-spec-kind" content="roadmap">`. Each row MUST have a stable ID
(and an element `id` to link to), one-line intent, explicit in/deferred scope boundary,
dependencies, status, and a future child-spec path. Ask the user to select the next ready row;
author only that row's `spec.html` and include its parent roadmap path and row ID in the Summary.

If the project keeps a system map (durable constraints, bounded contexts, shared contracts),
read it before writing requirements and reference its IDs instead of restating its rules.

Do not create a roadmap for a small coherent change merely because it has several tasks.

### 2. Read optional discovery context

Before authoring the spec, look for prior exploration notes:

```bash
test -f spec/discovery/<name>/idea.md && cat spec/discovery/<name>/idea.md
test -f spec/discovery/<name>/technical.md && cat spec/discovery/<name>/technical.md
```

If discovery notes exist:
- Treat them as source context for the whole spec (problem, requirements, design, tasks, team).
- Preserve decisions and open questions unless the current codebase contradicts them.
- If the codebase contradicts a note, surface the conflict and either ask the user or
  record it as an Open Question in `spec.html`.
- Do not silently invent a different architecture, stack, deployment, or agent plan.

If discovery notes do not exist:
- Continue from the user's request, making reasonable assumptions.
- Call out major assumptions in the Design section and log genuine unknowns as
  `[NEEDS CLARIFICATION]` open questions.

### 3. Load team context and quality config

1. Read `.agentweave/session.json` → agent list, mode, principal
2. Read `.agentweave/roles.json` → role assignments per agent
3. Read `agentweave.yml` `quality:` section (if present) → `review_required`,
   `docs_threshold`, `echo_chamber_guard`, `docs_path`

Build a role map, e.g.:
```
{ "tech_lead": ["agent-a"], "backend_dev": ["agent-a"], "frontend_dev": ["agent-b"], "qa_engineer": ["agent-c"] }
```

Build a quality summary to reflect in the Tasks/Team sections:
```
Quality: review_required=true | docs_threshold=non_trivial | echo_chamber=enforce | docs_path=code-docs/
```
If no `quality:` section exists, note: `Quality: not configured (governance off)`.

If `.agentweave/roles.json` doesn't exist or agents have no roles, note this and continue
— the Tasks section will carry role suggestions without agent names.

### 3b. Inventory supporting evidence

Before writing requirements, inspect the relevant tests, contracts, fixtures, schemas/migrations,
configuration, deployment/runbooks, and observability material when they exist. Add an **Evidence &
Coverage Limits** section to `spec.html` that states:

- what sources were checked;
- the behavior each source helps validate;
- material behavior that is untested, inferred, or contradictory; and
- the chosen spec lifecycle and reconciliation rule.

Do not convert an existing implementation detail or agent instruction into a product requirement without
recording the rationale and confirming it is intended.

### 4. Check for an existing change

If `spec/changes/<name>/spec.html` already exists, use **AskUserQuestion**:
> "A spec named `<name>` already exists. Continue/overwrite it or create a new one?"

### 5. Resolve open questions before writing

List every ambiguity as `[NEEDS CLARIFICATION: question]`. Use **AskUserQuestion** to
resolve the ones that block a testable requirement. Only unresolved, non-blocking items
may remain — and they must be gone before approval (step 8).

### 6. Read the authoring reference

Read `html-spec-conventions.md` (bundled beside this skill). It defines:
- The `<head>` metadata contract (`aw-spec-status`, `aw-spec-approved-by/at`).
- The task attribute contract (`data-task-id`, `data-status`, `data-role`, `data-agent`,
  `data-requirements`).
- The full annotated HTML skeleton and the section order to follow.

### 7. Create the change directory and write `spec.html`

```bash
mkdir -p spec/changes/<name>
```

Author a **single self-contained** `spec/changes/<name>/spec.html` following the skeleton
in the reference. Requirements below are mandatory:

- Inline `<style>` only — no external CSS/JS/CDN; renders offline.
- `<head>` metadata exactly as specified, with `aw-spec-status="draft"`.
- Sections in order: Summary · Problem/Motivation · Scope & Non-Goals · Conformance
  (producer vs consumer) · Requirements (`FR-00x`, MUST/SHOULD/MAY) · Acceptance Criteria
  (Given/When/Then, linked to requirement IDs) · Behavior/Algorithms (numbered) · Design
  (approach, ASCII architecture, key decisions with rationale, security considerations) ·
  Evidence & Coverage Limits · Spec Lifecycle · Team & Ownership · Tasks · Open Questions · Approval.
- Every requirement has a unique anchor `id` (`FR-1`, `FR-2`, …).
- The **Team** table is derived from the *spec scope* (what the change genuinely needs),
  then compared to the current session to show gaps (`OK <agent>` / `missing`).
- Cross-reference: acceptance criteria and tasks link back to requirement IDs.

**Tasks section rules:**
- Each task is an `<li class="task">` with `data-task-id`, `data-status="pending"`,
  `data-role`, `data-agent`, and `data-requirements` (≥1 requirement ID). Include a
  disabled checkbox and a visible requirement reference.
- Each task is a single concrete unit of work (not "build the whole thing").
- Group tasks by role; put the agent name in the group heading.
- Decompose into small, independently deliverable units; mark parallelizable tasks with
  `data-parallel="true"`.
- A child spec's tasks MUST stay inside its roadmap row's boundary. Put a cross-context
  API/event/schema change in an explicit shared-contract task and reference the contract;
  do not silently duplicate it in sibling specs.
- **No non-coding tasks** (deployment sign-off, marketing, training) in the task list.
- Keep the `.progress` element accurate: `data-total`, `data-done="0"`, and the visible
  "0 / N tasks complete".

**Quality governance — when `quality:` settings are active, structure each feature as:**
```
QA Engineer (<agent>)        → task: write test spec for <feature> (before implementation)
<Impl role> (<agent>)        → task: implement <feature>  [+ decision doc task if docs_threshold applies]
Code Reviewer (<other agent>)→ task: review <feature> (use /aw-verify <task-id>)
```
The reviewer task MUST be assigned to a **different agent** than the implementer
(echo-chamber separation). If no agent has `code_reviewer` and `review_required: true`,
add a visible warning in the Tasks/Team sections:
> ⚠ No reviewer assigned — add via: `agentweave roles add <agent> code_reviewer`

### 7a. Update the spec manifest

Update `spec/index.json` in the same operation (create it if absent — see
`spec-manifest-conventions.md` for the shape and field-ownership rules):

- Add or refresh this change's entry: `title`/`kind: "change-spec"`/`status: "draft"` from the
  HTML you just wrote.
- Set `parent` to the relevant roadmap row's path if step 1b identified one, else `null`.
- Pick an `order` after the highest existing sibling at the same level.
- Never touch another document's entry as a side effect of proposing this change.

### 7b. Self-check the spec before showing it

Run this pass yourself — it is cheap and it is what stops a plausible-looking spec from
reaching implementation. Fix what it finds, then re-run. Treat it as unit tests for the
requirements, not a formality.

**Structural (machine contract):**
- Every `href="#..."` resolves to an `id` that exists in the file; no duplicate `id`s.
- No external CSS/JS/font/image reference — the file renders offline.
- `<head>` carries `aw-spec-name`, `aw-spec-status="draft"`, `aw-spec-approved-by/at`.
- Every `li.task` has `data-task-id`, `data-status="pending"`, `data-role`, `data-agent`,
  and `data-requirements` naming requirement IDs that exist in this document.
- The three theme layers (`:root`, `prefers-color-scheme`, `:root[data-theme]`) and the
  same-document anchor-click interceptor are present.

**Content (consistency):**
- Every requirement is referenced by at least one acceptance criterion **and** one task;
  every task references at least one requirement. Report both directions — an orphan in
  either direction is a real gap, not a formatting nit.
- Every requirement states MUST/SHOULD/MAY (or EARS `THE SYSTEM SHALL`) and could be
  turned into a passing or failing test. Rewrite anything unfalsifiable
  ("robust", "user-friendly", "as needed").
- Ordered or conditional behavior is a numbered `<ol class="algorithm">`, not prose.
- Non-Goals is non-empty. Producer requirements are separated from consumer requirements.
- Notes, examples, and warnings are class-labelled so nothing informative reads as binding.
- The spec stays inside its roadmap row's boundary; cross-context work is a shared-contract
  task referencing the contract, not a duplicated requirement.
- Open Questions contains no unresolved `[NEEDS CLARIFICATION]`.

Report the result in one block (counts + what you fixed), then continue to the gate.

### 8. Approval gate (mandatory)

The spec is **draft** and must not be implemented until the user approves it.

1. Confirm the **Open Questions** section contains no unresolved `[NEEDS CLARIFICATION]`
   markers. If any remain, resolve them with the user first.
2. Present a concise summary (see step 9) and open `spec.html` for the user to read.
3. Use **AskUserQuestion**:
   > "The specification is ready for review at `spec/changes/<name>/spec.html`. Approve it
   > for implementation, or request changes?"
   Options: `Approve` · `Request changes`.
4. If the user requests changes, revise `spec.html` and re-ask. Do not approve on their behalf.
5. On explicit approval, edit `spec.html`:
   - `<meta name="aw-spec-status" content="approved">`
   - fill `aw-spec-approved-by` (the user, or how they identified themselves) and
     `aw-spec-approved-at` (today's ISO date)
   - flip the visible status banner to the approved style/text and complete the Approval section.

**Never set `aw-spec-status="approved"` without an explicit user approval decision.**

### 9. Show final summary

```
## Spec Ready: <change-name>

**Location:** spec/changes/<change-name>/spec.html
**Status:** draft (awaiting approval) | approved

**Contents:**
- N requirements (FR-1 … FR-N), M acceptance criteria
- K tasks across P agents, each traced to requirement IDs
- Team: N roles recommended, M missing from current session

**Discovery Inputs:** idea.md used/not present · technical.md used/not present · conflicts: none/listed

**Recommended Team:**
- OK <agent-a> covers [role1, role2]
- missing [role3] — run `agentweave roles add <agent> role3`

Once approved, run /aw-spec-apply to implement.
```

---

## Guardrails

- `spec.html` is the only artifact — do NOT create `proposal.md`, `design.md`,
  `tasks.md`, or `team.md`.
- Read `html-spec-conventions.md` before authoring; follow its metadata and task contracts exactly.
- Update `spec/index.json` in the same operation (step 7a) — do not leave a new change spec
  unfiled when its manifest entry is this cheap to write.
- Read discovery notes when present; surface conflicts with the codebase instead of overriding either silently.
- Keep requirements free of implementation detail; keep the "how" in the Design section.
- Every task must trace to at least one requirement ID.
- Include evidence/coverage limits and the lifecycle/reconciliation rule; do not claim a complete rebuild from
  prose or passing tests alone.
- Run the step 7b self-check before presenting the spec; never show a spec with dead anchors,
  untraced tasks, or unfalsifiable requirements.
- Resolve every `[NEEDS CLARIFICATION]` before approval — never guess a blocking detail.
- Never flip the spec to `approved` without an explicit user decision.
- Do NOT implement anything — spec creation only.
