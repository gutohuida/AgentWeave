## Context

Spec synchronization is currently a per-file cache:

```text
watchdog: two hard-coded globs
        -> POST /project/specs/sync {path, content}
        -> ProjectSpec upsert
        -> GET /project/specs returns a flat path list
```

That protocol cannot describe which document is primary, express roadmap/change relationships,
report a manifest entry whose file is missing, or learn that a formerly uploaded file was deleted.
Its narrow path regex also conflicts with the AW-Spec role and skills, which produce system maps,
roadmaps, named baselines, and archives elsewhere beneath `spec/`.

The Hub is explicitly multi-machine. Several watchdogs may synchronize the same project from
different checkouts, so a naive "latest full inventory wins" design would let a stale checkout
delete content uploaded by another machine. The CLI must retain zero runtime dependencies, and spec
sync failures must remain isolated from the watchdog polling loop.

This design treats Hub content as a recoverable projection of repository files, the HTML document
as the source of intrinsic metadata, and `spec/index.json` as the source of semantic navigation.

## Goals / Non-Goals

**Goals:**

- Synchronize every safe HTML spec without making manifest correctness a visibility prerequisite.
- Give the Hub a versioned, validated document forest with an explicit home document.
- Make drift complete, visible, and repairable from the Spec page.
- Detect deletions while preventing one stale machine from deleting another machine's content.
- Keep current sync/fetch clients working and preserve watchdog retry behavior.
- Keep manifest maintenance reliable by separating mechanical reindexing from semantic curation.

**Non-Goals:**

- Rendering Markdown discovery notes in the Hub.
- Building the shell navigation tree, command palette, iframe cross-document bridge, or responsive
  layout; those belong to `add-spec-navigation`.
- Changing the HTML iframe security model or document authoring format.
- Making the Hub write repository files directly.
- Adding Git as a correctness dependency or requiring all workspaces to share a branch/commit.
- Automatically resolving an ambiguous missing file or semantic parent.

## Decisions

### 1. Use a hybrid, versioned manifest

Version 1 uses this logical shape:

```json
{
  "version": 1,
  "home": "spec/agentweave-spec.html",
  "documents": [
    {
      "path": "spec/agentweave-spec.html",
      "title": "AgentWeave — Canonical Regeneration Specification",
      "kind": "baseline",
      "status": "living",
      "parent": null,
      "order": 10
    }
  ]
}
```

HTML owns `title`, `kind`, and `status`, because those values travel with and govern the document.
The manifest caches them so a missing document can still be identified. The manifest owns `home`,
`parent`, and `order`, because those relationships are project semantics and cannot be derived
reliably from a directory name.

`aw-spec-reindex` performs the mechanical merge: scan files, parse HTML metadata, retain entries,
refresh intrinsic fields, and add new entries deterministically. An agent then maintains or repairs
semantic relationships. Normal watchdog synchronization is read-only and never rewrites the tree.

Alternatives rejected:

- Fully generated manifest: deterministic but destroys semantic roadmap relationships.
- Fully hand-maintained manifest: repeats file and metadata facts and predictably drifts.
- Filesystem hierarchy alone: cannot express a named baseline or roadmap-to-change relationship.
- HTML links alone: non-exhaustive and may drift; they remain useful in-document navigation.

### 2. Validate paths as structured POSIX paths, not one permissive regex

A shared stdlib-only helper validates normalized paths segment by segment and is used by discovery,
manifest validation, the manual command, and Hub request schemas. The Hub remains the security
boundary and repeats validation even when the CLI already validated.

Discovery walks `spec/**/*.html` in sorted order. Candidate files must be regular safe files and
resolve beneath the canonical `spec/` root. Unsafe candidates are skipped with a structured event
and manual-command warning. The manifest is separately bounded (proposed defaults: 256 KiB and
1,000 documents) before JSON parsing.

The HTML metadata parser uses `html.parser.HTMLParser`, stops after `</head>`, and extracts
`<title>`, `aw-spec-kind`, and `aw-spec-status`. This avoids new dependencies and avoids regex-based
HTML parsing.

