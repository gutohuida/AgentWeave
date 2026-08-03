# Handoff: Agent capability plane phase 0 authentication

**Date:** 2026-08-03T01:56:00+01:00 · **Branch:** hub-native-experience · **HEAD:** a97dd39
**Agent:** T3 Code / Codex gpt-5.6-sol
**Previous handoff:** .claude/handoffs/2026-08-03-0147-accounting-slice-archived.md
**Status:** chunk complete

## Goal

Complete the entire Hub-native-experience umbrella through focused OpenSpec successors. The active
successor is agent-capability-plane: make one least-privilege, run-bound application API available
equally through direct HTTP, MCP, and bound commands, without giving spawned agents project keys.

## Current state

Phase 0 is implemented and verified, pending its phase commit. Every spawned run receives a
high-entropy `AW_RUN_TOKEN`; only its SHA-256 digest is stored on the Run. The `AgentActor`
dependency accepts only active run credentials and derives project, agent, and run identity from
the database. Project keys remain exclusive to operator routes, terminal Run state immediately
revokes the run credential, migration 0020 upgrades existing databases without inventing tokens,
and the empty `/api/v1/agent-actions` router is ready for phase 1 operations.

## Files touched

- hub/hub/agent_auth.py — finished run-token mint/hash and AgentActor dependency.
- hub/hub/api/v1/agent_actions.py — finished empty least-privilege namespace scaffold.
- hub/hub/api/v1/__init__.py — finished router registration.
- hub/hub/api/v1/agent_trigger.py — finished token mint, env injection, and digest persistence.
- hub/hub/db/models.py — finished nullable unique Run digest model field.
- hub/hub/migrations/versions/0020_add_run_capability_tokens.py — finished additive migration.
- hub/tests/test_agent_capability_auth.py — finished active/refusal/revocation boundary tests.
- hub/tests/test_agent_trigger.py — finished plaintext injection/digest-only persistence checks.
- hub/tests/test_migrations.py — finished 0020 head and old-run migration coverage.
- openspec/changes/agent-capability-plane/tasks.md — phase 0 marked complete.

## Key decisions

- Plaintext run tokens exist only in the spawned process environment; hashes are persisted so a
  database leak does not directly grant live agent capabilities. Passing tokens in command args,
  events, API responses, or logs was rejected because those surfaces are routinely observable.
- Authentication resolves only `Run.status == "running"`; a separate revocation table or expiry
  clock was rejected because Run lifecycle is already the authoritative execution boundary.
- Agent and operator dependencies are distinct and discriminate token prefixes. Reusing
  `get_project` with extra headers was rejected because it would preserve project-wide authority
  and caller-asserted identity.
- Migration leaves pre-existing Run digests NULL. Backfilling credentials was rejected because no
  recoverable plaintext token could be delivered securely to already-started processes.

## Constraints and user directives (verbatim)

> “I want you to work on the entire umbrella project with the same parameters that we discussed previously”

> “Ignore the aw-spec skills. I'm using openspec only.”

> “At the end of every implementation run handoff aaand spawn a new run with the skill resume.”

Repository constraint: do not create `.agentweave/`, `agentweave.yml`, or `spec/` at repository
root; do not invoke aw-* skills. Test product flows only inside `testbed/`. Stage paths explicitly;
never use `git add -A`.

## Dead ends

- Running targeted tests from `hub/` with paths prefixed `hub/tests/` found no files; use
  `tests/...` from that working directory.
- `ruff` and `python -m ruff` are unavailable in the current Python environment. Do not repeatedly
  retry unless the environment changes; use tests and existing build/type checks.
- Initial LATEST loading joined `.claude/handoffs` twice because LATEST already contains the full
  relative path. Read that path directly.

## Verification

- `pytest -q tests/test_agent_capability_auth.py tests/test_agent_trigger.py::test_trigger_injects_identity_env_and_tells_agent_the_access_path tests/test_migrations.py::test_alembic_upgrade_head_fresh_file_db tests/test_migrations.py::test_init_db_runs_alembic_for_file_db tests/test_migrations.py::test_migration_0020_adds_empty_unique_run_token_digest` — 13 passed.
- `pytest -q tests/test_auth.py tests/test_agent_capability_auth.py tests/test_agent_trigger.py tests/test_migrations.py` — 54 passed, 1 skipped.
- Ruff was not run because neither executable nor module is installed.
- Full Hub, CLI, frontend, OpenSpec, and live-run regressions were not run at this phase boundary.

## Git state

Branch `hub-native-experience`, HEAD `a97dd39`, dirty with exactly the ten implementation/test/spec
paths listed above before the phase commit. The branch has no configured/available origin diff in
the command output.

## Next steps

1. Explicitly stage the ten phase-0 paths, commit `capability phase 0: bind credentials to runs`,
   then read `agent_actions.py`, existing message/task/question routers and models to write phase-1
   actor-derived API tests before implementation.
2. Implement message, task, and question agent routes through shared services; persist create/update
   Run attribution and enforce that an actor reads only answers to its own questions.
3. Verify phase 1, update tasks, write another durable handoff, and commit.
4. Continue phases 2–4 without waiting for user input, then archive/reconcile and choose the next
   umbrella successor.

## Open questions for the user

None.

## Read on resume

- openspec/changes/agent-capability-plane/design.md
- openspec/changes/agent-capability-plane/specs/agent-capability-plane/spec.md
- openspec/changes/agent-capability-plane/tasks.md
- hub/hub/api/v1/agent_actions.py
- hub/hub/api/v1/messages.py
- hub/hub/api/v1/tasks.py
