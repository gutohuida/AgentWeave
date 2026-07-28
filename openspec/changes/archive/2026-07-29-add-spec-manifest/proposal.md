## Why

The spec authoring workflow now produces baselines, system maps, roadmaps, active changes, and
archived changes throughout `spec/`, but the watchdog and Hub accept only `spec/spec.html` and
`spec/changes/<slug>/spec.html`. Valid agent-authored documents therefore disappear from the Hub
without an error, while deleted or renamed documents remain there indefinitely.

This is actively worsening as the improved AW-Spec skills create more document shapes. The current
repository already demonstrates the failure: its baseline is `spec/agentweave-spec.html`, alongside
`spec/system-map.html` and `spec/roadmaps/agentweave-reconstruction.html`, and none is discoverable
under the current root-spec contract.

## What Changes

- Add a versioned, agent-maintained `spec/index.json` manifest that declares the default document
  and the ordered parent/child structure of every Hub-visible HTML spec.
- Discover every safe `spec/**/*.html` document independently of the manifest, so absent or invalid
  manifest entries degrade to visible drift rather than silent data loss.
- Reconcile the complete filesystem inventory with the Hub and expose unfiled, missing, orphaned,
  conflicting, invalid-manifest, and stale-row diagnostics.
- Make removal explicit and multi-machine-safe: ordinary synchronization marks stale rows but does
  not delete them; a deliberate repair or `agentweave spec push --prune` may prune after a complete,
  successful reconciliation.
- Enrich the Hub spec-list contract with manifest metadata, an explicit home document, and drift
  diagnostics while preserving existing per-document sync and fetch compatibility.
- Add a one-click Hub repair action that sends the computed drift set to a suitable spec agent.
- Add an `aw-spec-reindex` repair skill and require AW-Spec authoring/archive skills to maintain the
  manifest as documents are created, moved, or archived.
- Lean the spec role to routing and boundaries, leaving authoring procedure in skills; correct
  obsolete setup, archive-library, metadata-status, and fixed-`spec/spec.html` guidance.
- Keep Markdown discovery notes agent-facing; this change does not add Markdown rendering to the
  Hub.

## Capabilities

### New Capabilities

- `spec-manifest-sync`: Safe recursive HTML discovery, manifest validation and reconciliation,
  Hub persistence and diagnostics, explicit pruning, home-document selection, and agent-assisted
  drift repair.

### Modified Capabilities

- `aw-spec-workflow`: AW-Spec skills and the spec role maintain the manifest consistently, provide
  a reindex repair workflow, and use the correct document-kind metadata and archive conventions.

## Impact

- CLI/watchdog: `src/agentweave/watchdog.py`, the `agentweave spec push` command, and spec-sync
  retry/state tracking.
- Transport: the optional HTTP spec-sync operations and their backward-compatible payloads.
- Hub backend: project-spec API schemas/endpoints, `ProjectSpec` persistence plus a migration,
  metadata parsing, reconciliation, pruning authorization, and SSE refresh events.
- Hub UI: enriched spec API types, manifest-aware default selection, drift presentation, and the
  repair trigger. Tree navigation, cross-document navigation, and responsive layout remain in the
  later `add-spec-navigation` change.
- Agent guidance: packaged AW-Spec skills, both packaged spec-role sources, support-file generation,
  setup/archive instructions, framework spec, and workflow documentation.
- Tests: watchdog discovery/reconciliation, transport compatibility, API validation and
  multi-project isolation, migration coverage, skill packaging, and focused UI behavior.
- No new CLI runtime dependency is introduced; filesystem, JSON, HTML metadata, and HTTP handling
  continue to use the Python standard library.
