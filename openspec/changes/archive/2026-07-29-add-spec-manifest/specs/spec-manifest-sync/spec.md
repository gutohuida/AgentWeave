## ADDED Requirements

### Requirement: Spec discovery covers every safe HTML document

The CLI SHALL recursively discover regular `.html` files beneath the repository's `spec/`
directory without requiring a manifest entry. A discoverable path MUST be a normalized,
lowercase, repository-relative POSIX path no longer than the Hub path limit, MUST begin with
`spec/`, MUST contain no empty, dot, dot-dot, hidden, control-character, or backslash segment, and
MUST resolve within the `spec/` root.

The CLI MUST NOT treat `spec/index.json`, Markdown discovery notes, or any other non-HTML file as a
Hub-renderable spec. It MUST report unsafe candidate files rather than silently accepting them.

#### Scenario: Nested HTML documents are discovered

- **WHEN** the spec tree contains a baseline, system map, roadmap, active change, and archived
  change at safe nested HTML paths
- **THEN** discovery returns every one of those HTML paths in deterministic path order

#### Scenario: Manifest omission does not hide a file

- **WHEN** a safe HTML file exists beneath `spec/` but is absent from `spec/index.json`
- **THEN** the CLI still synchronizes the file
- **AND** reconciliation reports it as unfiled

#### Scenario: Unsafe and non-HTML files are not rendered

- **WHEN** discovery encounters Markdown notes, an escaping symlink, a hidden path, a path with a
  traversal segment, or a non-HTML file
- **THEN** none is uploaded as a Hub spec
- **AND** unsafe HTML candidates produce a visible CLI or watchdog diagnostic

### Requirement: The manifest has a versioned structural contract

`spec/index.json` SHALL contain `version`, `home`, and `documents`. Version 1 documents MUST declare
`path`, `title`, `kind`, `status`, `parent`, and integer `order`.

`home` MUST reference exactly one manifest document. Document paths MUST be unique and satisfy the
safe spec-path contract. `parent` MUST be null or reference another manifest document, MUST NOT
reference the document itself, and the parent graph MUST be acyclic. Valid kinds MUST be
`baseline`, `system-map`, `roadmap`, or `change-spec`. A baseline, system map, or roadmap MUST use
status `living`; a change spec MUST use `draft` or `approved`.

#### Scenario: A valid manifest describes a document forest

- **WHEN** a version 1 manifest has unique safe documents, a valid home, compatible kind/status
  pairs, and an acyclic parent graph
- **THEN** the manifest is accepted
- **AND** sibling presentation order is determined by `order` with path as a deterministic tie-break

#### Scenario: Invalid structure is diagnosed

- **WHEN** the manifest has an unsupported version, duplicate path, invalid home, unsafe path,
  incompatible kind/status, unknown or self parent, or parent cycle
- **THEN** reconciliation reports a specific manifest diagnostic for every detected violation
- **AND** the invalid structure is not treated as authoritative navigation

### Requirement: HTML owns intrinsic metadata and the manifest owns relationships

For an existing document, its HTML `<title>`, `aw-spec-kind`, and `aw-spec-status` metadata SHALL be
the authoritative intrinsic values. The manifest SHALL cache those values so missing documents
remain intelligible and SHALL own `home`, `parent`, and `order`.

The Hub MUST compare cached intrinsic values with the corresponding HTML and report conflicts. A
repair operation MUST refresh intrinsic manifest values from valid HTML while preserving valid
semantic relationships.

#### Scenario: Intrinsic metadata drifts

- **WHEN** an existing document's title, kind, or status differs from its manifest entry
- **THEN** the Hub reports each differing field as a conflict
- **AND** the repair workflow refreshes the manifest value from the HTML document

#### Scenario: A manifest entry references a missing file

- **WHEN** a valid manifest document has no matching discovered HTML file
- **THEN** its cached title, kind, status, parent, and order remain available for diagnostics
- **AND** it is reported as missing rather than silently removed

### Requirement: Synchronization publishes a complete source snapshot

After synchronizing changed documents, an HTTP watchdog or manual spec push SHALL submit a
source-identified reconciliation snapshot containing the manifest text or manifest-read error and
the complete set of discovered safe HTML paths.

The client MUST submit the snapshot only after every discovered file is known to match a
successfully uploaded version for the current file state. A failed read, stat, or upload MUST
prevent that cycle from authorizing reconciliation or pruning and MUST be retried without breaking
the watchdog poll loop.

#### Scenario: Initial watchdog synchronization

- **WHEN** an HTTP watchdog starts with unchanged spec files already on disk
- **THEN** it uploads every discovered document
- **AND** submits a complete reconciliation snapshot after all uploads succeed

#### Scenario: A document upload fails

- **WHEN** at least one discovered document cannot be read or uploaded
- **THEN** its successful-state marker is not advanced
- **AND** the client does not submit a snapshot that could classify or prune against the incomplete
  upload set
- **AND** a later poll retries the operation

#### Scenario: A document is deleted

- **WHEN** a previously synchronized document disappears from the discovered inventory
- **THEN** the next complete snapshot records its absence even though no file upload occurs

### Requirement: Reconciliation is safe across multiple machines

Each HTTP workspace SHALL use a stable, non-secret sync-source identifier, and the Hub SHALL retain
the latest reconciliation snapshot per project and source. The Hub MUST treat recently updated
source snapshots as active and MUST surface conflicting active inventories or manifests rather than
silently treating the last writer as globally authoritative.

Ordinary synchronization MUST NOT delete stored document content. A document absent from every
active complete inventory MAY be classified as stale. A prune request MUST delete only rows absent
from every active complete inventory and every active manifest; it MUST refuse or report a conflict
rather than deleting a path claimed by another active source.

