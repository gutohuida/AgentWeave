# Design — corpus-aware documents

## Context

Three things are already true, and the design is mostly a matter of not fighting them.

1. **The manifest is the portable record of shape.** `spec/index.json` is *"the only record of the
   corpus's home, hierarchy and ordering that survives the project being copied to another machine"*
   (`hub/hub/api/v1/spec.py:1049-1053`). It already holds `parent` and `order`.
2. **`parent` is a validated document reference.** Not a label, not a group name — a path that must
   name another entry in the same manifest. `spec_manifest.py:256-258` emits `manifest_unknown_parent`
   for a target that is not in the index, `:240-241` refuses self-parenting, and `:270` detects
   cycles. The tree machinery is built. It has never had data.
3. **A rendered document is self-contained by rule.** `render_document`'s docstring:
   *"A self-contained document: inline style only, no external resource."* Every one of the 35 files
   opens correctly in a bare browser with no Hub running.

Fact 2 has a consequence worth stating early: because `parent` names a *document*, a grouping
heading must itself be a document. There is no way to express "these ten belong together" without
something for them to belong to. That is not a limitation to route around — it is what keeps the
hierarchy meaningful, and it is why this design introduces area documents rather than a group
string.

## Goals

- A reader who opens any single `.html` file, in the app or in a bare browser, can reach the home
  document and the document above it.
- A reader who opens the home document sees every capability in the project, grouped, with a line
  saying what each one is.
- The map cannot go stale, because nobody maintains it.
- Adding one document does not rewrite the corpus.

## Non-goals

- Rendering the hierarchy in the rail (`SpecTree` stays a file tree).
- Cross-references between arbitrary documents. This is a tree, not a graph.
- Deriving structure from anything the operator did not state.

## Decisions

### D1 — The map is rendered into the file, not injected by the viewer

**Rejected:** having `SpecFrame`/`SpecDocumentPanel` overlay navigation and a map from `GET /specs`
at view time. It is cheaper, touches no files, and creates no re-render problem at all.

**Chosen:** render it in.

The corpus's value is that it is 35 committed, self-contained files that reproduce anywhere. That is
the same principle the operator stated for adoption — *"this is something that gets committed and
can be reproduced anywhere in any environment"* — and it is why `render_document` refuses external
resources in the first place. A map that exists only inside the running app is absent exactly when
the corpus is being read the way corpora are usually read: on GitHub, in a diff, in a browser, on a
machine with no Hub.

The cost of this choice is re-rendering, and D2 is what makes that cost small.

### D2 — Navigation is home and parent; a map renders only where there are children

This is the load-bearing decision of the change.

The obvious design gives every document a full navigation strip — home, parent, and siblings. It is
also the design that makes adding one capability document rewrite all thirty-five files, because
every sibling's sibling list changed. That is a corpus-wide diff for a one-document edit, repeated
forever.

Bounding navigation to **home and parent** makes a document's navigation strip depend only on its
own manifest entry. It changes when *that document's* parent changes, and at no other time.

Bounding the map to **documents that have children** means a new capability re-renders exactly one
other file: its area document. Adding an area re-renders exactly one: the home.

```
  add spec/capabilities/new-thing/spec.html under "Agents and execution"

  D2 (chosen)                         full sibling lists (rejected)
  ───────────                         ────────────────────────────
  areas/agents-and-execution.html     all 35 files
  = 1 file re-rendered                = 35 files re-rendered
```

Sibling navigation is not lost, only indirect: the parent link goes to the area map, which lists
every sibling. One extra click, in exchange for a corpus that does not churn.

### D3 — Hierarchy comes from the manifest, and setting it is an operator act

`parent` is read from `spec/index.json`, the same source `build_index` already preserves. No column,
no migration, no second copy to disagree with the first.

Setting it needs a route, because today nothing can. `POST /project/spec/documents/arrange` takes a
path and a parent path (or `null` to unparent), validates against the manifest's existing rules, and
rewrites the index. It is the operator's: a document's place in the corpus is an editorial judgement
about what the project *is*, which is exactly the category of decision `build_index` already refuses
to make on the operator's behalf.

**Rejected:** a `parent` field on the payload, set by whoever writes the document. It would let an
agent place its own document in the corpus, and it would put the arrangement in two places — the
payload and the manifest — with no rule for which wins.

### D4 — The initial hierarchy is authored once, by hand, into `spec/index.json`

Operator, asked where the structure should come from: *"You can read them and generate it on your
own. Those files were derived from openspec and the code. So until it's all set and done and I'm
using them we can edit them as we see fit."*

So the arrangement below is derived by reading all 35 documents, written into the manifest once, and
preserved by `build_index` from then on. It is data, and the operator can rearrange it with D3's
route or by editing the file.

```
spec/agentweave.html                          home · system-map
├── Agents and execution                      10 documents
│     agent-capability-plane · agent-tool-surface · agent-charter ·
│     agent-configuration · agent-context-onboarding · agent-context-usage ·
│     agent-run-sandboxing · operator-agent-creation · runner-registry ·
│     model-catalog
├── Conversations                              7 documents
│     agent-composer · agent-conversation-workspace ·
│     agent-conversation-handoff · agent-stream-events ·
│     conversation-checkpoint · conversation-lifecycle ·
│     conversation-side-panel
├── Specification                              3 documents
│     spec-document-authority · spec-chat-session · requirement-traceability
├── Work and traceability                      4 documents
│     task-lifecycle-governance · run-task-binding · agent-loops ·
│     trace-timeline
├── The local instance                         8 documents
│     app-lifecycle · local-project-workspace · project-environment-settings ·
│     project-instructions* · opencode-config · runtime-diagnostics ·
│     usage-accounting · quiet-hours*
└── Interface                                  2 documents
      hub-workspace-shell · hub-interaction-feedback
```

