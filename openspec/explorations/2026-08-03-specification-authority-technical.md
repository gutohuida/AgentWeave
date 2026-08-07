# Technical exploration: specification authority, identity, and traceability

**Date:** 2026-08-03  
**State:** ready to become a roadmap and first child proposal after the prerequisite below  
**Scope:** technical design only; no runtime behavior is implemented by this document

## Executive conclusion

AgentWeave should keep portable HTML files authoritative for specification meaning and use the
Hub database as a derived index plus an append-only record of work, evidence, review, and drift.
The Hub must read and write those files directly from the registered local project directory. It
must not make `ProjectSpec.content`, a browser editor buffer, or a database requirement row into a
second document authority.

The specification program is **not implementable safely against the current project model**. The
single-runtime app bootstraps one global `Project` independently of its invocation directory;
`Project` has no working-directory field. The old watchdog was also the only production caller that
discovered and pushed `spec/**/*.html`, and it has been removed. The existing Spec page therefore
reads cached `ProjectSpec` rows without a live authoritative repository producer.

The next implementation successor should be the local multi-project workspace through the point
where every project has a canonical, validated working directory and the Hub can resolve it. The
specification program can then proceed as four vertical child changes:

1. portable document authority and stable requirement identity;
2. requirement-to-work traceability, evidence, verification state, and drift;
3. rigor transitions and completion gates;
4. in-document proposals and conversational authoring.

Conversation approval panels remain a later integration over stable task and specification-gate
identities.

## Evidence from the current repository

### Two specification systems exist for different audiences

- This framework repository uses OpenSpec Markdown under `openspec/` for its own development.
- AgentWeave ships an AW-Spec workflow to user projects. It authors self-contained HTML documents
  under `spec/`, with `spec/index.json` as the navigation manifest.
- The new product capability belongs to the shipped AW-Spec/Hub system. It does not replace this
  repository's OpenSpec contributor workflow.

### Existing portable contract

`src/agentweave/templates/skills/references/html-spec-conventions.md` already defines:

- HTML as the authoritative document;
- document kinds and intrinsic `<head>` metadata;
- requirement anchors such as `FR-1`;
- task elements with `data-task-id`, `data-status`, and `data-requirements`;
- approval state and task progress inside a change document; and
- an opaque-origin iframe (`sandbox="allow-scripts"`) for safe Hub rendering.

`spec/index.json` version 1 already has a useful ownership split:

- HTML owns title, kind, and status;
- the manifest owns home, parent, and order; and
- the database stores synchronized content and per-source reconciliation snapshots.

This is the right direction, but local identifiers such as `FR-1` are not unambiguous across
documents, and the database has no requirement, revision, link, evidence, proposal, or gate model.

### Existing runtime gaps

- `hub.hub.db.models.Project` has budgets and relationships but no working directory.
- native start creates `proj-default` globally, independent of the directory from which
  `agentweave` is invoked.
- `hub/hub/api/v1/spec.py` reads `ProjectSpec.content`; it does not read repository files.
- `HttpTransport.push_spec()` and `reconcile_specs()` remain, but repository search finds only tests
  calling them after the watchdog and collaboration CLI were removed.
- `Task.requirements` is nullable untyped JSON. `TaskUpdate` cannot update it, and no foreign-keyed
  link survives identifier validation or document movement.
- the current Hub parses only `<title>`, `aw-spec-kind`, and `aw-spec-status` from HTML.

The database cache cannot become authoritative merely because its former producer disappeared.

## Domain and authority boundaries

| Information | Authority | Derived/cached elsewhere |
|---|---|---|
| Requirement wording, level, identifier, state, and document rigor | HTML document | searchable requirement index |
| Document home, parent, and order | `spec/index.json` | Hub navigation index |
| Issued and retired requirement identifiers | portable project identity ledger | database uniqueness index |
| Task lifecycle | Hub task ledger | rendered beside requirements |
| Requirement-to-task relationship | normalized Hub link record | task and requirement read models |
| Evidence, review, attribution, and gate decisions | append-only Hub records | requirement verification state |
| External file state | registered project filesystem | content hash and parsed index |
| Proposed edits | Hub proposal records until accepted | preview HTML |
| Accepted specification meaning | atomically updated HTML file | new indexed revision |

