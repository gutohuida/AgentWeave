## MODIFIED Requirements

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
- **AND** unsafe HTML candidates produce a visible CLI diagnostic

---

### Requirement: Invalid or absent manifests degrade visibly

Manifest absence, unreadability, malformed JSON, excessive size, or semantic invalidity MUST NOT
prevent safe HTML content from synchronizing. The Hub SHALL retain the source's inventory and
manifest state, classify its documents as unfiled when no valid structure is available, and expose
the actionable error.

The system MUST bound manifest bytes and document count before parsing or persistence.

#### Scenario: Manifest JSON is temporarily malformed

- **WHEN** a synchronization pass reads malformed `spec/index.json`
- **THEN** safe HTML documents continue to synchronize
- **AND** the Hub reports the malformed manifest without replacing it with invented structure

## REMOVED Requirements

### Requirement: Synchronization publishes a complete source snapshot

**Reason**: This requirement describes the watchdog's poll loop and manual `spec-push` submitting
reconciliation snapshots. Single-runtime (`openspec/changes/single-runtime`) deletes the watchdog
and the `spec-push` command; neither actor exists to submit a snapshot. This is an accepted
regression, not a redesign — `aw-spec-workflow`'s sync mechanism has no replacement in this change.

**Migration**: None. A locally-running Hub already has direct filesystem access to its project's
`spec/` directory and does not need anything synced to it — but building that replacement is real
design work left to the specification-program slice (see
`openspec/explorations/2026-08-02-product-direction.md`, "the specification program moves up in
priority"), not invented here.

### Requirement: Reconciliation is safe across multiple machines

**Reason**: Multi-source reconciliation existed for the cross-machine case (git transport, several
checkouts syncing to one Hub). Single-runtime deletes `transport/git.py` and the watchdog; there is
exactly one machine and one source, so there is nothing to reconcile between.

**Migration**: None. If a future federation slice reintroduces multiple sources synchronizing to one
Hub, this requirement (or its replacement) is reinstated at that point.
