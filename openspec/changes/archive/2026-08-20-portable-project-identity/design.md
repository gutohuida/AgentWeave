## Context

`ProjectLifecycleService.open_existing` (`hub/hub/project_lifecycle.py:54-107`) has three cases
after canonicalizing the target directory:

1. `existing_by_path` is set — this database already has a project row bound to this exact path.
   Opens it directly.
2. `existing_by_path` is `None`, but the directory carries a marker, and this database has a
   project row for the marker's id (`marked_project is not None`). Runs `_guard_relocation`, which
   refuses if the *previously registered* directory for that id is still available (a genuine
   copy) and otherwise rebinds the existing row to the new path (a real relocation).
3. `existing_by_path` is `None`, the directory carries a marker, and this database has **no**
   project row for the marker's id (`marked_project is None`). Today this always raises
   `ProjectIdentityConflict("marked directory is a copied or orphaned project identity...")`.

Case 3 cannot occur from an ordinary single-database workflow — a marker is only ever written by
`_write_marker_and_commit`, in the same transaction as the row it names. It occurs when: (a) a
second Hub instance, pointed at a second database, opens a directory a first Hub already
registered; or (b) `delete()` removes a project's row (documented in
`openspec/changes/archive/2026-08-18-2026-08-16-delete-project-api/design.md` D4 to never touch
the filesystem) and the same directory is reopened afterward, in the *same* database, naming an id
that database no longer has.

Both are the same shape: a marker naming an id this database has zero knowledge of. The refusal
cannot distinguish "no Hub has ever created this id" from "a Hub with a different database created
it," and originally treated both as suspicious. But the thing worth being suspicious of — two
directories both claiming one id inside the *same* database — is a case-2 scenario, handled by
`_guard_relocation`, and is structurally impossible in case 3 by definition (`marked_project is
None` means this database holds no row to collide with).

## Goals / Non-Goals

**Goals:**
- Opening a directory whose marker names an id absent from the opening database succeeds, and
  results in a project usable immediately (runners and charters present), under the marker's own
  id.
- Delete-then-reopen of a project, within one Hub, restores the same id.
- Case 2's collision guard (`_guard_relocation`) is untouched, byte-for-byte.

**Non-Goals:**
- Reconciling or merging data between two databases that each hold a row for the same id. That is
  case 2 territory (both rows exist) and is out of scope here; case 3's whole premise is that the
  opening database holds no such row.
- Any operator-facing interstitial or confirmation prompt for adoption. Pre-authorised in
  `.claude/autonomous/STATE.json`: adopt silently, but leave a trace.
- Removing or altering the `register_copy_as_new` remedy shipped in `75c7685`. It remains the
  correct remedy for the case-2 refusal, which adoption does not touch.
- A persisted, queryable audit table for project lifecycle events. Out of proportion to one new
  code path; a structured log line is enough to make adoption "visible after the fact" per the
  pre-authorised note, consistent with this codebase's existing stdlib-`logging` observability
  (`CLAUDE.md` "Logging"; no project-scoped event table exists today).

## Decisions

**Adopt by constructing a `Project` row with the marker's id, then delegate to the existing seed
path.** `_seed_new_project(project)` already does exactly what a freshly adopted project needs
(default runners, starter charters, `charters_seeded = True`) and is reused unchanged — the only
difference from `case 3 is None` (brand-new project, fresh generated id) is which id the row gets:
the marker's, not `short_id()`'s.

Alternative considered: give adoption its own seeding routine so "adopted" and "created" projects
are visibly different code paths. Rejected — the two are seeded identically today (there is no
"adopted" flavor of a runner or charter), and a second routine is a second place for the seed set
to drift out of sync.

**Record adoption via `logger.info`, not a new table or column.** A single structured log line
(`event="project_adopted"`, the id, and the canonical path) is emitted at the point of adoption,
alongside the existing `_observe`/`_write_marker_and_commit` calls every other branch already
uses. This satisfies "the adoption is visible after the fact" without a migration. If the operator
later wants adoption surfaced in the UI (e.g., a badge on the project), that is a separate,
larger change with its own schema needs — flagged as an Open Question below rather than folded in
here.

**Scope the new behaviour to exactly `marked_project is None`, not to "any marker read failure."**
`_read_marker` already raises `ProjectIdentityConflict` for an unreadable or malformed marker
(lines 314-323) — that error path is untouched. Adoption only fires when the marker parses cleanly
and simply names an id absent from this database's `projects` table.

**No change to the `register_copy_as_new` parameter or its case-2 branch.** It stays exactly where
it is (`open_existing` lines 78-90 today); this change only rewrites the `else` that currently
raises for case 3.

## Risks / Trade-offs

- **[Risk] A directory that legitimately should never be reachable from a second Hub (e.g., one
  the operator does not intend to share) is silently adopted the first time that second Hub opens
  it.** → Mitigation: this is exactly the behaviour the operator asked for
  ("I should be able to open any agentweave project from any agentweave app that I want") and the
  Hub has no way to know intent beyond "this directory is being opened here." Nothing about
  adoption grants remote or network access — it requires local filesystem access to the directory,
  which is the same bar `create_new` and case 1/2 already assume.
- **[Risk] Adopting reuses the marker's id verbatim; if two unrelated Hubs happen to generate
  colliding short ids for unrelated projects (both then opened by a third Hub, or one opened twice
  against two different original databases), the "adopted" project silently merges identities that
  were never the same project.** → Mitigation: `short_id()` collision odds are the same birthday-
  problem risk `create_new` already accepts for brand-new projects; this change adds no new
  collision surface, since adoption id space is a subset of ids some Hub already minted. Not
  mitigated further here.
- **[Trade-off] A log line, not a UI-visible marker, is the only trace of adoption.** Acceptable
  per the pre-authorised note in `STATE.json`, revisit if the operator wants more.

## Migration Plan

No schema migration. Deploys as an ordinary code change to `open_existing`. Rollback is reverting
the commit — no data written by the new path is incompatible with the old refusal (the adopted
row and its seed data are indistinguishable from a row a normal `create_new`/first-open would have
produced).

## Open Questions

- Should the UI eventually surface "this project was adopted from another Hub instance" as
  something other than a log line? Deferred — see Non-Goals.