The filesystem and database participate in one model without owning the same fact. HTML says what a
requirement means. The database says what work and evidence happened against a particular observed
revision of that meaning.

## Prerequisite: directory-backed projects

The local multi-project successor must provide at least:

1. a canonical absolute working directory on every project;
2. registration from a user-selected or launch directory, with duplicate-directory detection;
3. containment-safe resolution of repository-relative paths;
4. a clear state for missing, moved, or inaccessible directories; and
5. project-scoped background services that stop or retarget when the active project changes.

The specification program should consume a `ProjectWorkspace`/path-resolver abstraction rather
than reading `Path.cwd()`. That same abstraction can serve runner workspaces, composer path search,
and future project switching.

The prerequisite need not deliver all navigation polish before specification work begins, but it
must settle directory identity and lifecycle. Smuggling `working_directory` into the specification
proposal would create two owners for the local-project contract.

## Portable document contract

### Document identity and rigor

Extend HTML intrinsic metadata with:

```html
<meta name="aw-spec-id" content="SPEC-<stable-id>">
<meta name="aw-spec-rigor" content="sketch"> <!-- sketch | contract | gate -->
```

`aw-spec-id` survives path changes. `aw-spec-rigor` is visible in the file and defaults to
`sketch`. Existing kind/status metadata remains; rigor is not a replacement for change approval.

Manifest version 2 adds the stable document ID to each document entry. Path remains the lookup key
for rendering, while document ID is the identity key for relocation and evidence links. Version 1
continues to parse and is upgraded by deterministic repair; the Hub never guesses semantic parent
relationships during upgrade.

### Requirement identity

Every normative requirement uses a project-global generated identifier, for example:

```html
<tr id="REQ-01K..." data-aw-requirement-id="REQ-01K..." data-aw-state="active">
  <td>REQ-01K...</td>
  <td><span class="badge badge-must">MUST</span></td>
  <td>The system MUST ...</td>
</tr>
```

The exact encoding should be a fixed-length, uppercase Crockford-base32 value generated from 128
bits of randomness using Python's standard-library cryptographic RNG. A human prefix makes the
identifier recognizable; random project-global identity avoids coupling it to a document, title,
or sequence. The Hub rejects duplicates before accepting a write.

Retirement is explicit rather than deletion: a retired requirement remains in a labelled retired
section with the same ID and `data-aw-state="retired"`. A small portable identity ledger under
`spec/` records every issued ID and its active/retired state so a whole-document removal cannot make
an ID reusable. The ledger contains identity and tombstones only—never requirement wording—and is
not a renderable document. The first child proposal should choose its exact filename and schema and
amend the current “no companion state” convention narrowly for this project-level invariant.

Legacy `FR-1` identifiers are reported as document-local and migration-required, not silently
treated as globally citable. Repair assigns new IDs only through an explicit preview/accept action
because the operation rewrites links and task references.

### Parsing contract

Do not infer requirements from arbitrary headings or visible prose. Define a bounded structural
profile for normative elements and validate it in both the authoring tool and Hub parser:

- one stable document ID;
- one explicit rigor value;
- unique requirement IDs;
- explicit active/retired state;
- a normative level (`MUST`, `SHOULD`, or `MAY`);
- normalized requirement text;
- explicit acceptance-criterion links; and
- explicit task references when tasks live in the document.

Malformed and unidentified content remains renderable but is excluded from verified coverage and
reported with an actionable diagnostic.

## Revision and external-edit reconciliation

### Semantic revisions

For each parsed requirement, compute a semantic digest from the fields that define meaning:

