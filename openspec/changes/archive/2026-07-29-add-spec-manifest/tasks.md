## 1. Manifest and Discovery Contract

- [x] 1.1 Add a stdlib-only CLI manifest module with version 1 models, bounded JSON loading,
  portable path validation, parent/home/cycle validation, and kind-aware metadata rules
- [x] 1.2 Replace the watchdog's two hard-coded spec globs with deterministic safe recursive HTML
  discovery, including visible diagnostics for rejected candidate paths and escaping files
- [x] 1.3 Add a bounded stdlib HTML-head parser for title, `aw-spec-kind`, and `aw-spec-status`, and
  use it to compute intrinsic manifest conflicts
- [x] 1.4 Add focused unit tests for nested discovery, Markdown exclusion, Windows/POSIX path edge
  cases, symlink escape, manifest size/count limits, duplicate paths, invalid home/parents, cycles,
  and kind/status compatibility

## 2. CLI and HTTP Reconciliation

- [x] 2.1 Extend HTTP transport setup and existing-config migration with a stable non-secret spec
  sync source ID
- [x] 2.2 Add the optional HTTP transport reconciliation operation and tests for valid snapshots,
  manifest read errors, authentication failures, and backward-compatible per-file uploads
- [x] 2.3 Refactor watchdog spec synchronization to track current successful file states plus an
  inventory/manifest fingerprint, publish complete snapshots, detect deletion-only changes, and
  suppress reconciliation after any incomplete upload cycle
- [x] 2.4 Extend watchdog tests for startup snapshots, unchanged polling, manifest-only changes,
  deletion, malformed manifests, partial failure/retry, and non-HTTP no-op behavior
- [x] 2.5 Extend `agentweave spec push` with manifest diagnostics, reconciliation reporting, and an
  explicit `--prune` flag while retaining clear old-Hub failure behavior
- [x] 2.6 Update CLI command/help and HTTP transport tests for named baselines, recursive paths,
  prune results, and exit codes

## 3. Hub Persistence and API

- [x] 3.1 Add the per-project/per-source spec snapshot model, active-source constants, and an
  idempotent additive migration with a safe downgrade that preserves `project_specs`
- [x] 3.2 Replace the narrow Hub spec-path regex with equivalent structured path validation and add
  bounded reconciliation request/response schemas
- [x] 3.3 Implement authenticated snapshot upsert, server-side manifest/HTML validation, active
  source comparison, drift computation, stale classification, and conflict-safe explicit pruning
- [x] 3.4 Enrich the spec-list response additively with home, effective metadata and ordering,
  missing entries, manifest state, drift diagnostics, and source conflicts while preserving
  existing document sync/get behavior
- [x] 3.5 Broadcast list-refreshable `spec_updated` events for manifest, inventory, and prune
  changes without presenting `spec/index.json` as a renderable document
- [x] 3.6 Add Hub tests for all drift categories, deterministic fallback, source expiry/disagreement,
  prune authorization and conflicts, legacy uploads, content/manifest limits, project isolation,
  SSE payloads, and migration upgrade/downgrade

## 4. Hub Spec Repair Experience

- [x] 4.1 Extend the UI spec API types and query handling for manifest-aware list data and
  reconciliation-only SSE events
- [x] 4.2 Update Spec-page selection to prefer valid manifest home, then baseline, system map, and
  effective order while preserving an available current selection
- [x] 4.3 Add a compact drift summary/details presentation that distinguishes unfiled, missing,
  orphaned/cyclic, intrinsic conflict, invalid manifest, stale row, and source conflict states
- [x] 4.4 Add the immediate `Repair manifest` trigger using the exact bounded Hub drift set,
  spec-role target preference, current session-mode behavior, and clear disabled states
- [x] 4.5 Add focused React tests for named home selection, fallback, selection continuity, drift
  rendering, repair target/message/session behavior, busy/no-agent states, and SSE invalidation

## 5. AW-Spec Skills and Role Guidance

- [x] 5.1 Add and package `aw-spec-reindex` with deterministic inventory merge, intrinsic refresh,
  semantic-field preservation, ambiguity handling, and explicit final reconciliation/prune rules
- [x] 5.2 Update propose and other spec-creating/moving skills to maintain `spec/index.json` in the
  same operation and add shared manifest support material where needed
- [x] 5.3 Remove the obsolete change-local `specs/` to `spec/specs/` merge flow from archive
  guidance and require archive moves to update manifest paths and relationships
- [x] 5.4 Make HTML conventions kind-aware for `living` versus `draft`/`approved` status and retain
  the hard approval gate only for change specs
- [x] 5.5 Lean both packaged spec-role sources to identity, boundaries, escalation, and skill
  routing; remove duplicated procedure and the invalid generated-reference path
- [x] 5.6 Update skill packaging and role-equivalence tests for Claude/Codex installation, support
  files, reindex discoverability, and behaviorally matching role copies

## 6. Documentation and Project Adoption

- [x] 6.1 Update setup detection and instructions so named baselines and manifest-based spec trees
  are recognized without creating a competing `spec/spec.html`
- [x] 6.2 Update the AW-Spec guide, CLI reference, and architecture documentation for the hybrid
  manifest, HTML-only Hub view, repair flow, explicit pruning, multi-machine behavior, and archive
  semantics
- [x] 6.3 Update the framework's behavioral HTML spec for the new manifest, sync, API, persistence,
  SSE, UI, CLI, role, and workflow contracts
- [x] 6.4 Generate this repository's initial `spec/index.json` from its baseline, system map, and
  roadmap; verify intrinsic metadata and set the named baseline as home

## 7. Integrated Verification

- [x] 7.1 Run targeted CLI/watchdog/transport/skill tests plus Hub spec, migration, auth/BOLA, and
  SSE tests; fix all regressions
- [x] 7.2 Run focused UI tests, TypeScript build, and production UI build for the Spec-page changes
- [x] 7.3 Run CLI formatting, linting, type checking, full pytest suites, and documentation build
- [x] 7.4 Exercise a live new-CLI/new-Hub sync with manifest drift and multi-source disagreement,
  confirm ordinary sync is non-destructive, then verify an explicit prune removes only true orphans
