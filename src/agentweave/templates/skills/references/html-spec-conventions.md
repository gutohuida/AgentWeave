# Authoring `spec.html` — Conventions & Deep Dive

This is the canonical reference for producing the **authoritative HTML specification**
(`spec.html`) that `/aw-spec-propose` generates for every change. In the AW-Spec
workflow, `spec.html` is the single source of truth — it **replaces** the older
`proposal.md`, `design.md`, `tasks.md`, and `team.md` markdown artifacts.

The conventions below are distilled from spec-driven-development research: GitHub Spec
Kit, Amazon Kiro (EARS), Cline/Copilot instruction-file guidance, and — most
importantly — the WHATWG HTML Living Standard, which is engineered to be
"detailed enough that implementations can achieve complete interoperability without
reverse-engineering each other." That is exactly the property we want in a spec an AI
agent will execute.

---

## Why HTML (not markdown)

- **One self-contained, authoritative document.** A single file a human opens in a
  browser, reads top-to-bottom, and explicitly approves before any code is written.
- **Rich, unambiguous structure.** HTML gives us real semantic containers
  (`<section>`, `<dl>`, `<ol>`), typographic markers for normative vs. non-normative
  text, cross-reference anchors, and — critically — **machine-readable data
  attributes** that `/aw-spec-apply` and `/aw-spec-archive` rely on.
- **Approval + progress live in the file.** The approval gate and per-task completion
  state are encoded as metadata/attributes inside `spec.html`, so no companion state
  file is needed.

---

## Hard rules (the machine-readable contract)

`/aw-spec-apply` and `/aw-spec-archive` parse these. They MUST be present and exact.

### 1. Approval status (the hard gate)

Put these in `<head>`:

```html
<meta name="aw-spec-name" content="<change-name>">
<meta name="aw-spec-status" content="draft">        <!-- draft | approved -->
<meta name="aw-spec-approved-by" content="">        <!-- filled on approval -->
<meta name="aw-spec-approved-at" content="">        <!-- ISO date, filled on approval -->
```

- Propose always writes `content="draft"`.
- Only after the user **explicitly approves** does the status flip to `approved`
  (and `approved-by` / `approved-at` get filled in).
- `/aw-spec-apply` **refuses to run** unless `aw-spec-status` is `approved`.

### 2. Tasks (traceable + trackable)

Every task is a list item with these attributes:

```html
<li class="task"
    data-task-id="T1"
    data-status="pending"                <!-- pending | done -->
    data-role="backend_dev"
    data-agent="claude"
    data-requirements="FR-1,FR-3">
  <input type="checkbox" disabled>        <!-- checked when data-status="done" -->
  <span class="task-desc">Implement the token-refresh endpoint.</span>
  <span class="req-refs">(FR-1, FR-3)</span>
</li>
```

- `data-task-id` — stable unique ID (`T1`, `T2`, …).
- `data-status` — `/aw-spec-apply` flips `pending` → `done` and checks the checkbox.
- `data-requirements` — comma-separated requirement IDs this task satisfies
  (traceability; every task MUST reference at least one requirement).
- `data-role` / `data-agent` — ownership.

`/aw-spec-archive` treats the change as complete only when **every** `li.task` has
`data-status="done"` and `aw-spec-status="approved"`.

---

## Content conventions (WHATWG-inspired)

### A. Separate WHAT/WHY from HOW
The **Requirements** and **Acceptance Criteria** sections describe user-facing behavior,
goals, and constraints — no tech-stack commitments. Implementation details
(architecture, libraries, data model) live in the **Design** section. This keeps the
requirements stable even if the implementation approach changes.

### B. Explicit conformance classes: producer vs. consumer
Following WHATWG §1.9.1, separate:
- **Producer requirements** — what inputs the user/system is *allowed* to provide.
- **Consumer requirements** — how the software *must act* in response.
Conflating input-validation rules with processing/behavior rules is a top source of
ambiguity. Give them separate subsections or a labelled column.

### C. Requirements as testable assertions
Write each requirement with a stable ID and a modal verb (MUST / SHOULD / MAY), or EARS
syntax (`WHEN <event> THEN <system> SHALL <response>`). Never vague prose.

```html
<tr id="FR-1">
  <td>FR-1</td><td>MUST</td>
  <td>The system MUST issue a new access token when a valid refresh token is presented.</td>
</tr>
```

### D. Acceptance criteria = Given/When/Then, one per behavior
Each criterion is independently testable, binary pass/fail. Make success criteria
measurable ("handles 1000 concurrent refreshes" — not "is fast").

