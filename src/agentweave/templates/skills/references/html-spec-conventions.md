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

`spec.html` MUST be a single file with **inline `<style>`** (and, for the TOC/progress-bar
behavior below, a small inline `<script>`) — no external CSS/JS/CDN, so it renders
identically offline. Beyond "clean and readable," every spec must be:

- **Navigable.** Include a sticky left table-of-contents nav (one link per section,
  `href="#<section-id>"`) so the user can jump around a long spec instead of scrolling.
  Highlight the active section as the user scrolls (a small `IntersectionObserver` script
  is fine — `allow-scripts` is granted). Collapse the nav on narrow viewports. Intercept
  all `a[href="#..."]` clicks in JS and scroll manually (`scrollIntoView`) instead of
  letting the browser navigate the frame — the Hub's iframe sandbox has no
  `allow-same-origin`, and native hash navigation inside that opaque origin can blank the
  frame out until the user manually reloads it.
- **Oriented at a glance.** A sticky page header (title, status pill, and a visual task
  progress bar computed from `li.task[data-status]` counts, not just the text) stays
  visible above the content.
- **Theme-aware (light/dark).** The Hub renders `spec.html` in an iframe and stamps the
  viewer's active mode onto `<html data-theme="light">` / `<html data-theme="dark">`. The
  stylesheet MUST define colors as CSS custom properties with three layers, in this order,
  so it degrades gracefully outside the Hub too:
  1. Light-mode values on `:root` (also the default when opened as a plain file).
  2. A `@media (prefers-color-scheme: dark)` override for standalone dark-mode viewing.
  3. Explicit `:root[data-theme="light"]` / `:root[data-theme="dark"]` overrides, which win
     inside the Hub regardless of OS preference.
- **Consistent visual language.** Clear, distinct styling for `.note` / `.example` /
  `.warning` / `.issue`, colored MUST/SHOULD/MAY badges in the requirements table, and
  `.task[data-status="done"]` struck through.

