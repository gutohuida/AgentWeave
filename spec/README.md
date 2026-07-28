# AgentWeave Specification Map

**Navigation only — the specifications themselves are the HTML files below.** Every spec in
this project is a single self-contained HTML document (inline CSS/JS, no external
resources), so it can be opened offline in a browser, reviewed by a human, embedded in the
Hub's spec viewer, and parsed for its machine-readable attributes. This file is a
non-normative index; if it ever disagrees with a spec, the spec wins.

```text
spec/
├─ system-map.html                         # durable scope, domains, ownership, shared contracts
├─ roadmaps/
│  └─ agentweave-reconstruction.html       # rebuild slices, boundaries, dependencies
├─ agentweave-spec.html                    # detailed living behavioral baseline
├─ changes/<name>/spec.html                # one approved change (via /aw-spec-propose)
└─ discovery/<name>/                       # optional idea.md / technical.md notes
```

`spec/` is the single root for every spec artifact. The `aw-spec-*` skills and the Hub
spec sync (`_discover_spec_files`) both resolve paths under it; there is no `specs/`.

| Document | Holds | Changes when |
|---|---|---|
| [`system-map.html`](system-map.html) | System intent, durable constraints (`SM-C-*`), bounded contexts, shared contracts (`SM-K-*`), rules for child specs (`SM-R-*`) | A boundary, constraint, or contract changes |
| [`roadmaps/agentweave-reconstruction.html`](roadmaps/agentweave-reconstruction.html) | Vertical slices `R1`–`R6` with in/deferred boundaries, dependencies, status, child-spec links | A slice is added, split, started, or completed |
| [`agentweave-spec.html`](agentweave-spec.html) | The detailed living behavioral baseline (CLI, transport, MCP, Hub, UI) | Specified behavior changes |
| `spec/changes/<name>/spec.html` | One approved change: requirements, acceptance criteria, design, tasks, approval state | Per change, via `/aw-spec-propose` |

For new work, create a shallow epic roadmap first when the request contains multiple
independently demonstrable outcomes. Each roadmap row has a stable ID, intent, explicit
in/deferred boundary, dependencies, status, and a link to its own approved change spec under
`spec/changes/<name>/spec.html`. Do not split by frontend/API/database layer.

The roadmap owns the division of scope. A child spec owns the requirements, acceptance
criteria, design, and tasks for exactly one vertical capability. Shared interfaces live in
the system map or a versioned contract referenced by both sides.
