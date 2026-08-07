# Handoff: Local multi-project workspace phase 1 complete

**Date:** 2026-08-03T22:27:34+01:00  
**Branch:** `hub-native-experience`  
**HEAD:** `37a6854a1920bfd0028ab01433caf7b24df80d5d`  
**Previous handoff:** `.claude/handoffs/2026-08-03-2151-local-multi-project-phase0.md`  
**Status:** chunk complete - approved change phases 0 and 1 implemented and verified

## Goal

Implement the approved local multi-project workspace change so one local AgentWeave instance can
own multiple directory-backed projects without filesystem, authentication, event, or frontend-state
leakage. Phase 1 establishes instance-operator authentication, explicit project resource routes,
project collection/lifecycle APIs, and validated project settings.

## Current state

- Tasks 0.1-1.7 are complete in the approved change. Phases 2-6 remain pending.
- `OperatorCredential` is now the only operator authentication source. Legacy project `ApiKey`
  credentials no longer authenticate operator routes; run-scoped credentials retain their separate
  capability boundary.
- Operator resources live only below `/api/v1/projects/{project_id}/...`. The implicit global
  resource routes were deliberately removed, per the specification's no-compatibility-shortcut
  rule.
- The new project API lists safe summaries for every project, opens/creates/gets/relocates projects,
  and reads/updates validated name and budget settings.
- Setup bootstrap returns the instance credential without selecting a project or falling back to a
  legacy project credential.
- The full Hub suite passes after all existing API tests were migrated to explicit project routes.
- The frontend is intentionally an intermediate mismatch: it still calls the removed implicit
  resource routes until phase 4 migrates API clients, query keys, selection state, and SSE.
- A full Hub test run created untracked `.agentweave/context/*.md` files at the framework root via
  existing `Path.cwd()` runtime behavior. They were inspected and removed. Phase 3 explicitly owns
  replacing these project-related cwd paths with `ProjectWorkspace` and adding two-repository tests.

## Phase 1 implementation

- `hub/hub/auth.py` now separates instance operator authentication from explicit project lookup.
  `get_operator_project()` validates a requested project, while request-derived project dependencies
  require a `project_id` path parameter. SSE tickets are checked against the explicit project.
- `hub/hub/api/v1/projects.py` adds collection/open/create/get/settings/relocate endpoints, typed
  lifecycle errors, safe live-agent summaries, constrained settings validation, and scheduler
  reconciliation after budget changes.
- `hub/hub/api/v1/__init__.py` mounts all operator project resources under one explicit project
  router and removes the old implicit mounts.
- `hub/hub/api/v1/setup.py` bootstraps only the instance operator credential.
- Resource endpoint docs and error text now describe explicit project routes.
- `hub/tests/test_operator_projects_api.py` covers collection visibility, safe summaries, auth
  boundaries, isolation, lifecycle APIs, settings atomicity, setup, parity route shapes, and absence
  of legacy routes.
- Existing Hub API tests now exercise `/api/v1/projects/proj-test/...`; BOLA and spec-reconcile tests
  explicitly use two project identities.

## Files touched

Phase 0 files still present in the dirty worktree:

- `hub/hub/db/models.py`
- `hub/hub/db/engine.py`
- `hub/hub/migrations/versions/0026_add_project_workspace_identity.py`
- `hub/hub/project_workspace.py`
- `hub/hub/project_lifecycle.py`
- `hub/tests/test_migrations.py`
- `hub/tests/test_project_persistence.py`
- `hub/tests/test_project_workspace.py`
- `hub/tests/test_project_lifecycle.py`

Phase 1 product files:

- `hub/hub/auth.py`
- `hub/hub/api/v1/__init__.py`
- `hub/hub/api/v1/projects.py`
- `hub/hub/api/v1/setup.py`
- `hub/hub/api/v1/agent_chat.py`
- `hub/hub/api/v1/agent_trigger.py`
- `hub/hub/api/v1/events.py`
- `hub/hub/api/v1/logs.py`
- `hub/hub/api/v1/session_sync.py`
- `hub/hub/api/v1/status.py`
- `hub/hub/api/v1/workspace.py`
- `hub/hub/api/v1/worktrees.py`

