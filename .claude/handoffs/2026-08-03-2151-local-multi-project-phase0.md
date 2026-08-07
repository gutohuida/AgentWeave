# Handoff: Local multi-project workspace phase 0 complete

**Date:** 2026-08-03T21:51:57+01:00 · **Branch:** hub-native-experience · **HEAD:** 37a6854
**Agent:** Codex gpt-5.6-sol (T3 Code)
**Previous handoff:** `.claude/handoffs/2026-08-03-2118-local-multi-project-proposed.md`
**Status:** chunk complete — approved change, phase 0 implemented and verified

## Goal

Implement the approved local multi-project workspace change so one local AgentWeave instance can
own multiple directory-backed projects without filesystem, authentication, event, or frontend-state
leakage. Phase 0 establishes the stable directory identity and lifecycle foundation required by
all later API, CLI, runtime, and UI phases.

## Current state

- The user explicitly approved
  `openspec/changes/2026-08-03-local-multi-project-workspace/` for implementation.
- Phase 0 tasks 0.1 through 0.8 are checked complete in `tasks.md`; phases 1–6 remain pending.
- `Project` now has nullable legacy directory bindings, a unique canonical `path_key`, a constrained
  observation state, and last-opened/last-seen timestamps.
- A separate project-free `OperatorCredential` model/table exists. Migration 0026 copies the
  surviving bootstrap secret without deleting or changing the legacy project-scoped API key.
- `project_workspace.py` owns platform-semantic canonical keys, rejection of unsafe roots/data/
  worktree paths, typed unavailable/conflict errors, marker validation, and contained relative-path
  resolution.
- `project_lifecycle.py` implements idempotent open, bounded create, guarded relocation, copied
  marker refusal/explicit replacement, first-open legacy binding, atomic marker rollback, and
  default runner/starter-charter seeding for genuinely new projects.
- The complete Hub suite and all strict OpenSpec validation pass. No phase-1 API/auth work has
  started.

## Files touched

- `.claude/handoffs/LATEST.md` — updated pointer; finished after this handoff is written.
- `.claude/handoffs/2026-08-03-2118-local-multi-project-proposed.md` — inherited untracked proposal
  handoff; unchanged during implementation.
- `.claude/handoffs/2026-08-03-2151-local-multi-project-phase0.md` — this phase handoff; finished.
- `hub/hub/db/models.py` — added project directory fields/state constraint and instance-scoped
  `OperatorCredential`; phase-0 portion finished.
- `hub/hub/db/engine.py` — registers/seeds operator credentials for fresh and in-memory databases;
  phase-0 portion finished.
- `hub/hub/migrations/versions/0026_add_project_workspace_identity.py` — adds fields, unique path
  index, operator table, and bootstrap-secret migration; finished.
- `hub/hub/project_workspace.py` — new canonical path/workspace resolver and typed errors; finished
  for phase 0, to be consumed across later phases.
- `hub/hub/project_lifecycle.py` — new marker/open/create/relocate lifecycle service; finished for
  phase 0, with API integration pending phase 1.
- `hub/tests/test_migrations.py` — advanced head assertions from 0025 to 0026; finished.
- `hub/tests/test_project_persistence.py` — new model, constraint, bootstrap, and upgrade tests;
  finished.
- `hub/tests/test_project_workspace.py` — new canonicalization, alias, boundary, escape, and resolver
  tests; finished.
- `hub/tests/test_project_lifecycle.py` — new marker/open/create/relocate/rollback/seeding tests;
  finished.
- `openspec/changes/2026-08-03-local-multi-project-workspace/proposal.md` — approved proposal;
  unchanged this phase.
- `openspec/changes/2026-08-03-local-multi-project-workspace/design.md` — approved design;
  unchanged this phase.
- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md` — phase 0 checked complete;
  phases 1–6 pending.
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/local-project-workspace/spec.md`
  — approved primary delta; unchanged this phase.
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/app-lifecycle/spec.md` — approved
  lifecycle delta; unchanged this phase.
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/agent-conversation-workspace/spec.md`
  — approved navigation delta; unchanged this phase.
- `openspec/explorations/2026-08-03-local-multi-project-technical.md` — inherited technical source;
  unchanged this phase.
- `openspec/explorations/2026-08-03-specification-authority-technical.md` — inherited later-programme
  source; unchanged this phase.
- `src/agentweave/templates/skills/handoff.md` — protected pre-existing untracked user-owned file;
  not read or modified.
- `src/agentweave/templates/skills/resume.md` — protected pre-existing untracked user-owned file;
  not read or modified.
- `tests/test_handoff_resume_templates.py` — protected pre-existing untracked user-owned file; not
  read or modified.

## Key decisions

- Directory states are `unbound`, `available`, `missing`, `unreadable`, `not_directory`, and
  `identity_conflict`; rejected a nullable/loosely typed observation because unavailable projects
  need stable, testable diagnostics.
- Canonical keys are prefixed with host semantics (`windows:` or `posix:`). Windows folds case and
  separators; POSIX preserves case. Rejected path-derived project IDs because relocation must retain
  all foreign identity.
- A bound workspace must carry the exact versioned marker `{version, project_id}`. Rejected silently
  repairing missing/conflicting markers inside the resolver because that could adopt a copied tree.
- Opening an unmarked directory binds exactly one unbound legacy project; explicit Create always
  creates a genuinely new project. This preserves migration continuity without consuming legacy
  history for a user-requested new directory.