#### Scenario: An older checkout omits a newer document

- **WHEN** two active sources disagree and one source still reports a document
- **THEN** ordinary reconciliation does not delete or classify that document as globally absent
- **AND** the Hub reports the source disagreement

#### Scenario: Explicit prune removes a true orphan

- **WHEN** an authenticated user or repair workflow requests pruning after a complete successful
  snapshot and no active inventory or manifest claims a stored path
- **THEN** the Hub deletes that orphaned row
- **AND** returns the paths it pruned

#### Scenario: Explicit prune encounters an active claim

- **WHEN** a prune request omits a path that another active source still claims
- **THEN** the Hub preserves the path
- **AND** reports why it was not pruned

### Requirement: Invalid or absent manifests degrade visibly

Manifest absence, unreadability, malformed JSON, excessive size, or semantic invalidity MUST NOT
prevent safe HTML content from synchronizing. The Hub SHALL retain the source's inventory and
manifest state, classify its documents as unfiled when no valid structure is available, and expose
the actionable error.

The system MUST bound manifest bytes and document count before parsing or persistence.

#### Scenario: Manifest JSON is temporarily malformed

- **WHEN** the watchdog reads malformed `spec/index.json`
- **THEN** safe HTML documents continue to synchronize
- **AND** the Hub reports the malformed manifest without replacing it with invented structure

#### Scenario: No manifest exists

- **WHEN** a project has safe HTML specs but no `spec/index.json`
- **THEN** all synchronized documents remain available
- **AND** the list response reports manifest absence and marks the documents unfiled

### Requirement: The Hub exposes manifest-aware spec state

The project spec list API SHALL remain backward compatible with existing `path` and `updated_at`
entries while adding the effective home path, intrinsic and structural metadata, manifest validity,
drift diagnostics, source conflicts, missing entries, and stale stored rows.

The Hub SHALL compute at least these diagnostics: unfiled discovered file, missing manifest file,
unknown parent, parent cycle, intrinsic metadata conflict, invalid manifest, stale stored row, and
active source conflict. Project authentication and isolation MUST apply to documents, snapshots,
diagnostics, reconciliation, and pruning.

#### Scenario: Existing client lists specs

- **WHEN** an existing client reads the enriched list endpoint
- **THEN** every available document still includes its existing `path` and `updated_at` fields
- **AND** additive manifest fields do not require the client to change

#### Scenario: Project diagnostics are isolated

- **WHEN** two projects synchronize identical paths with different manifests
- **THEN** each project sees only its own documents, snapshots, metadata, diagnostics, and prune
  results

### Requirement: Home-document selection is explicit and resilient

The Hub UI SHALL select the valid manifest `home` document by default. If no valid home is
available, it SHALL deterministically fall back to an available baseline, then an available
system map, then the first available document by effective order and path.

The UI MUST preserve a user's current selection while that document remains available.

#### Scenario: Repository uses a named baseline

- **WHEN** the manifest declares `spec/agentweave-spec.html` as home
- **THEN** the Spec page opens that document without requiring `spec/spec.html`

#### Scenario: Home document is unavailable

- **WHEN** the declared home is missing or invalid
- **THEN** the Spec page uses the deterministic fallback
- **AND** exposes the home diagnostic instead of failing to render all other specs

### Requirement: Users can trigger manifest repair from the Hub

The Spec page SHALL visibly summarize manifest drift and provide one repair action. When a suitable
agent is available and idle, activating the action SHALL immediately send that agent a repair
request containing the Hub-computed drift set and instructing it to use `aw-spec-reindex`.

The action SHALL prefer an agent with the `spec` role, fall back to the currently selected Spec-page
agent, and be disabled with an explanation when no target is available or the target cannot accept
the request.

#### Scenario: User repairs visible drift

- **WHEN** the Hub reports manifest drift and an idle spec agent is available
- **THEN** one activation sends that agent the exact computed drift categories and paths
- **AND** the request resumes the agent's most recent session unless the existing Spec-page session
  control explicitly requests a new one

#### Scenario: Repair cannot currently run

- **WHEN** no eligible agent exists or the selected target is busy
- **THEN** the repair action does not enqueue an ambiguous request
- **AND** the UI explains why the action is unavailable

### Requirement: Spec synchronization remains backward compatible

The Hub SHALL continue accepting the existing per-document sync operation and serving the existing
per-document fetch operation. A new Hub MUST accept legacy `spec/spec.html` and
`spec/changes/<slug>/spec.html` clients, and documents uploaded without a reconciliation snapshot
MUST remain available as unindexed content.

The CLI and HTTP transport MUST add no runtime dependency outside the Python standard library.

#### Scenario: Legacy CLI uploads a spec

- **WHEN** a legacy CLI uploads an accepted document without a manifest or source snapshot
- **THEN** the new Hub stores and serves it
- **AND** lists it as unindexed rather than rejecting it

#### Scenario: New synchronization uses the existing content limit

- **WHEN** a document exceeds the established per-file byte limit
- **THEN** the Hub rejects that document without accepting a reconciliation snapshot that assumes
  the file was stored

### Requirement: Spec state changes refresh subscribers

The Hub SHALL broadcast a project-scoped spec update after document content, reconciliation state,
or prune results change. The event contract MUST allow clients to invalidate the spec list without
attempting to fetch `spec/index.json` as a renderable document.

#### Scenario: Manifest-only reconciliation changes

- **WHEN** parent ordering, home, or drift state changes without HTML content changing
- **THEN** subscribed UI clients invalidate and refresh their manifest-aware spec list