See the annotated skeleton below for the exact CSS variables, layout, and script to reuse.

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
    /* 1. Light-mode defaults (also used standalone, outside the Hub) */
    :root {
      color-scheme: light dark;
      --bg:#ffffff; --surface:#f6f7f9; --surface-2:#eef0f3; --fg:#1a1a1a; --muted:#5b6472;
      --border:#e2e4e9; --accent:#2563eb; --done:#0a7f3f; --warn:#8a6400; --warn-bg:#fff3cd;
      --danger:#b3261e; --danger-bg:#fdeaea;
    }
    /* 2. Standalone dark-mode (file opened directly, OS set to dark) */
    @media (prefers-color-scheme: dark) {
      :root {
        --bg:#15171c; --surface:#1c1f26; --surface-2:#22262e; --fg:#e6e8ec; --muted:#9aa3b2;
        --border:#2a2e37; --accent:#6c9bff; --done:#3ddc84; --warn:#f0c04c; --warn-bg:#3a301a;
        --danger:#ff7a72; --danger-bg:#3a2020;
      }
    }
    /* 3. Explicit override — the Hub stamps this on <html> to match its own toggle */
    :root[data-theme="light"] {
      --bg:#ffffff; --surface:#f6f7f9; --surface-2:#eef0f3; --fg:#1a1a1a; --muted:#5b6472;
      --border:#e2e4e9; --accent:#2563eb; --done:#0a7f3f; --warn:#8a6400; --warn-bg:#fff3cd;
      --danger:#b3261e; --danger-bg:#fdeaea;
    }
    :root[data-theme="dark"] {
      --bg:#15171c; --surface:#1c1f26; --surface-2:#22262e; --fg:#e6e8ec; --muted:#9aa3b2;
      --border:#2a2e37; --accent:#6c9bff; --done:#3ddc84; --warn:#f0c04c; --warn-bg:#3a301a;
      --danger:#ff7a72; --danger-bg:#3a2020;
    }

    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0; background: var(--bg); color: var(--fg);
      font: 16px/1.6 system-ui, -apple-system, sans-serif;
      display: flex; align-items: flex-start; min-height: 100vh;
    }
    h1,h2,h3 { line-height:1.25; }
    a { color: var(--accent); }

    /* Sticky left table of contents */
    nav.toc {
      position: sticky; top: 0; align-self: flex-start; width: 220px; flex-shrink: 0;
      height: 100vh; overflow-y: auto; padding: 1.25rem 1rem; background: var(--surface);
      border-right: 1px solid var(--border);
    }
    nav.toc .toc-title { font-size:.75rem; text-transform:uppercase; letter-spacing:.05em;
      color: var(--muted); margin: 0 0 .5rem; }
    nav.toc ol { list-style:none; margin:0; padding:0; }
    nav.toc li { margin: 0; }
    nav.toc a { display:block; padding:.35rem .5rem; border-radius:6px; font-size:.85rem;
      color: var(--muted); text-decoration:none; }
    nav.toc a:hover { background: var(--surface-2); color: var(--fg); }
    nav.toc a.active { background: var(--surface-2); color: var(--accent); font-weight:600; }

    main.content { flex:1; min-width:0; max-width: 860px; margin: 0 auto; padding: 0 1.5rem 3rem; }

    /* Sticky page header: title, status, live progress bar */
    header.spec-header {
      position: sticky; top:0; z-index:2; background: var(--bg);
      padding: 1.5rem 0 1rem; border-bottom: 1px solid var(--border); margin-bottom: 1.5rem;
    }
    .status { display:inline-block; padding:.3rem .7rem; border-radius:999px; font-weight:600; font-size:.8rem; }
    .status.draft { background: var(--warn-bg); color: var(--warn); }
    .status.approved { background: var(--surface-2); color: var(--done); }
    .progress-track { height:6px; border-radius:999px; background: var(--surface-2); margin-top:.75rem; overflow:hidden; }
    .progress-fill { height:100%; background: var(--accent); width:0%; transition: width .2s ease; }
    .progress-label { font-size:.8rem; color: var(--muted); margin-top:.35rem; }

    section { scroll-margin-top: 1rem; margin-bottom: 2.5rem; }
    table { border-collapse:collapse; width:100%; margin:1rem 0; }
    th,td { border:1px solid var(--border); padding:.5rem .7rem; text-align:left; vertical-align:top; }
    th { background: var(--surface); }
    code,.mono { font-family: ui-monospace, 'JetBrains Mono', monospace; }
    pre { background: var(--surface); border:1px solid var(--border); border-radius:8px;
      padding: 1rem; overflow-x:auto; }

    .note,.example,.warning,.issue { border-left:4px solid var(--border); padding:.4rem .8rem;
      margin:1rem 0; background: var(--surface); border-radius: 0 6px 6px 0; }
    .warning { border-color: var(--warn); background: var(--warn-bg); }
    .issue { border-color: var(--danger); background: var(--danger-bg); }

    .badge { display:inline-block; padding:.1rem .5rem; border-radius:4px; font-size:.75rem;
      font-weight:700; letter-spacing:.02em; }
    .badge-must { background: var(--danger-bg); color: var(--danger); }
    .badge-should { background: var(--warn-bg); color: var(--warn); }
    .badge-may { background: var(--surface-2); color: var(--muted); }

    ol.algorithm li { margin:.2rem 0; }
    ul.tasks { list-style:none; padding-left:0; }
    li.task { margin:.4rem 0; padding:.4rem .6rem; border-radius:6px; background: var(--surface); }
    li.task[data-status="done"] .task-desc { color: var(--done); text-decoration:line-through; }
    .req-refs { color: var(--muted); font-size:.85em; }

    @media (max-width: 780px) {
      nav.toc { display:none; }
      main.content { margin: 0; padding: 0 1rem 3rem; }
    }
  </style>