### E. Multi-step / conditional behavior as numbered algorithms
Wherever behavior has ordering or a branch, write an `<ol>` algorithm, not a paragraph —
leaves no room for reordering or a missed branch (WHATWG; mirrors EARS and Spec Kit).

```html
<ol class="algorithm">
  <li>Parse the refresh token.</li>
  <li>If the token is expired, respond 401 and stop.</li>
  <li>Otherwise, mint a new access token and respond 200.</li>
</ol>
```

### F. Explicit non-goals
State out-of-scope items in a **Non-Goals** section — do not rely on omission. This
prevents an agent from "helpfully" expanding scope.

### G. Justify non-obvious rules
When a rule could seem arbitrary, state the reason inline. A rule with a documented
"why" generalizes correctly to edge cases the spec didn't anticipate.

### H. Label non-normative content distinctly
Mark notes, examples, and warnings so an agent does not treat rationale or illustration
as binding. Use dedicated classes:

```html
<p class="note"><strong>Note:</strong> non-normative background.</p>
<p class="example"><strong>Example:</strong> illustrative only.</p>
<p class="warning"><strong>Warning:</strong> …</p>
<p class="issue"><strong>Open issue:</strong> …</p>
```

### I. Mark unresolved ambiguity explicitly
Any open question becomes a visible `[NEEDS CLARIFICATION: …]` marker in an
**Open Questions** section. The spec MUST NOT be approved while any remain — resolve
them with the user first.

### J. Cross-reference every defined term once
Give each requirement/term a single anchor (`id="FR-1"`) and link to it from tasks and
acceptance criteria. Avoid synonyms for the same concept (a frequent LLM
misinterpretation trigger).

---

## Task-list quality (SDD)

- **Decompose** into small, independently deliverable units. Mark `[P]` (or
  `data-parallel="true"`) when tasks can run in parallel.
- **Trace** every task to requirement IDs via `data-requirements`.
- **No non-coding tasks** (deployment sign-off, marketing, user training) in the agent
  task list — keep it to what the agent actually executes.
- **Quality governance:** when `agentweave.yml` `quality:` settings are active, keep the
  reviewer task assigned to a *different* agent than the implementer (echo-chamber
  separation), add a decision-doc task when `docs_threshold` applies, and flag a missing
  `code_reviewer` when `review_required: true`.

---

## Self-contained styling

`spec.html` MUST be a single file with **inline `<style>`** — no external CSS/JS/CDN, so
it renders identically offline. Keep it clean and readable: a fixed max width, readable
font, and clear visual distinction for `.note` / `.example` / `.warning` /
`.task[data-status=done]`.

---

## Annotated skeleton