Alternatives rejected:

- Relaxing `SPEC_PATH_RE` to `^spec/.*\.html$`: accepts ambiguous separators and traversal-like
  segments and does not protect local reads.
- Manifest-only discovery: recreates silent loss whenever the agent forgets an entry.

### 3. Add a source snapshot protocol beside existing file upserts

Per-file content remains on the existing endpoint and under the existing 2 MiB limit. A new
reconciliation operation carries:

```text
source_id
manifest_text | manifest_read_error | absent
discovered_paths[]
prune: false | true
```

The HTTP transport receives an optional `reconcile_specs` operation. A stable random `source_id`
is generated during HTTP transport setup (and lazily for existing configurations), stored in the
gitignored transport configuration, and contains no credential or machine-identifying path.

The watchdog tracks successful file state plus an inventory/manifest fingerprint. It sends a
snapshot at startup and whenever the inventory or manifest changes, but only after every current
discovered file matches a successful upload marker. Deleted paths therefore cause reconciliation
even though no content upload occurs. Any stat, read, or upload failure suppresses reconciliation
for that cycle and remains retryable.

`agentweave spec push` uses the same orchestration and adds `--prune`; it prints manifest and
reconciliation diagnostics rather than only an upload fraction.

Alternatives rejected:

- Batch-upload every document: request size scales with the whole tree and makes one bad file
  reject otherwise valid updates.
- Extend each file upsert with the manifest: repeats large state, cannot reliably signal a complete
  inventory, and creates ordering races.
- Infer deletion from timestamps: the Hub has no filesystem view and cannot distinguish offline
  sources from deletion.

### 4. Store per-source snapshots separately from document content

Keep `project_specs` as the content cache and add a `project_spec_snapshots` table:

```text
project_id       composite primary key, foreign key
source_id        composite primary key
manifest_content nullable text
manifest_state   bounded string (valid | absent | unreadable | invalid)
inventory        JSON list of validated paths
diagnostics      JSON list
updated_at       timestamp/index
```

The migration is additive. Missing manifest documents do not require nullable fake
`ProjectSpec.content` rows; list responses are computed by joining manifest entries, content rows,
and active inventories.

Snapshots newer than a named constant (proposed five minutes, comfortably above normal polling and
the current 120-second heartbeat stale threshold) are active. The effective navigation structure
comes from the newest valid active snapshot. Other active snapshots are compared and disagreements
are returned as source-conflict diagnostics. A stored document is stale only when no active
inventory or active valid manifest claims it.

An ordinary reconciliation never deletes. `prune=true` deletes only stored paths claimed by no
active inventory and no active valid manifest. If active sources disagree, claimed paths are
preserved and returned as prune conflicts. This permits legacy orphan cleanup without allowing
last-writer-wins deletion.

Alternatives rejected:

- Add manifest columns to `ProjectSpec`: cannot represent missing files or per-source disagreement
  without fake content rows.
- One project-wide snapshot: whichever machine polls last becomes destructively authoritative.
- Never prune: safe but leaves renamed paths permanently misleading.

### 5. Enrich the list response additively

The existing `{"specs":[{"path","updated_at"}]}` shape remains valid. Additive response data
includes:

```text
home
manifest {state, version, source_id, updated_at}
specs[] {path, updated_at, title, kind, status, parent, order, state}
missing[]
diagnostics[] {code, path?, field?, expected?, actual?, source_ids?}
```

Available content remains in `specs`; missing manifest entries are returned separately so the
current UI never selects a row that must 404. Effective ordering is `order`, then path. A valid home
is preferred; fallback is available baseline, available system map, then first effective document.

The Hub computes diagnostics rather than trusting a client-provided result. Invalid raw manifest
text is retained only as bounded snapshot state so the UI can identify and repair the actual error.
Document GET behavior remains unchanged.

### 6. Reuse `spec_updated` for document and manifest changes

Continue the existing project-scoped SSE event. Reconciliation-only events omit `path` and include a
reason such as `manifest`, `inventory`, or `prune`; clients invalidate the list and only invalidate a
specific document query when a renderable HTML path is present. This avoids teaching clients to
fetch `spec/index.json` as a document.

