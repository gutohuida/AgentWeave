# Handoff: Legacy roles removed; final verification and docs next

**Date:** 2026-08-03T19:00:00+01:00 · **Branch:** hub-native-experience · **HEAD:** 1513314
**Agent:** Codex gpt-5.6-sol (T3 Code)
**Previous handoff:** `.claude/handoffs/2026-08-03-1806-runner-registry-complete.md`
**Status:** phase 4 complete; continue with phase 5

## Goal

Complete the `runner-agent-charter-separation` OpenSpec successor and then close the remaining
Hub-native-experience umbrella work. Runner, Agent, and Charter are now separate Hub-owned records.

## Completed in this chunk

- Re-ran the legacy caller audit. It found design-time drift in diagnostics, Hub role-sync storage
  and endpoints, self-registration, role-derived agent summaries, and frontend role badges/spec
  selection.
- Deleted `src/agentweave/roles.py`, `src/agentweave/context_builder.py`, their tests, CLI role
  templates/helpers/constants, role sync from Session/HTTP transport, and the obsolete AgentConfig
  `roles` field.
- Removed Hub `ProjectRolesConfig`, `/agents/roles/config`, `role_request`, dev-role response fields,
  file fallback loaders, and role-based frontend presentation/selection.
- Added Alembic 0025 to drop `project_roles_config` from upgraded databases.
- Moved the unchanged 21 starter documents from `hub/hub/data/roles/` to
  `hub/hub/data/charters/` and replaced the old role metadata with a charter-only seed manifest.
- Reconciled agent-context specs so provisional and machine-readable contracts describe charters,
  not roles.
- Marked OpenSpec phase 4 complete with evidence and committed as `1513314`.

## Verification

- CLI: 349 passed, 3 skipped.
- Hub: 489 passed, 4 skipped.
- Frontend: 286 passed.
- Frontend production build passed; existing duplicate-case and chunk-size warnings remain.
- Ruff passed on all changed Python files.
- `openspec validate --all --strict`: 21/21 passed.
- Zero imports/callers remain for `roles.py`, `context_builder.py`, `VALID_ROLE_IDS`,
  `ROLES_CONFIG_FILE`, or `ROLES_DIR`.

## Next actions

1. Execute OpenSpec phase 5.1–5.3: final regressions, live verification in `testbed/`, strict spec
   validation.
2. Update `AGENTS.md` and `CLAUDE.md` to remove the multi-role deprecation section and accurately
   document Runner/Agent/Charter architecture and current module layout.
3. Archive `runner-agent-charter-separation` and annotate the umbrella task 16.2.
4. Run final verification, update tasks, commit, and write the final handoff.

## Constraints

- This framework repository must not acquire root `agentweave.yml`, `.agentweave/`, or `spec/`
  state. Exercise product commands only inside `testbed/` or another throwaway subdirectory.
- Preserve these unrelated untracked files and never stage them:
  - `src/agentweave/templates/skills/handoff.md`
  - `src/agentweave/templates/skills/resume.md`
  - `tests/test_handoff_resume_templates.py`
- Stage paths explicitly; never use `git add -A`.
- The user explicitly requested continuation in this same session after checkpoints.

## Resume prompt

Continue phase 5 of `openspec/changes/runner-agent-charter-separation/tasks.md` from commit
`1513314`. Start with the live testbed verification, then docs, archive/umbrella annotation, final
regressions, and final handoff. Preserve the three unrelated untracked handoff/resume files.