1. normative level;
2. normalized normative text;
3. linked acceptance-criterion text; and
4. explicit algorithm clauses owned by that requirement.

Normalize Unicode, line endings, and insignificant whitespace, but exclude CSS classes, layout,
derived status decoration, and proposal markup. The digest algorithm and canonicalization version
are stored with each indexed revision.

If the digest changes, existing evidence becomes stale by default. An operator may classify the
change as editorial; that decision is recorded with actor, time, old digest, and new digest, and
allows evidence to carry forward. Agents may propose the classification but cannot accept it.

### Filesystem observation

After directory-backed projects exist, the Hub owns a project-scoped spec indexer:

1. discover safe HTML files and the manifest/identity ledger beneath the registered `spec/` root;
2. reject symlink escapes and retain the current path/size/count limits;
3. parse files off the request path;
4. transact parsed document, requirement, and diagnostic updates together;
5. broadcast one project-scoped `spec_updated` event containing the affected document IDs; and
6. preserve the previous valid index if a file is temporarily malformed during an editor write.

Use `watchfiles` as an explicit Hub dependency for cross-platform rename/debounce behavior, plus a
full bounded rescan at startup and after overflow/error. A watcher notification is a hint, not the
authority; the rescan and content hash determine state.

All Hub-originated writes use a compare-and-swap content hash and an atomic same-directory replace.
If the on-disk base hash changed, acceptance returns a typed conflict and keeps the proposal for
rebase. The indexer ignores its own duplicate notification by content hash, not by a fragile timing
flag.

### Legacy cache migration

On first filesystem scan:

- a real file always wins over a `ProjectSpec.content` cache row;
- a cache row with no file is reported as recoverable legacy content and is never written into the
  repository automatically;
- the UI may offer an explicit export/recovery action after showing the target path and conflict
  status; and
- old sync/reconcile endpoints and `ProjectSpecSnapshot` are removed after the recovery window,
  rather than retained as a second ingestion architecture.

## Persistence model

Names are illustrative; the proposal should freeze exact columns and constraints.

### Derived indexes

- `spec_documents`: project, stable document ID, current path, kind, status, rigor, content hash,
  parse state, observed time.
- `spec_requirements`: project, stable requirement ID, document ID, active/retired state, current
  semantic digest, canonicalization version, anchor, observed time.
- `spec_requirement_revisions`: append-only old/new digests, source (Hub/external), classification,
  actor, observed time.

These rows never author wording. Reindexing from files can reconstruct current document state.

### Durable workflow records

- `task_requirement_links`: project, task ID, requirement ID, creator actor/run, created time. Links
  are not deleted when a task reaches a terminal state.
- `requirement_evidence`: requirement ID and semantic digest, kind, immutable artifact locator or
  bounded result payload, producing actor, producing run when applicable, produced time, review
  state.
- `evidence_reviews`: append-only acceptance/rejection decisions with operator attribution.
- `requirement_drift`: candidate, resolved, or superseded diagnostic with baseline/current artifact
  fingerprints and an attributed resolution.
- `spec_rigor_events`: append-only promotion/demotion history. The current rigor still lives in
  HTML.
- `spec_proposals` and `spec_proposal_operations`: proposer/run, base content hash, target stable
  element, before/after fragment, status, and accepter/rejecter.

Use foreign keys and project-scoped unique constraints. Replace `Task.requirements` JSON through a
migration that preserves recognizable legacy values as unresolved references until explicitly
mapped; do not drop opaque values silently.

## Derived verification and coverage

Keep lifecycle and diagnostics distinct in storage, then expose one deterministic presentation
state so document badges and project totals cannot disagree.

Recommended precedence for the primary displayed category:

1. `drifting` — an unresolved implementation-drift record exists;
2. `stale` — evidence exists but none applies to the current semantic digest;
3. `evidence_awaiting_review` — current-revision evidence exists but required review is pending;
4. `verified` — sufficient current-revision evidence is accepted;
5. `in_progress` — linked work is active or completed without evidence;
6. `not_started` — linked work exists but has not started; and
7. `unserved` — no work is linked.

