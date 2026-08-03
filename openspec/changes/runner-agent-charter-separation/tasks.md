# Implementation plan

## Working protocol

1. Re-read proposal, design, and the delta specs touched by a phase before starting it.
2. Open each phase with the test for the behaviour it adds — several defects in prior successors
   survived "complete" phases because no test asserted the scenario.
3. Commit and hand off every verified phase.
4. Never mark work complete from a plan alone — only real, verified implementation closes a task.
5. Grep every caller of `roles.py`, `context_builder.py`, `RUNNER_CONFIGS`, `RUNNER_TYPES`, and
   `VALID_ROLE_IDS` before deleting anything in phase 5 — do not trust the design doc's caller list
   alone; it was written from a point-in-time grep that may be stale by then.

## 0. Data model

- [ ] 0.1 Write failing tests for new `Runner` and `Charter` SQLAlchemy models (project-scoped,
      `Agent.runner_id`/`Agent.charter_id` nullable FKs) in `hub/tests/`.
- [ ] 0.2 Add `Runner` and `Charter` tables to `hub/hub/db/models.py`; add `runner_id`/`charter_id`
      columns to `Agent`. Write the Alembic-equivalent migration this project uses (check
      `hub/hub/db/engine.py` for the current schema-creation mechanism before assuming Alembic).
- [ ] 0.3 Verify: new tables/columns created on fresh DB; existing `Agent` rows load with null
      `runner_id`/`charter_id` on an upgraded DB. Hand off and commit.

## 1. Runner registry

- [ ] 1.1 Write failing tests for runner CRUD API (`POST`/`GET`/`PATCH`/`DELETE` on a new
      `/api/v1/runners` route) and the first-boot seed behavior (project with zero runners gets one
      `claude` and one `codex` runner).
- [ ] 1.2 Implement the CRUD API and the seed step. Confirm against `design.md`'s open question
      whether `RUNNER_CONFIGS`' existing flags are worth carrying into seeded runner rows — inspect
      current `RUNNER_CONFIGS` in `src/agentweave/constants.py` and `hub/hub/runner_commands.py`
      before deciding, and record the decision here once made.
- [ ] 1.3 Wire agent triggering (`hub/hub/api/v1/agent_trigger.py` and whatever calls
      `runner_commands.py`) to resolve CLI/flags/model from the agent's bound runner instead of
      `RUNNER_CONFIGS`. An agent with no bound runner refuses launch with a typed error (per the
      `runner-registry` spec's "Agent has no bound runner" scenario).
- [ ] 1.4 Build the Hub UI runner screen (list/create/edit/delete) and a runner picker on the agent
      detail view, following the `project-instructions` Instructions-screen pattern.
- [ ] 1.5 Verify: runner CRUD, seed-on-first-boot, and trigger-resolves-from-binding scenarios all
      pass against real tests, not just the plan. Hand off and commit.

## 2. Agent charter

- [ ] 2.1 Write failing tests for charter CRUD API (`/api/v1/charters`) and the one-time seed step
      (project with zero charters gets one per bundled role guide in `hub/data/roles/*.md`, named
      from the guide's label).
- [ ] 2.2 Implement the CRUD API and the seed step. Seeding runs at most once per project — verify
      this with a test that restarts the Hub against an existing project and asserts no duplicate
      charters appear.
- [ ] 2.3 Wire `hub/hub/api/v1/agents.py::_render_hub_agent_context` and the `/context` role-lookup
      route to resolve the agent's bound charter instead of `_load_role_content`'s file-based
      lookup. An agent with no bound charter gets project instructions plus a clear no-charter
      notice, not an error (per `agent-charter`'s "Agent has no bound charter" scenario).
- [ ] 2.4 Build the Hub UI charter screen (list/create/edit/delete) and a charter picker on the
      agent detail view.
- [ ] 2.5 Verify: charter CRUD, one-time seed-from-role-guides, context resolution with and without
      a bound charter all pass against real tests. Hand off and commit.

## 3. Spec reconciliation

- [ ] 3.1 Sync this change's delta specs into `openspec/specs/`: create `runner-registry` and
      `agent-charter`; apply the MODIFIED deltas to `agent-context-onboarding`.
- [ ] 3.2 Verify every scenario in the touched delta specs against the phase 0–2 implementation, not
      against intent. Note anything that cannot be verified and why.
- [ ] 3.3 Hand off and commit.

## 4. Delete the legacy role system

- [ ] 4.1 Re-run the caller grep from the working protocol's rule 5. Confirm the actual current
      caller set of `roles.py`, `context_builder.py`, `VALID_ROLE_IDS`, and the role-list constants
      matches (or note how it has drifted from) `design.md`'s point-in-time list.
- [ ] 4.2 Delete `src/agentweave/roles.py`, `src/agentweave/context_builder.py` (confirm zero
      remaining callers first — design.md's premise is that `session.py` was its only caller and
      `session.py`'s role calls are removed in 4.3), `templates/roles/*.md`, `hub/data/roles/*.md`
      (only after phase 2's seed step no longer reads it), `_load_role_content`'s file-lookup tiers
      in `hub/hub/api/v1/agents.py`, and `VALID_ROLE_IDS`/role-list constants in
      `src/agentweave/constants.py`.
- [ ] 4.3 Remove the now-dead role-sync calls in `src/agentweave/session.py` (the `set_agent_roles`/
      `save_roles_config` call sites found during design-phase grep).
- [ ] 4.4 Verify: full CLI and Hub regression suites pass; grep confirms no remaining import of
      `roles.py` or `context_builder.py` anywhere in `src/`, `tests/`, `hub/`. Hand off and commit.

## 5. Regression, live verification, and docs

- [ ] 5.1 Run full CLI, Hub, and frontend regressions.
- [ ] 5.2 Live-verify in a throwaway `testbed/` directory: a fresh project boots with seeded default
      runners and charters, an agent bound to a runner and a charter is triggered and its context
      includes the charter content, an agent with no charter gets the no-charter notice instead of
      an error, and an agent with no runner refuses to launch with a typed error.
- [ ] 5.3 `openspec validate --all --strict` passes.
- [ ] 5.4 Update `AGENTS.md`/`CLAUDE.md`: resolve the multi-role deprecation note (it currently
      warns against building on the old system; after this change there is no old system to warn
      about) and correct the `src/agentweave/` module list and Hub architecture sections.
- [ ] 5.5 Archive this change; annotate
      `openspec/changes/2026-07-30-hub-native-experience/tasks.md` 16.2 with what this successor
      synced, matching the pattern of prior successors' annotations.
- [ ] 5.6 Final handoff and commit.