Phase 1 tests (explicit-route migration plus focused contracts):

- `hub/tests/conftest.py`
- `hub/tests/test_operator_projects_api.py`
- `hub/tests/test_accounting_api.py`
- `hub/tests/test_accounting_budget.py`
- `hub/tests/test_agent_actions_coordination.py`
- `hub/tests/test_agent_actions_governed.py`
- `hub/tests/test_agent_capability_auth.py`
- `hub/tests/test_agent_chat.py`
- `hub/tests/test_agent_output_stream.py`
- `hub/tests/test_agent_tool_surface_phase7.py`
- `hub/tests/test_agent_trigger.py`
- `hub/tests/test_agents.py`
- `hub/tests/test_agents_self_registered.py`
- `hub/tests/test_auth.py`
- `hub/tests/test_bola.py`
- `hub/tests/test_charter_context.py`
- `hub/tests/test_charters_api.py`
- `hub/tests/test_context_usage.py`
- `hub/tests/test_conversation_contract.py`
- `hub/tests/test_conversations.py`
- `hub/tests/test_inbound_queue.py`
- `hub/tests/test_instructions.py`
- `hub/tests/test_jobs.py`
- `hub/tests/test_jobs_crud.py`
- `hub/tests/test_launchability.py`
- `hub/tests/test_mcp_server.py`
- `hub/tests/test_messages.py`
- `hub/tests/test_questions.py`
- `hub/tests/test_runners_api.py`
- `hub/tests/test_runtime_diagnostics.py`
- `hub/tests/test_scheduler.py`
- `hub/tests/test_session_sync.py`
- `hub/tests/test_spec.py`
- `hub/tests/test_spec_reconcile.py`
- `hub/tests/test_status.py`
- `hub/tests/test_tasks.py`
- `hub/tests/test_workspace_paths.py`
- `hub/tests/test_worktrees.py`

Specification and handoff files:

- `openspec/changes/2026-08-03-local-multi-project-workspace/proposal.md`
- `openspec/changes/2026-08-03-local-multi-project-workspace/design.md`
- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md`
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/local-project-workspace/spec.md`
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/app-lifecycle/spec.md`
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/agent-conversation-workspace/spec.md`
- `openspec/explorations/2026-08-03-local-multi-project-technical.md`
- `openspec/explorations/2026-08-03-specification-authority-technical.md`
- `.claude/handoffs/2026-08-03-2118-local-multi-project-proposed.md`
- `.claude/handoffs/2026-08-03-2151-local-multi-project-phase0.md`
- `.claude/handoffs/2026-08-03-2227-local-multi-project-phase1.md`
- `.claude/handoffs/LATEST.md`

Protected pre-existing untracked files, not read or modified:

- `src/agentweave/templates/skills/handoff.md`
- `src/agentweave/templates/skills/resume.md`
- `tests/test_handoff_resume_templates.py`

## Key decisions

- One project-free credential authenticates the instance operator; explicit URL identity selects a
  project. Rejected using project API keys as administrator credentials because that preserves
  implicit project authority.
- Removed the old routes instead of dual-mounting routers. Supporting both would violate the
  approved rule that every project-aware API carries explicit identity.
- Project settings update through one validated payload and flush once, so invalid mixed updates do
  not partially persist. Scheduler reconciliation consumes the stored settings afterward.
- Project summaries expose only UI-safe live agent state and path display; they do not expose
  credential material or provider session identity.
- Existing resource handlers retain their response contracts; only their route identity and shared
  dependency changed.

## Constraints and user directives

- "This repo has no AgentWeave session, and must not acquire one."
- "Do the work directly."
- "Write to `openspec/changes/<date>-<name>/`."
- "Nothing under `.agentweave/`, `agentweave.yml`, or `spec/` should exist at the repository root."
- "Also: stage paths explicitly. `git add -A` sweeps in untracked `.claude/handoffs/` scratch."
- User commands in this workstream: `$resume`, `approve`, `continue`.
- Do not invoke shipped `aw-*` product skills against this framework repository.
- Re-read the proposal, design, all three delta specs, and tasks before every phase; demonstrate
  failing contracts before implementation.