### 7. Keep Change 1 UI deliberately small

Change 1 adds:

- manifest-aware home selection and enriched API types;
- a compact drift summary/details area;
- state labels in the existing selector where practical;
- one `Repair manifest` action.

The action prefers an idle agent with the `spec` role, otherwise uses the currently selected agent.
It calls the existing trigger endpoint immediately with a bounded message containing diagnostic
codes and paths plus an instruction to invoke `aw-spec-reindex`. It follows the existing Spec-page
new/resume session control. It is disabled while no target is eligible.

The navigation tree and layout redesign stay out of this change even though they consume this
contract later.

### 8. Put procedure in skills and routing in the role

Add `src/agentweave/templates/skills/aw-spec-reindex.md`; top-level skill discovery automatically
packages it for Claude and Codex. Update propose/archive and any other path-mutating AW-Spec skills
to maintain the manifest. Bundle shared manifest conventions as a support file where multiple
skills need the exact schema.

Reduce both spec-role sources to identity, durable ownership boundaries, approval/escalation, and
skill routing. Remove the broken direct reference to a generated `references/` path and duplicated
HTML procedure. Tests compare the two packaged role copies.

The archive workflow moves the HTML change and updates the manifest. Its leftover
`spec/changes/<name>/specs/ -> spec/specs/` merge guidance is removed, along with the corresponding
documentation claim. Setup detects any safe HTML/manifest tree rather than only `spec/spec.html`.

## Risks / Trade-offs

- **[Active-source expiry temporarily marks offline-only content stale]** → Content is never deleted
  by ordinary sync; use a conservative named TTL and show source recency.
- **[Two active manifests disagree about home or structure]** → Use the newest valid snapshot for
  presentation, report the disagreement prominently, and forbid pruning claimed paths.
- **[Agent repair removes intentional historical information]** → Missing entries require evidence
  or user confirmation; reindex does not blindly discard them.
- **[Manifest is read during a partial agent write]** → Continue syncing HTML, retain the bounded
  invalid snapshot and error, and repair on the next poll; no destructive action follows invalid
  state.
- **[Recursive discovery uploads unexpectedly large archives]** → Keep the existing per-file limit,
  bound manifest entries, use mtime/fingerprint deltas, and leave archive filtering to navigation.
- **[Case-sensitive behavior differs between Windows and Unix]** → Enforce lowercase portable paths
  at both producer and Hub boundaries.
- **[New CLI against an old Hub rejects newly shaped paths]** → Fail visibly and retry; new Hub/old
  CLI remains compatible. Cross-version feature support cannot be made symmetric without changing
  the old server.
- **[Generated role/skill copies in an existing project remain stale]** → Package source changes and
  document regeneration through the normal `agentweave activate`/initialization flow.

## Migration Plan

1. Add the snapshot model and idempotent migration; deploy the Hub while retaining all existing
   `project_specs` rows and endpoints.
2. Broaden safe path acceptance, add reconciliation, enrich list responses, and broadcast
   manifest-only refreshes. Existing rows initially appear unindexed and are not deleted.
3. Add transport `source_id`, reconciliation support, recursive discovery, and manual `--prune`.
   Existing HTTP configurations lazily receive a source ID without exposing credentials.
4. Add the manifest-aware UI and repair action.
5. Add `aw-spec-reindex`, update authoring/setup/archive guidance, lean the role, and update docs.
6. Create this repository's initial `spec/index.json` through the repair workflow and run a
   non-pruning sync. Review diagnostics, then explicitly prune legacy orphan rows.

Rollback disables the new UI/reconciliation client while leaving the additive snapshot table in
place. Existing per-file sync/list/get behavior continues to work. The migration downgrade may drop
only `project_spec_snapshots`; it must not drop `project_specs` content.

## Open Questions

None blocking. The active-source TTL and manifest byte/document limits are named implementation
constants whose proposed defaults must be covered by boundary tests and may be tuned without
changing the external contract.