Use this as the starting template. Fill every `<!-- … -->`. Substitution tokens
(`{project_name}`, `{principal}`, `{agents_list}`, `{mode}`) are available at generation time.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Spec: <!-- Change Name --></title>
  <meta name="aw-spec-name" content="<!-- change-name -->">
  <meta name="aw-spec-status" content="draft">
  <meta name="aw-spec-approved-by" content="">
  <meta name="aw-spec-approved-at" content="">
  <meta name="aw-spec-generated-at" content="<!-- ISO date -->">
  <style>
    :root { --fg:#1a1a1a; --muted:#555; --accent:#0b5fff; --done:#0a7f3f; }
    body { max-width: 860px; margin: 2rem auto; padding: 0 1rem;
           font: 16px/1.6 system-ui, sans-serif; color: var(--fg); }
    h1,h2,h3 { line-height:1.25; }
    .status { padding:.5rem .75rem; border-radius:6px; font-weight:600; }
    .status.draft { background:#fff3cd; }
    .status.approved { background:#d4edda; color:var(--done); }
    table { border-collapse:collapse; width:100%; margin:1rem 0; }
    th,td { border:1px solid #ddd; padding:.4rem .6rem; text-align:left; vertical-align:top; }
    code,.mono { font-family: ui-monospace, monospace; }
    .note,.example,.warning,.issue { border-left:4px solid #ccc; padding:.4rem .8rem; margin:1rem 0; background:#f7f7f7; }
    .warning { border-color:#e0a800; background:#fff8e6; }
    .issue { border-color:#d33; background:#fdeaea; }
    ol.algorithm li { margin:.2rem 0; }
    ul.tasks { list-style:none; padding-left:0; }
    li.task { margin:.3rem 0; }
    li.task[data-status="done"] .task-desc { color:var(--done); text-decoration:line-through; }
    .req-refs { color:var(--muted); font-size:.85em; }
  </style>
</head>
<body>
  <h1>Specification: <!-- Change Name --></h1>
  <p class="status draft">Status: DRAFT — awaiting user approval</p>

  <section id="summary">
    <h2>1. Summary</h2>
    <p><!-- 1–2 sentences: what this change does --></p>
  </section>

  <section id="problem">
    <h2>2. Problem / Motivation</h2>
    <p><!-- why this is needed; what hurts without it --></p>
  </section>

  <section id="scope">
    <h2>3. Scope &amp; Non-Goals</h2>
    <h3>In scope</h3>
    <ul><li><!-- … --></li></ul>
    <h3>Non-Goals</h3>
    <ul><li><!-- explicit out-of-scope items --></li></ul>
  </section>

  <section id="conformance">
    <h2>4. Conformance</h2>
    <h3>Producer requirements (allowed inputs)</h3>
    <ul><li><!-- what the user/system may provide --></li></ul>
    <h3>Consumer requirements (required behavior)</h3>
    <ul><li><!-- how the software must act --></li></ul>
  </section>

  <section id="requirements">
    <h2>5. Requirements</h2>
    <table>
      <thead><tr><th>ID</th><th>Level</th><th>Requirement</th></tr></thead>
      <tbody>
        <tr id="FR-1"><td>FR-1</td><td>MUST</td><td><!-- testable assertion --></td></tr>
      </tbody>
    </table>
  </section>

  <section id="acceptance">
    <h2>6. Acceptance Criteria</h2>
    <div class="scenario">
      <p><strong>AC-1</strong> (satisfies <a href="#FR-1">FR-1</a>)</p>
      <ul>
        <li><strong>Given</strong> <!-- … --></li>
        <li><strong>When</strong> <!-- … --></li>
        <li><strong>Then</strong> <!-- measurable, binary outcome --></li>
      </ul>
    </div>
  </section>

  <section id="algorithms">
    <h2>7. Behavior / Algorithms</h2>
    <ol class="algorithm"><li><!-- step --></li></ol>
  </section>

  <section id="design">
    <h2>8. Design (How)</h2>
    <p><!-- approach in 2–4 sentences --></p>
    <pre><!-- ASCII architecture diagram --></pre>
    <h3>Key decisions</h3>
    <ul><li><strong><!-- decision --></strong>: <!-- rationale (the "why") --></li></ul>
    <h3>Security considerations</h3>
    <ul><li><!-- permissions, data flows, new deps, input handling --></li></ul>
  </section>

  <section id="team">
    <h2>9. Team &amp; Ownership</h2>
    <table>
      <thead><tr><th>Role</th><th>Agent</th><th>Responsibility</th><th>Status</th></tr></thead>
      <tbody><tr><td><!-- role --></td><td><!-- agent --></td><td><!-- … --></td><td><!-- OK / missing --></td></tr></tbody>
    </table>
  </section>

  <section id="tasks">
    <h2>10. Tasks</h2>
    <p class="progress" data-total="0" data-done="0">0 / 0 tasks complete</p>
    <h3><!-- Role --> — <!-- agent --></h3>
    <ul class="tasks">
      <li class="task" data-task-id="T1" data-status="pending" data-role="<!-- role -->"
          data-agent="<!-- agent -->" data-requirements="FR-1">
        <input type="checkbox" disabled>
        <span class="task-desc"><!-- concrete unit of work --></span>
        <span class="req-refs">(FR-1)</span>
      </li>
    </ul>
  </section>

  <section id="open-questions">
    <h2>11. Open Questions</h2>
    <!-- Must be empty before approval. While unresolved: -->
    <p class="issue"><strong>Open issue:</strong> [NEEDS CLARIFICATION: … ]</p>
  </section>

  <section id="approval">
    <h2>12. Approval</h2>
    <p>This specification requires explicit user approval before implementation.</p>
    <p><strong>Status:</strong> <span class="mono">draft</span></p>
    <p><strong>Approved by:</strong> <span class="mono">—</span> ·
       <strong>on:</strong> <span class="mono">—</span></p>
  </section>
</body>
</html>
```

---

## Approval procedure (for propose)

1. Generate `spec.html` with `aw-spec-status="draft"`.
2. Ensure the **Open Questions** section is empty (resolve every
   `[NEEDS CLARIFICATION]` with the user first).
3. Present the spec and **ask the user to approve** (AskUserQuestion).
4. On approval, edit `spec.html`:
   - `<meta name="aw-spec-status" content="approved">`
   - fill `aw-spec-approved-by` and `aw-spec-approved-at`
   - update the visible status banner to the `approved` style/text and the approval block.
5. Only then is the spec eligible for `/aw-spec-apply`.

Never flip the status to `approved` without an explicit user decision.