Unidentified or structurally invalid requirements are diagnostics outside coverage and prevent a
gate from passing. Sketches and contracts report their state but do not block task completion.

Evidence policy must be explicit per requirement or document. An agent assertion is never evidence.
At minimum, supported evidence kinds should include test result, review record, artifact/diff,
manual observation, and external reference. Evidence always has an authenticated actor; agent
evidence also requires the live run attribution supplied by the capability plane.

## Implementation drift

“Implementation changed” can be detected; “the requirement should have changed” cannot be inferred
reliably. Treat drift as a review diagnostic, never an automatic document edit.

When a task or evidence record serves a requirement, capture the relevant implementation footprint:

- git commit and changed path/blob IDs when the workspace is a git repository;
- bounded file paths and content hashes otherwise; and
- test identifiers and result artifacts where applicable.

A later change to a linked footprint without a new requirement revision or explicit resolution
creates a drift candidate. The operator resolves it as:

- specification updated;
- implementation corrected; or
- no specification change required.

Resolution records the current requirement digest and implementation fingerprint so the same
change is not repeatedly reported. File overlap is deliberately a sensitive candidate signal, not
proof of semantic divergence.

## Rigor and gate enforcement

Rigor transitions are compare-and-swap writes to the HTML metadata plus an append-only event.
Promotion to contract or gate is refused while identifiers, duplicate references, or parse errors
remain unresolved. Demotion changes enforcement only; it retains links, revisions, evidence, and
reviews.

The completion gate belongs in the task transition service, not only in the UI:

1. resolve every requirement linked to the task;
2. select those whose current document rigor is `gate`;
3. compute state from the same query used by document badges;
4. refuse the terminal completion/approval transition when any selected requirement is not
   verified; and
5. return a typed response listing requirement IDs and reasons.

Operator UI, agent HTTP actions, MCP, and jobs must all call this same transition service. No route
may bypass it by assigning `Task.status` directly.

## In-document proposals and authoring

The canonical file does not change while a proposal is pending. A proposal is a list of independent
operations against stable element IDs and a base content hash. The Hub builds a preview document by
applying operations in memory and adding non-authoritative `<ins>`/`<del>` presentation. The opaque
iframe continues to render that preview safely.

Each operation can be accepted or rejected independently:

- rejection records the decision and leaves the file byte-for-byte unchanged;
- acceptance reparses the result, enforces identity invariants, atomically writes the file, and
  records proposer plus accepting operator; and
- conflicting operations are rebased or rejected explicitly, never last-write-wins.

Sketch behavior may auto-accept an authenticated agent proposal, but it still passes through the
same validated write service and retains attribution. Contracts and gates always require operator
acceptance.

The authoring workspace should extend the current three-pane Spec workspace rather than create a
second editor. Proposed changes appear in position in the document pane; conversation remains bound
to stable document ID and proposal set, not path. On-ramps (derive from implementation, grow from
conversation, template) produce a new sketch through the same document service.

## API and capability-plane integration

Operator APIs should be resource-oriented and project-scoped:

- list/get documents and requirements;
- retrieve coverage and diagnostics;
- create/review proposals;
- link tasks;
- attach/review evidence;
- classify revisions and resolve drift; and
- promote/demote rigor.

Agent capabilities remain intent-shaped and run-authenticated:

- read a specification/requirement needed for the current run;
- propose a requirement change;
- link current work to requirements;
- attach evidence produced by the run; and
- request verification/review.

Agents cannot accept their own evidence, approve contract/gate edits, classify their own
substantive change as editorial, or override a gate. Direct HTTP, MCP, and command adapters must
reach the same application service and retain run attribution.

## Security and failure handling

- Resolve every document path beneath the registered project `spec/` root; reject traversal,
  hidden segments, backslashes, case violations, control characters, and symlink escapes.