`*` — no row today, so `build_index` cannot file them. They join when `document-adoption` lands.
Thirty-two of the thirty-four capabilities are placeable now.

The six area documents are **new** documents, so `POST /project/documents` — which mints a row and
writes a starter file — is the correct way to create them. This change therefore does **not** depend
on `document-adoption` for its own machinery, only for the two orphans above.

### D5 — The renderer is generic over depth; the arrangement is two levels

`render_document` receives children and one parent. It does not know or care whether it is the home,
an area, or a leaf. A three-level arrangement would work without a code change, because depth lives
in the data.

Two levels is what ships because it is what the operator described — *"the general gist of the
features and navigate between the deep dive on the other files"* — and because a flat list of
thirty-two is the shape they already called thin.

### D6 — Re-rendering is driven from the file's own payload

To re-render a document the Hub needs its payload. It does not need the database: `extract_payload`
reads the embedded `id="aw-spec-payload"` block back out of the file
(`hub/hub/spec_payload.py:297`), and all 35 documents carry one, verified.

So reindex re-renders by reading the file, extracting the payload, re-rendering with fresh corpus
context, and writing. This works identically for documents the Hub created and documents that
arrived by clone, and it keeps the re-render path off `save_document` — which would otherwise emit a
`content` event attributing an editorial change to whoever triggered reindex, and would refuse
outright on an approved document.

**A document with no readable payload is skipped and reported**, not guessed at, consistent with
`extract_payload` returning `None` rather than inventing.

### D7 — A Hub-initiated re-render updates the stored digest

`save_document` stores `content_digest` on write, and `POST /spec/drift/detect` reports a file whose
content no longer matches. Re-rendering changes file bytes. Without this decision, every reindex
would leave the corpus reporting itself as drifted, and the drift signal would become noise within
one cycle.

The Hub wrote it, so the Hub records it. The re-render updates the digest and records an event of
its own kind — `rerendered` — so the document history distinguishes "the Hub refreshed the generated
region" from "somebody changed what this document says". Documents with no row have no digest to
update, and are simply re-rendered.

### D8 — A missing summary is stated, not blank

The map shows each child's title and a one-line summary drawn from its payload. Eight of the
thirty-five cannot supply one:

| | documents |
|---|---|
| empty `summary` | `agent-context-usage`, `agent-loops`, `agent-stream-events`, `local-project-workspace`, `opencode-config`, `requirement-traceability` |
| placeholder text | `model-catalog`, `runtime-diagnostics` — both still say *"TBD - created by syncing change … Update Purpose after archive"* |

A blank cell reads as a rendering bug. The map says *"no summary yet"* in the muted style the
renderer already uses for `aw-empty`, which turns an invisible content gap into a visible one — the
same reasoning that made an empty open-questions list render as "None outstanding" rather than
vanish (`spec_render.py:301-304`).

Filling those eight in is content work, not code, and it is listed as a task rather than smuggled
into the renderer.

## Risks

**Re-render churn.** Bounded by D2, but the bound is a claim about which files a reindex touches,
and claims like that decay. The test asserts the exact touched set, not just that the map is right.

**A first reindex after this ships re-renders everything once.** Every document gains a navigation
strip, so every file changes. That is a single large diff, expected and reviewable, and it happens
once.

**Authored narrative and generated region share a file.** The map is appended as its own section
below the authored content, in a region the renderer owns entirely. Nothing merges the two, so there
is no conflict to resolve — but an operator editing `spec/agentweave.html` by hand outside the app
would have their map edits silently overwritten on the next reindex. The generated section is
labelled as generated for that reason.

## Migration plan

1. Renderer accepts corpus context and emits both regions, defaulting to none — every existing
   caller keeps working and produces byte-identical output.
2. Reindex assembles context and re-renders. At this point the corpus gains navigation but the
   hierarchy is still flat, so every document's parent link points at home.
3. The arrange route lands.
4. The six area documents are created and given their narrative.
5. The hierarchy from D4 is authored, one reindex regenerates all six area maps and the home.

Steps 1–2 are useful on their own: even a flat corpus with a home link on every page is better than
thirty-five islands.

## Open questions

- **Should the home's map list every document recursively, or only its direct children?** Direct
  children means the home shows six area names and a reader clicks once more to see capabilities.
  Recursive means the home is the whole map and the area pages are nearly redundant. The operator's
  *"overview of the entire project there"* leans recursive; D2's cost argument does not apply, since
  the home re-renders whenever anything anywhere is added either way. **Recommendation: recursive on
  the home, direct children elsewhere** — but this is a real fork and it is the operator's.
- **Does the navigation strip belong above the title or below the meta chips?** Presentation, and it
  wants seeing rather than deciding.
- **Should an area document be `system-map` kind, or does the corpus want a new kind?** `system-map`
  fits and is already valid (`spec_payload.py:43`). A new kind would need adding in two places that
  have diverged before (`spec_manifest.py:27-30` records exactly that having happened with
  `capability`). **Recommendation: `system-map`.**