- Preserve the three protected untracked handoff/resume template files listed above.

## Dead ends and cautions

- A first bulk PowerShell route rewrite encoded tracked test files with a BOM and mojibake. Every
  affected file was reconstructed from `git show HEAD:<path>` as UTF-8 and the substitutions were
  reapplied with explicit UTF-8 handling before formatting and tests.
- The first full test pass exposed five missed unscoped `test_spec.py` requests. Its shared base URL
  was migrated and the complete suite then passed.
- `python` in the harness environment has Black but not pytest. Use the `pytest` executable from
  the system Python for tests; `python -m black` currently resolves through the harness interpreter.
- Black 26.5.1 was installed into the active development environment only; no project dependency
  files changed. It warns that Python 3.11 cannot safety-parse possible Python 3.12 syntax, but its
  check completed and left all 59 changed Hub Python files unchanged after formatting.
- The complete Hub suite currently leaks generated context files into root `.agentweave/` because
  project runtime paths still use cwd. Remove that residue after test runs until phase 3 fixes the
  cause. The removed files were untracked generated artifacts and are not recoverable from Git.

## Verification

Final checks after Black formatting:

- `pytest hub/tests -q` - 546 passed, 6 skipped, 13 Alembic deprecation warnings in 110.72s.
- `python -m black --check --line-length 100 <59 changed Hub Python files>` - all unchanged.
- `python -m compileall -q hub/hub hub/tests` - passed.
- `openspec validate --all --strict --no-interactive` - 21 passed, 0 failed.
- `git diff --check` - passed.
- Focused operator/auth/BOLA/spec tests passed earlier: 58 passed, then 31 passed after the final
  spec base correction.
- Root `.agentweave/` test residue was removed after verification; `agentweave.yml` and `spec/` were
  absent.

Not yet tested by design:

- CLI lifecycle, frontend tests/build, browser behavior, Docker, PostgreSQL, and live `testbed/`
  workflows belong to later phases.
- The current frontend cannot use the removed implicit project resource routes until phase 4.
- Ruff and mypy were not run. No repository dependency was added solely to run them.
- Windows symlink/junction tests remain skipped where the OS denies link creation.

## Git state

- Branch `hub-native-experience`; HEAD remains `37a6854` (`handoff: runner agent charter separation
  complete`).
- Worktree is dirty with the phase 0/1 files above. No files are staged and no commit was created.
- Before adding this handoff, tracked diff stat was 52 files changed, 884 insertions, 652 deletions;
  untracked files are not represented in that statistic.
- No upstream is configured, so unpushed comparison cannot be determined.
- Root `.agentweave/`, `agentweave.yml`, and `spec/` are absent after cleanup.

## Next steps

1. Re-read the approved proposal, design, all three delta specs, and tasks.
2. Begin phase 2 test-first at task 2.1: first start, already-running instance, foreground start,
   zero-project direct Hub start, legacy `proj-default` binding, status counts, and open failure.
3. Inspect `src/agentweave/cli.py`, native app lifecycle support, existing CLI lifecycle tests, and
   local runtime state before implementation.
4. Refactor bare native start to capture its directory and perform one post-health project-open call;
   then replace bootstrap labels in status and implement idempotent legacy binding/locate repair.
5. Verify phase 2 against copied pre-change data, check only proven tasks, and write its handoff.

## Open questions

None. The approved design supplies the phase-2 behavior. Any discovery that changes that design
requires a revised specification and renewed approval.

## Read on resume

- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md`
- `openspec/changes/2026-08-03-local-multi-project-workspace/design.md`
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/app-lifecycle/spec.md`
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/local-project-workspace/spec.md`
- `src/agentweave/cli.py`
- CLI/native lifecycle tests found during the phase-2 inventory
