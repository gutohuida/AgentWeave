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

- [x] 0.1 Added `hub/tests/test_runner_charter_models.py`: ORM round-trip tests for `Runner`
      (including the `cli IN ('claude','codex')` check constraint) and `Charter`, agent
      binding/unbound-binding tests, and a migration test (`test_migration_0023_...`) that
      stamps a pre-change DB at 0022 and asserts the upgrade adds `runners`/`charters` tables plus
      nullable `agents.runner_id`/`charter_id` columns with existing rows loading null.
- [x] 0.2 Added `Runner` and `Charter` to `hub/hub/db/models.py` (project-scoped; `Runner` has
      `cli`/`model`/`flags`, `Charter` has `name`/`content`); added nullable `runner_id`/`charter_id`
      FK columns to `Agent`; registered both new models in `hub/hub/db/engine.py`'s side-effect
      import list (required for `create_all` to pick them up — see the comment already there
      warning about this). Wrote `hub/hub/migrations/versions/0023_add_runner_charter.py` following
      the existing idempotent create-if-missing pattern (0022's style), including a SQLite-safe FK
      addition (no `create_foreign_key` on SQLite, matching 0017's `conversation_id` precedent) and
      a downgrade that drops the new agent columns before dropping the referenced tables.
      **Decision on design.md's open question**: `Runner.flags` exists as a freeform, optional JSON
      column but nothing populates it yet — `RUNNER_CONFIGS` in `src/agentweave/constants.py` turned
      out to hold CLI-invocation structure (session flags, output format, model flag syntax) that's
      derived from `cli` itself, not a per-runner-instance override an operator would set; only
      `cli` and `model` are meaningfully operator-facing today. Revisit if a real need for per-runner
      flag overrides appears.
- [x] 0.3 Verified: `hub/tests/test_runner_charter_models.py` (6 new tests) plus full
      `hub/tests/test_migrations.py` (including the two pre-existing tests whose hardcoded
      `alembic_version == "0022"` assertions were updated to `"0023"`) all pass. Full Hub regression:
      460 passed, 4 skipped. (This phase's own baseline wasn't independently re-measured before
      starting — the single-runtime successor's own handoffs reported 453–454/4 at various points —
      so the exact delta isn't reconciled here; what's confirmed is that the full suite is green
      now, including every pre-existing test.) Hand off and commit.

## 1. Runner registry

- [x] 1.1/1.2 Added `hub/hub/schemas/runners.py` (`RunnerCreate`/`RunnerUpdate`/`RunnerResponse`,
      `cli` validated against `RUNNER_CLIS`) and `hub/hub/api/v1/runners.py` (`POST`/`GET list`/
      `GET one`/`PATCH`/`DELETE` on `/api/v1/runners`, registered in `api/v1/__init__.py`; delete
      refuses with 409 if any agent is still bound, per an implementation-level safety decision not
      required by the spec). Added `_seed_default_runners()` to `hub/hub/db/engine.py::init_db()`,
      run unconditionally (not gated behind the API-key bootstrap's early-return) so it seeds on
      every restart, idempotent per project. Added `hub/tests/test_runner_charter_models.py`-sibling
      `hub/tests/test_runners_api.py` (10 tests: CRUD, seed, seed-doesn't-duplicate,
      delete-refused-when-bound, bind-to-unknown-runner-refused).
      **`RUNNER_CONFIGS` decision**: did not carry its flags into seeded runners — inspection showed
      `RUNNER_CONFIGS` holds CLI-invocation structure (session-resume flag syntax, output format,
      model-flag syntax) derived from *which CLI*, not a per-runner-instance override; only `cli` and
      `model` are meaningfully operator-facing. `Runner.flags` exists as an unused freeform escape
      hatch (recorded in phase 0's own task note too).
- [x] 1.3 Wired `hub/hub/api/v1/agent_trigger.py::trigger_agent_directly`: loads the agent's
      `Agent.runner_id`, refuses with a 409 `TriggerAgentError` ("has no runner bound...") if unset
      or dangling, otherwise overrides `config["runner"]`/`config["model"]` from the bound `Runner`
      row before calling `probe_agent`/`build_command` — the bound Runner is now the sole source of
      which CLI/model to launch; legacy config-dict `runner`/`model` keys are superseded, not merged.
      Added `PATCH /api/v1/agents/{name}` support for `runner_id` (validates the runner exists and
      belongs to the project).
      **Real bug found and fixed during this wiring, not just a test artifact**: forcing
      `config["runner"]` to `Runner.cli` ("claude"/"codex" only) collapsed the old
      claude/claude_proxy/native distinction that `launchability.resolve_agent_env`'s
      `ANTHROPIC_BASE_URL`-stripping guard depended on (`if runner == "claude": strip
      ANTHROPIC_BASE_URL`) — a claude-cli-bound proxy agent's own explicitly-configured base URL
      would have been silently stripped, breaking proxy routing. Fixed by decoupling the guard from
      the runner-type string entirely: it now only strips an *ambient* `ANTHROPIC_BASE_URL` (present
      in the Hub's own environment but not explicitly set by the agent's own `env_vars`), which is
      what the guard's own docstring already said it was for.
      **Also found and fixed**: `PATCH /api/v1/agents/{name}` unconditionally rejected any edit to a
      session-synced ("configured") agent with 409 — which would have made `runner_id`/`charter_id`
      unbindable for any agent the CLI's legacy session-sync ever touched. Narrowed the rejection to
      exclude `runner_id`/`charter_id` (fields the CLI never owned).
      **Test fallout, all fixed**: 16 tests across `test_agent_trigger.py`, `test_scheduler.py`,
      `test_accounting_budget.py`, `test_conversation_contract.py`, `test_conversations.py`,
      `test_inbound_queue.py`, `test_runtime_diagnostics.py` assumed an agent could spawn without a
      bound runner — added a shared `bind_runner` fixture in `conftest.py` and called it wherever a
      test needed a real spawn or spawn-adjacent pre-flight check to be reached. Two tests were
      retired, not just patched: `test_manual_runner_accumulates_queue_with_visible_reason`
      (`runner="manual"`) was rewritten as `test_unbound_agent_accumulates_queue_with_visible_reason`
      — Runner.cli can't express "manual" anymore, so "no execution capability configured" is now
      expressed as no binding, which is the real equivalent behavior.
      `test_trigger_unsupported_runner_accumulates_queue` (`runner="kimi"`) was deleted outright —
      Runner.cli is schema-constrained to claude/codex, so there is no longer any way, through the
      real API, to construct the scenario it tested; a comment at its old location explains why and
      points to the unbound-agent test as the surviving equivalent coverage.
      Full Hub regression after this task: 469 passed, 4 skipped.
- [x] 1.4 Built the Hub UI runner screen (list/create/edit/delete) and registered it in the
      project sidebar/page router. Added runner API React Query hooks and a runner picker to the
      agent detail view, including explicit unbind plus loading/pending/error states. The agent list
      response now exposes `runner_id`/`charter_id`, with a backend regression test for the bound
      runner ID contract.
- [x] 1.5 Verified runner CRUD, idempotent default seeding, agent binding, and trigger resolution
      through `hub/tests/test_runners_api.py` (11 passed) and the full Hub suite (470 passed, 4
      skipped). Frontend production build passes and all 289 frontend tests pass. The repository's
      existing `npm run lint` command cannot start because ESLint 9 requires an `eslint.config.*`
      file and this project still has only legacy configuration; no lint-result claim is made.
      Hand off and commit.

## 2. Agent charter

- [x] 2.1 Write failing tests for charter CRUD API (`/api/v1/charters`) and the one-time seed step
      (project with zero charters gets one per bundled role guide in `hub/data/roles/*.md`, named
      from the guide's label).
- [x] 2.2 Implement the CRUD API and the seed step. Seeding runs at most once per project — verify
      this with a test that restarts the Hub against an existing project and asserts no duplicate
      charters appear.
- [x] 2.3 Wire `hub/hub/api/v1/agents.py::_render_hub_agent_context` and the `/context` role-lookup
      route to resolve the agent's bound charter instead of `_load_role_content`'s file-based
      lookup. An agent with no bound charter gets project instructions plus a clear no-charter
      notice, not an error (per `agent-charter`'s "Agent has no bound charter" scenario).
- [x] 2.4 Build the Hub UI charter screen (list/create/edit/delete) and a charter picker on the
      agent detail view.
- [x] 2.5 Verify: charter CRUD, one-time seed-from-role-guides, context resolution with and without
      a bound charter all pass against real tests. Hand off and commit.

**Phase 2 evidence:** Added failing-first charter CRUD, exact 21-guide seed parity, restart and
delete-all idempotence, migration, binding, edited-content, direct-lookup, and bound/unbound context
tests. Implemented typed charter API/schema, migration 0024's durable `Project.charters_seeded`
marker, DB-backed context by stable charter ID, project-instructions layering, Charters UI, and the
agent charter picker. Verified 37 focused tests passed (1 skipped), the full Hub suite passed 486
(4 skipped), all 291 frontend tests passed, the production frontend build passed, and Black/Ruff
passed on the changed Python surface. The build retains pre-existing duplicate-case and bundle-size
warnings. Packaged seed guides live at `hub/hub/data/roles/` (the shorter path above is conceptual).

## 3. Spec reconciliation

- [x] 3.1 Sync this change's delta specs into `openspec/specs/`: create `runner-registry` and
      `agent-charter`; apply the MODIFIED deltas to `agent-context-onboarding`.
- [x] 3.2 Verify every scenario in the touched delta specs against the phase 0–2 implementation, not
      against intent. Note anything that cannot be verified and why.
- [x] 3.3 Hand off and commit.

**Phase 3 evidence:** Created canonical `runner-registry` and `agent-charter` specs and applied the
approved `agent-context-onboarding` modifications. Reconciliation found that the unchanged
project-instructions ordering contract needed a terminology delta, so `project-instructions` is now
declared as modified and its canonical wording says charter rather than role guide. Scenario review
also found Runner flags were persisted but not launched; added failing command/integration tests and
wired validated string-list flags from the bound Runner into Claude/Codex command construction.
Runner/charter authoring and reassignment scenarios now have dedicated frontend tests. Verification:
102 focused Hub scenario tests passed, full Hub regression passed 489 (4 skipped), all 293 frontend
tests passed, production frontend build passed, Ruff passed on the changed Python surface, and
`openspec validate --all --strict` passed 21/21. No touched delta scenario remains unverified.

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