- Keep byte, document-count, and HTML-head bounds; add requirement-count and proposal-size bounds.
- Preserve the iframe's opaque origin. Extend its message bridge with a versioned allowlist rather
  than granting `allow-same-origin`.
- Parse and validate the complete candidate document before atomic replacement.
- Use optimistic content hashes for every mutation and database transactions for index/workflow
  updates.
- Require authenticated operator identity for acceptance, evidence review, editorial
  classification, rigor changes, drift resolution, and gate override policy changes.
- Never execute code, tests, or links merely because an HTML document or evidence record names them.
- Back up/restore the database and repository separately; the files reconstruct meaning, while the
  database preserves workflow history and evidence review.

## Delivery decomposition

### Prerequisite successor: local project directories

Deliver canonical project path registration and resolution first. Its acceptance test must launch
AgentWeave from two directories and prove every project-scoped filesystem read resolves to the
correct root.

### Child 1: portable authority and identity

- filesystem-backed document service and watcher;
- stable document/requirement IDs, identity ledger, rigor metadata;
- manifest v2 and deterministic migration/repair;
- parsed indexes and diagnostics;
- legacy cache recovery; and
- document/requirement read APIs and live refresh.

This child is demonstrable when an external edit, rename, and requirement rewrite update the Hub
without losing identity, while malformed intermediate writes preserve the last valid view.

### Child 2: traceability, evidence, and drift

- normalized task links and legacy JSON migration;
- revisions, evidence, reviews, and deterministic verification state;
- bidirectional navigation and project coverage;
- implementation footprints and drift resolution; and
- run-bound agent actions.

This child is demonstrable when requirement → task → diff/evidence and the reverse are navigable,
and a later implementation change produces a resolvable drift diagnostic.

### Child 3: rigor and completion gates

- promotion/demotion history;
- shared completion transition service;
- contract/gate evidence policy; and
- typed gate failures across operator and agent access paths.

This child is demonstrable when identical task completion succeeds for a sketch/contract but is
refused for an unsatisfied gate, then succeeds after independent evidence acceptance.

### Child 4: authoring workspace

- structured proposal operations and preview rendering;
- per-operation accept/reject/rebase;
- sketch auto-apply versus contract/gate acceptance;
- derive/conversation/template on-ramps; and
- current-interface-standard workspace polish.

This child is demonstrable when several proposed edits are previewed in position, accepted
selectively, and rejected operations leave the canonical file byte-for-byte unchanged.

### Later integration: approval gates in conversation

Surface pending task and specification decisions in the existing conversation composer only after
stable proposal, evidence-review, and gate-decision IDs exist.

## Testing strategy

| Area | Automated coverage | Manual/live verification |
|---|---|---|
| Parser and identity | property/table tests for valid, duplicate, malformed, moved, retired, legacy IDs | edit representative HTML in an external editor |
| Path safety | traversal, case, hidden, control, symlink, size/count tests on Windows and POSIX CI | open a project through a symlink/junction edge case |
| Watcher/indexer | atomic rename, burst/debounce, malformed intermediate, restart/full-rescan tests | keep Spec page open while editing and renaming files |
| Migration | Alembic upgrade/downgrade policy, legacy JSON/cache fixtures, idempotent reindex | migrate a copied pre-change database/repository |
| Revisions/evidence | canonicalization vectors, editorial/substantive classification, actor/run constraints | inspect stale and accepted evidence in the document |
| Coverage/gates | one shared state matrix exercised through service, REST, agent HTTP, MCP, and jobs | attempt completion from operator and live agent |
| Drift | git and non-git fingerprint fixtures, resolution idempotence | change linked code and observe/resolve candidate |
| Proposals | independent operations, conflict/rebase, byte-identical rejection, attribution | accept some of several edits in the rendered document |
| UI | React tests for badges, navigation, proposal controls, SSE invalidation, keyboard/a11y | full authoring workflow at narrow and wide widths |