- A copied marker is refused while its registered directory exists. Explicit register-copy-as-new
  replaces only the copy's marker and creates new database identity.
- Lifecycle writes the marker before committing the database and restores/removes it on failure;
  rejected presenting a committed project with a failed marker as ready.
- The operator secret has its own table and no `project_id`. The old `ApiKey` remains temporarily
  for route compatibility until phase 1 migrates operator consumers; rejected nullable project IDs
  as implicit administrator privilege.

## Constraints and user directives (verbatim)

- “This repo has no AgentWeave session, and must not acquire one.”
- “Do the work directly.”
- “Write to `openspec/changes/<date>-<name>/`.”
- “Nothing under `.agentweave/`, `agentweave.yml`, or `spec/` should exist at the repository root at
  all.”
- “Also: stage paths explicitly. `git add -A` sweeps in untracked `.claude/handoffs/` scratch.”
- User command starting this session: “$resume”.
- User approval: “approve”.
- Preserve `src/agentweave/templates/skills/handoff.md`,
  `src/agentweave/templates/skills/resume.md`, and
  `tests/test_handoff_resume_templates.py` unless their owner asks otherwise.
- Do not invoke shipped `aw-*` product skills against this framework repository.
- Before each new phase, re-read the proposal, design, all three delta specs, and tasks; tests must
  demonstrate the phase contract before implementation.

## Dead ends

- The bare `black` command and `python -m black` are unavailable in this environment; `ruff` is also
  not installed. Formatting was checked manually for changed files, and Python compilation passed.
- A first Windows raw-string test ended in a backslash and caused a syntax error; it was corrected
  to an escaped normal string before the expected red test was recorded.
- Directory symlink/junction tests skip on this Windows environment when link creation lacks the
  required privilege. The canonical alias behavior still has deterministic pure Windows/POSIX key
  tests and ordinary path-alias coverage.
- PowerShell continues after an unavailable command unless explicitly guarded; do not treat a later
  successful pytest exit code as proof an earlier formatter ran.

## Verification

Ran and passed after the final changes:

- `pytest hub/tests -q` — 522 passed, 6 skipped, 13 Alembic deprecation warnings.
- `pytest hub/tests/test_project_persistence.py hub/tests/test_project_workspace.py hub/tests/test_project_lifecycle.py hub/tests/test_migrations.py -q`
  — 48 passed, 3 skipped, 11 Alembic deprecation warnings.
- `openspec validate --all --strict --no-interactive` — 21 passed, 0 failed.
- `openspec validate 2026-08-03-local-multi-project-workspace --strict --no-interactive` — valid.
- `python -m compileall -q hub/hub hub/tests` — passed.
- `git diff --check` — passed with no output.
- Test-first red runs were observed before the model/migration, operator bootstrap, workspace module,
  and lifecycle module implementations.

Not tested:

- Black, Ruff, and mypy were not run because the formatter/linter modules are not installed.
- No CLI, frontend, browser, Docker, PostgreSQL, live native runtime, or `testbed/` verification was
  run; those belong to later phases.
- Windows directory symlink/junction live cases were skipped where the OS denied link creation.
- No phase-1 operator project routes, auth migration, or route parity exists yet.

## Git state

- Branch: `hub-native-experience`.
- HEAD: `37a6854` (`handoff: runner agent charter separation complete`).
- Worktree: dirty with the phase-0 tracked modifications and untracked new files listed above; no
  files are staged and no commit was created.
- `git diff --stat HEAD` reports 88 insertions and 6 deletions only for tracked files; the lifecycle,
  workspace, tests, migration, proposal, explorations, and handoffs are untracked and therefore not
  included in that statistic.
- Upstream: none (`origin/hub-native-experience` is unavailable), so unpushed comparison cannot be
  determined.
- No root `.agentweave/`, `agentweave.yml`, or `spec/` state was created.

## Next steps

1. Re-read `proposal.md`, `design.md`, all three delta specs, and `tasks.md`, then implement task 1.1
   test-first in a new `hub/tests/test_operator_projects_api.py`: prove one `OperatorCredential`
   lists all projects, explicit project route IDs isolate resources, unknown IDs fail, and run
   credentials cannot select a different project.
2. Add shared operator authentication and explicit project resolver dependencies, then collection,
   open/create/get/settings/relocate routes using `ProjectLifecycleService`.
3. Move operator resource routers under `/api/v1/projects/{project_id}/...` with response-parity
   tests before changing frontend consumers.
4. Complete phase 1 settings/bootstrap cleanup and verification, check only proven tasks, then write
   the required phase-1 handoff.

## Open questions for the user

None. The approved design has no open choices; discoveries that alter it require a revision and
renewed approval.

## Read on resume

- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md` — exact phase-1 order and
  test-first protocol.
- `openspec/changes/2026-08-03-local-multi-project-workspace/design.md` — auth/API boundaries and
  rejected compatibility shortcuts.
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/local-project-workspace/spec.md`
  — operator collection, isolation, and settings scenarios.
- `hub/hub/db/models.py` — completed persistence shape, legacy `ApiKey`, and new
  `OperatorCredential`.
- `hub/hub/project_lifecycle.py` — service phase-1 routes must call rather than reimplement.
- `hub/hub/auth.py` — current project-derived operator authentication to replace in phase 1.
