## Why

An operator running more than one AgentWeave Hub on a machine (for example, a trial instance
alongside the desktop app's own instance) cannot open the same project directory from the second
Hub. `ProjectLifecycleService.open_existing` in `hub/hub/project_lifecycle.py` refuses with
"marked directory is a copied or orphaned project identity" whenever a directory's marker names a
project id that the opening database has never seen — even though nothing in that database
collides with it. The same refusal also breaks delete-then-re-add of a project in a single Hub:
`delete()` is documented to never touch the filesystem (`openspec/changes/archive/2026-08-18-2026-08-16-delete-project-api/design.md`
D4), so the marker survives a delete and the very next open of that same directory hits this
refusal, on the same database, for a project id it deleted seconds ago.

When this refusal was written there was no way to tell "no one has ever seen this id" apart from
"an unreachable database owns this id," so both were refused identically as a safety margin. That
distinction turns out not to matter: the only thing the refusal was protecting against — two
registered directories claiming the same project id in the same database — is enforced elsewhere,
by `_guard_relocation` (`hub/hub/project_lifecycle.py:190-208`), which fires whenever this
database *does* hold a project row for the marker's id and the two directories collide. This
proposal narrows the refusal to exactly the cases that remain genuinely ambiguous.

## What Changes

- `open_existing`'s third case — the marker names a project id absent from the opening database,
  and no project in that database is already bound to this path — stops refusing and instead
  **adopts** the id: it creates the project row using the marker's own id (not a freshly generated
  one), seeds it the same way `_seed_new_project` seeds a brand-new project (default runners plus
  the starter charter set), records an adoption event distinguishable from ordinary creation, and
  opens it.
- Case 2 — the marker names a project id this database already has a row for — is unchanged.
  `_guard_relocation` still refuses a genuine copy whose original directory remains available, and
  still allows relocation when it is not.
- Delete-then-re-add of a project within one Hub now restores the same project id, because the
  surviving marker is adopted rather than refused.
- **Non-Goal:** merging or reconciling project *data* (tasks, runs, conversations) between two
  databases that both happen to hold a row for the same id. Adoption only ever runs where the
  opening database has zero rows for that id — there is nothing to merge.
- **Non-Goal:** any change to `_guard_relocation` or to the "marker was copied" refusal it
  produces. That scenario (`openspec/specs/local-project-workspace/spec.md` scenario "A marker was
  copied") is untouched by this proposal.
- **Non-Goal:** the operator-facing `register_copy_as_new` remedy shipped in `75c7685` is not
  removed. It still applies to the case-2 collision, which adoption does not eliminate.

## Capabilities

### Modified Capabilities

- `local-project-workspace`: the "Projects have stable directory-backed identity" requirement
  gains an explicit adoption scenario for an orphaned marker (case 3), narrowing what counts as an
  identity conflict to the case the marker's project id is already held by this database
  (case 2, unchanged).

## Impact

- `hub/hub/project_lifecycle.py`: `open_existing`'s case-3 branch (currently lines 86-90) changes
  from raising `ProjectIdentityConflict` to constructing and seeding a `Project` row keyed by the
  marker's id.
- New adoption event, recorded the same way other project lifecycle observations are recorded, so
  the adoption is visible in the project's history even though the operator sees no interstitial
  (an explicit product decision recorded in `.claude/autonomous/STATE.json` `pre_authorised`: adopt
  silently, but leave a trace).
- No API contract change: `POST` open-existing-directory already returns a `Project`; it now
  returns one with a pre-existing id in a path that previously errored.
- No database migration: adoption inserts a `Project` row through the existing `Project` model,
  using the id read from the marker instead of a freshly generated one.
