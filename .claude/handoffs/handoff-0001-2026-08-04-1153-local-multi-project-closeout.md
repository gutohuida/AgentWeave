# Handoff 0001: Local multi-project workspace verified; spec archive remains

**Date:** 2026-08-04T11:53:41+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `4f2a776`
**Model:** gpt-5.6-sol
**Agent:** T3 Code / Codex
**Iteration commits:** unknown — predates this convention
**Previous handoff:** `.claude/handoffs/2026-08-04-1040-local-multi-project-phase5complete.md` (pre-chain, unnumbered)
**Status:** in progress

## Goal

Finish and archive the approved local multi-project workspace change so one local Hub safely owns
multiple directory-backed projects with explicit identity through APIs, runtime paths, events,
caches, navigation, and Docker containment.

## Current state

Implementation phases 0–6.5 are complete. Phase 6.4 was live-verified with a clean migrated legacy
database and two real concurrent Codex runs. Phase 6.5's complete CLI, Hub, and UI verification
matrix passes. The umbrella phase-10 reconciliation note is written but uncommitted. Task 6.6 still
needs OpenSpec's validated spec sync/archive; task 6.7 is this handoff and should be checked before
archive/closeout.

The isolated current-code Hub remains on `http://localhost:8010`, using ignored state beneath
`testbed/verify-phase6/`. The pre-existing stale Docker container remains untouched on port 8000.