Run focused suites during each child, then the complete CLI, Hub, and UI suites, production UI
build, strict OpenSpec validation, and `git diff --check` before archive. Live verification must use
a throwaway directory, never create AgentWeave state at this framework repository root.

## Deployment, migration, and rollback

- One or more Alembic migrations are required for directory-backed projects and specification
  workflow records.
- `watchfiles` is the only proposed new dependency; it is justified by cross-platform filesystem
  semantics and should be explicit rather than relied on as an optional uvicorn transitive.
- No new network service, secret, port, or remote reconciliation protocol is needed.
- Database migrations should be additive through children 1–3. Remove obsolete cache/snapshot
  tables only after explicit legacy recovery has shipped and been live-verified.
- File writes are git-visible and revert normally. Database workflow history is not reconstructed
  from git, so rollback must retain or migrate evidence/review rows rather than dropping them.
- Documentation must distinguish repository OpenSpec from the user-facing AW-Spec product and
  explain file/database backup boundaries.

## Execution strategy

This repository deliberately has no AgentWeave session and must not acquire one. Implementation is
therefore direct repository work, not delegation through shipped `aw-*` commands. The useful
ownership boundaries for future review are:

1. project/path lifecycle and security boundary;
2. HTML parser, identity, canonicalization, and persistence;
3. task/evidence/gate application services and migrations;
4. Spec workspace and proposal UX; and
5. independent zero-trust review of gate bypasses, attribution, and migration fixtures.

The parser/application contracts must land before UI work. Proposal preview UI may proceed after
the structured operation schema is frozen. Gate review must be performed separately from its
implementation because a false pass defeats the capability's purpose.

## Decisions rejected

- **Database-authored specification text:** rejected because it creates a competing source and
  makes external edits/import/export lossy.
- **Continue client push/reconcile as the normal local architecture:** rejected because there is one
  local runtime with filesystem access; it adds stale-source conflicts without a second machine.
- **Path plus `FR-1` as identity:** rejected because relocation and cross-document citation break it.
- **Renumber requirements on move:** rejected because every task, commit, conversation, and evidence
  reference would decay.
- **Infer requirements from arbitrary HTML:** rejected because verification and gates require a
  strict, testable machine contract.
- **Treat any file edit as proven semantic drift:** rejected because it creates false claims;
  footprint change is a diagnostic requiring deliberate resolution.
- **Mutate canonical HTML to show pending proposals:** rejected because rejection could not guarantee
  byte-identical restoration and external editors would observe unaccepted meaning.
- **UI-only gate enforcement:** rejected because agent HTTP, MCP, jobs, and future clients could
  bypass it.
- **Implement the specification program as one change:** rejected because authority, traceability,
  gating, and authoring are independently demonstrable and carry different migration risks.

## Open questions for proposal review

- [ ] Confirm the project-level issued/retired identifier ledger filename and exact versioned JSON
      schema. The need for a portable tombstone ledger is resolved; only its concrete contract is
      open.
- [ ] Decide whether accepted evidence is sufficient by default for contracts, or whether each
      document declares an evidence policy. Gates necessarily require accepted evidence.
- [ ] Define the bounded evidence payload/locator formats and retention limits without turning the
      database into an artifact store.
- [ ] Decide whether non-git implementation footprints are required in child 2 or may follow after
      the git-backed path, while preserving an explicit “unavailable” state.
- [ ] Set the legacy cache recovery window and removal milestone for `ProjectSpecSnapshot` and the
      dead sync/reconcile endpoints.

None of these questions blocks the local project-directory prerequisite. The first specification
child proposal must resolve the identity-ledger contract before approval; the remaining questions
belong to the child that consumes them.

## Ready for the next proposal

Do **not** propose the full specification program next. Propose the local multi-project workspace
first, with canonical directory ownership as a traced requirement. After it is approved and
implemented, create a shallow specification-program roadmap and propose child 1, “portable
specification authority and identity,” using this document as its technical design source.