</head>
<body>
  <nav class="toc" aria-label="Table of contents">
    <p class="toc-title">Contents</p>
    <ol>
      <li><a href="#summary">1. Summary</a></li>
      <li><a href="#problem">2. Problem / Motivation</a></li>
      <li><a href="#scope">3. Scope &amp; Non-Goals</a></li>
      <li><a href="#conformance">4. Conformance</a></li>
      <li><a href="#requirements">5. Requirements</a></li>
      <li><a href="#acceptance">6. Acceptance Criteria</a></li>
      <li><a href="#algorithms">7. Behavior / Algorithms</a></li>
      <li><a href="#design">8. Design (How)</a></li>
      <li><a href="#team">9. Team &amp; Ownership</a></li>
      <li><a href="#tasks">10. Tasks</a></li>
      <li><a href="#open-questions">11. Open Questions</a></li>
      <li><a href="#approval">12. Approval</a></li>
    </ol>
  </nav>

  <main class="content">
    <header class="spec-header">
      <h1>Specification: <!-- Change Name --></h1>
      <p class="status draft">Status: DRAFT — awaiting user approval</p>
      <div class="progress-track"><div class="progress-fill" data-progress-fill></div></div>
      <p class="progress-label" data-progress-label>0 / 0 tasks complete</p>
    </header>

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
          <tr id="FR-1"><td>FR-1</td><td><span class="badge badge-must">MUST</span></td><td><!-- testable assertion --></td></tr>
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
  </main>

  <script>
    // The Hub embeds this document in a sandboxed iframe (sandbox="allow-scripts",
    // no allow-same-origin -> opaque origin). Native `#hash` navigation from a click
    // on an in-page anchor can make that opaque-origin frame blank out until the
    // user manually reloads it. Intercept every same-document anchor click and
    // scroll manually instead of letting the browser navigate the frame.
    (function () {
      document.addEventListener('click', function (e) {
        var a = e.target.closest && e.target.closest('a[href^="#"]');
        if (!a) return;
        var id = a.getAttribute('href').slice(1);
        var target = id ? document.getElementById(id) : null;
        e.preventDefault();
        if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    })();

    // Live progress bar, derived from the actual task elements (not the static text).
    (function () {
      var tasks = document.querySelectorAll('li.task');
      var total = tasks.length;
      var done = document.querySelectorAll('li.task[data-status="done"]').length;
      var pct = total ? Math.round((done / total) * 100) : 0;
      var fill = document.querySelector('[data-progress-fill]');
      var label = document.querySelector('[data-progress-label]');
      if (fill) fill.style.width = pct + '%';
      if (label) label.textContent = done + ' / ' + total + ' tasks complete';
    })();

    // TOC scroll-spy: highlight the nav link for the section in view.
    (function () {
      var links = Array.prototype.slice.call(document.querySelectorAll('nav.toc a'));
      var sections = links
        .map(function (a) { return document.querySelector(a.getAttribute('href')); })
        .filter(Boolean);
      if (!('IntersectionObserver' in window) || sections.length === 0) return;
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          var link = document.querySelector('nav.toc a[href="#' + entry.target.id + '"]');
          if (!link) return;
          if (entry.isIntersecting) {
            links.forEach(function (l) { l.classList.remove('active'); });
            link.classList.add('active');
          }
        });
      }, { rootMargin: '-10% 0px -80% 0px' });
      sections.forEach(function (s) { observer.observe(s); });
    })();
  </script>
</body>
</html>
```

Notes on the skeleton:
- The TOC (`nav.toc`) and sticky `header.spec-header` are load-bearing for
  navigability — keep them even if you add or remove sections (update the TOC's `<a href>`
  list to match).
- The inline `<script>` only reads/decorates the DOM (progress bar, scroll-spy) — it never
  performs the `data-status` writes that make a task "done." Only `/aw-spec-apply` may flip
  `data-status="pending"` → `"done"`.
- Don't hardcode colors elsewhere in the document — reuse the `var(--*)` tokens so the
  light/dark override layers keep working everywhere.
- Keep the anchor-click interceptor (the first `<script>` block). It applies to *every*
  `a[href="#..."]` in the document — TOC links and inline cross-references alike (e.g.
  `<a href="#FR-1">FR-1</a>` in Acceptance Criteria) — not just the nav. Without it, the
  Hub's sandboxed iframe (`sandbox="allow-scripts"`, no `allow-same-origin`) can blank out
  on a native hash navigation and require a manual reload to recover.

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