## Files touched

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — uncommitted phase-10 successor reconciliation note; finished.
- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md` — phases 6.1–6.5 checked in committed history; 6.6/6.7 pending closeout.
- `hub/hub/api/v1/projects.py` — committed live directory-state refresh on collection/detail reads.
- `hub/tests/test_project_summary_live_state.py` — committed moved-directory regression contract.
- `hub/hub/static/ui/index.html` — committed current production bundle entry.
- `hub/hub/static/ui/assets/index-C1Emr8q3.js` — committed current production JS bundle.
- `hub/hub/project_lifecycle.py` — committed Ruff/Black cleanup after Docker implementation.
- `hub/hub/project_workspace.py` — committed Ruff cleanup plus stable-public-exception noqa annotations.
- `hub/tests/test_docker_workspace_root.py` — committed formatting/import cleanup.
- `hub/hub/api/v1/agent_chat.py` — pre-existing phase 0–3 dirty work; preserve.
- `hub/hub/api/v1/logs.py` — pre-existing phase 0–3 dirty work; preserve.
- `hub/hub/api/v1/setup.py` — pre-existing phase 0–3 dirty work; preserve.
- `hub/hub/api/v1/status.py` — pre-existing phase 0–3 dirty work; preserve.
- `hub/hub/db/models.py` — pre-existing phase 0–3 dirty work; preserve.
- `hub/tests/test_accounting_api.py`, `test_accounting_budget.py`, `test_agent_actions_coordination.py`, `test_agent_actions_governed.py`, `test_agent_capability_auth.py`, `test_agent_chat.py`, `test_agent_output_stream.py`, `test_agent_tool_surface_phase7.py`, `test_agents.py`, `test_agents_self_registered.py`, `test_auth.py`, `test_bola.py`, `test_charter_context.py`, `test_charters_api.py`, `test_context_usage.py`, `test_conversation_contract.py`, `test_conversations.py`, `test_inbound_queue.py`, `test_instructions.py`, `test_jobs.py`, `test_jobs_crud.py`, `test_launchability.py`, `test_mcp_server.py`, `test_messages.py`, `test_questions.py`, `test_runners_api.py`, `test_runtime_diagnostics.py`, `test_scheduler.py`, `test_spec.py`, `test_spec_reconcile.py`, `test_status.py`, `test_tasks.py` — pre-existing phase 0–3 dirty Hub tests; preserve.
- `hub/hub/migrations/versions/0026_add_project_workspace_identity.py` — untracked implemented migration from phase 0; preserve for final archival commit history.
- `hub/tests/test_operator_projects_api.py`, `hub/tests/test_project_persistence.py`, `hub/tests/test_project_workspace.py` — untracked implemented phase 0–1 tests; preserve.
- `openspec/changes/2026-08-03-local-multi-project-workspace/{proposal.md,design.md,specs/**}` — untracked approved change artifacts; archive them through OpenSpec, do not stage elsewhere first.
- `openspec/explorations/2026-08-03-local-multi-project-technical.md`, `openspec/explorations/2026-08-03-specification-authority-technical.md` — untracked approved explorations; preserve.
- `src/agentweave/templates/skills/handoff.md`, `src/agentweave/templates/skills/resume.md`, `tests/test_handoff_resume_templates.py` — untracked product-template work predating this phase; preserve.
- `.claude/handoffs/2026-08-03-2118-local-multi-project-proposed.md`, `2026-08-03-2151-local-multi-project-phase0.md`, `2026-08-03-2227-local-multi-project-phase1.md`, `2026-08-04-0009-local-multi-project-phase3b.md`, `2026-08-04-0240-local-multi-project-phase3complete.md` — old untracked handoff scratch; do not bulk-stage.
- `.claude/handoffs/2026-08-04-1153-local-multi-project-closeout.md` and `.claude/handoffs/LATEST.md` — this required durable handoff; stage explicitly for task 6.7.

## Key decisions

- Use `openspec archive -y 2026-08-03-local-multi-project-workspace` for the final sync and move;
  rejected hand-copying deltas because the CLI validates and applies MODIFIED/ADDED semantics.
- Preserve umbrella checkboxes and add a dated reconciliation note; this matches the established
  successor-reconciliation rule and avoids claiming the umbrella plan itself performed the work.
- Project summary reads now revalidate with the canonical workspace resolver and persist observation
  state; rejected returning stored state because a real moved directory stayed falsely available.
- Relocation remains guarded while a worktree is provisioned. The live scenario explicitly released
  the completed test worktree before moving/repairing; rejected bypassing the guard.
- The current-code Hub used an isolated database on port 8010; rejected using user-global native
  state or the stale port-8000 Docker image because either would contaminate or falsify evidence.

## Constraints and user directives (verbatim)

- "This repo has no AgentWeave session, and must not acquire one."
- "Do the work directly."
- "Write to `openspec/changes/<date>-<name>/`."
- "Nothing under `.agentweave/`, `agentweave.yml`, or `spec/` should exist at the repository root."
- "Stage paths explicitly. `git add -A` sweeps in untracked `.claude/handoffs/` scratch."
- "Tests open every phase; implementation does not begin until the phase's failing contract is demonstrated."
- "Commit each completed task/checkpoint without asking first."
- "Commit titles must name the actual current change (`local multi-project workspace`)."

## Dead ends

- Port 8000 served the stale five-day-old `agentweave-hub:audit` Docker container. Live verification
  moved to isolated current code on port 8010 rather than rebuilding or destroying that container.
- The first moved-directory read stayed `available`; the new regression test failed exactly there.
  `_refresh_project_observation` fixed collection and detail reads.
- Locate initially returned `project_relocation_active` because the completed writing agent's Git
  worktree was still provisioned. Releasing it after the directory had moved failed because Git
  metadata retained the old absolute path. Restoring, safely releasing, then moving again succeeded.
- `mkdocs build --strict` could not run because MkDocs is not installed.
- Bare `ruff` was unavailable; `py -3.11 -m ruff` works. Black required `--fast` under Python 3.11
  because repository target syntax includes Python 3.12 constructs.
- The production minified bundle contained trailing whitespace; scoped mechanical normalization made
  `git diff --cached --check` pass without executable changes.

## Verification

- `py -3.11 -m pytest tests -q` at repository root — 372 passed, 3 skipped.
- `py -3.11 -m pytest tests -q` in `hub/` — 598 passed, 8 skipped, 13 migration warnings.
- `npx vitest run` in `hub/ui/` — 44 files, 364 tests passed.
- `npm run build` in `hub/ui/` — passed, 2084 modules; existing duplicate-case and size warnings.
- Changed-file `py -3.11 -m ruff check ...` — passed.
- Changed-file `py -3.11 -m black --check --fast ...` — 11 files unchanged.
- `openspec validate 2026-08-03-local-multi-project-workspace --strict` — valid.
- Focused live-state/unavailable tests — 32 passed; new dedicated regression — 1 passed.
- Focused SSE/rail/settings UI tests — 14 passed.
- Live port-8010 verification — legacy bind retained `proj-default`; second project created as
  `proj-fea5a692`; concurrent runs `run-239ef1f5` and `run-cad62e27` reported distinct project
  worktrees; project switched during output; missing state and Locate repair rendered; final two
  projects available; browser used one `/api/v1/events` instance endpoint.
- Framework root check after removing one validated empty log-only artifact — `.agentweave/`,
  `agentweave.yml`, and `spec/` all absent.

Not tested: MkDocs build (dependency unavailable). Docker was configuration/unit-tested in phase
6.1 but the live closeout used native current code; the stale port-8000 container was not rebuilt.

## Git state

- Branch `hub-native-experience`; HEAD `4f2a776`; no upstream configured.
- Latest commits: `4f2a776` phase 6.5 verification, `1444dc5` phase 6.4 live verification/fix,
  `26faedf` phase 6.3 docs, `133f239` phase 6.2 cleanup, `1e0ff6a` phase 6.1 Docker.
- Dirty tree consists of the uncommitted umbrella note, this handoff/LATEST, and the preserved
  pre-existing phase 0–3 modified/untracked files itemized above.

## Next steps

1. Mark task 6.7 checked in `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md`,
   run strict validation, then execute
   `openspec archive -y 2026-08-03-local-multi-project-workspace` and inspect its exact spec/archive diff.
2. Confirm the archived task file has 6.6 and 6.7 checked; if OpenSpec moved 6.6 while pending,
   update the archived task checkbox only after confirming all three current specs contain the deltas.
3. Run `openspec validate --all --strict` (or the CLI's supported all-spec equivalent),
   `git diff --check`, and targeted current-spec searches for removed single-project wording.
4. Explicitly stage the archive/current specs, umbrella note, required handoff/LATEST, and the
   preserved phase 0–3 implementation artifacts that belong to this change; never use `git add -A`.
5. Commit the archival closeout with a title naming `local multi-project workspace`, then stop the
   isolated port-8010 process after verifying its owner. Leave the stale port-8000 Docker container untouched.

## Open questions for the user

None.

## Read on resume

- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md` — check 6.7 and archive.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — verify phase-10 reconciliation note.
- `openspec/specs/app-lifecycle/spec.md` — confirm MODIFIED requirement after archive.
- `openspec/specs/agent-conversation-workspace/spec.md` — confirm collection and URL requirements.
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/local-project-workspace/spec.md` — confirm new capability moved into current specs.
