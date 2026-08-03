# Handoff: Agent capability plane phase 1 coordination

**Date:** 2026-08-03T02:01:00+01:00 · **Branch:** hub-native-experience · **HEAD:** d1c659c
**Agent:** T3 Code / Codex gpt-5.6-sol
**Previous handoff:** .claude/handoffs/2026-08-03-0156-agent-capability-auth.md
**Status:** chunk complete

## Goal

Complete the entire Hub-native-experience umbrella. The active agent-capability-plane successor
must provide one run-bound, least-privilege application API with HTTP/MCP/command parity and no
project credential in spawned agents.

## Current state

Phases 0 and 1 are complete; phase 1 is verified and pending its commit. Agent-action routes now
send peer messages, create/list/get/update shared tasks, ask operator questions, and read only the
asking agent's questions. Payloads forbid identity fields. Server-derived actor identity controls
all effects despite spoofed headers. Message, task create/update, and question rows persist run
attribution via additive migration 0021. Operator and agent writes share the same core helpers.

## Files touched

- hub/hub/api/v1/agent_actions.py — finished phase-1 schemas and routes.
- hub/hub/api/v1/messages.py — finished shared actor-aware message write helper.
- hub/hub/api/v1/tasks.py — finished shared task create/update helpers.
- hub/hub/api/v1/questions.py — finished shared question create helper.
- hub/hub/db/models.py — finished coordination attribution columns.
- hub/hub/migrations/versions/0021_add_coordination_run_attribution.py — finished additive migration.
- hub/tests/test_agent_actions_coordination.py — finished intent, spoofing, privacy, denial tests.
- hub/tests/test_migrations.py — latest revision advanced to 0021.
- openspec/changes/agent-capability-plane/tasks.md — phase 1 marked complete.

## Key decisions

- Agent payload schemas are separate strict models, so actor fields are absent and extra identity
  fields fail validation. Reusing operator schemas was rejected because they expose sender,
  assigner, requester, and run fields.
- Existing operator handlers and agent handlers share write helpers. Duplicating queue/scheduling
  behavior inside agent routes was rejected because it would drift.
- Attribution columns are nullable and use loose run references, matching the approved design and
  retaining historical rows. Task updates always replace `updated_by_run_id`, including clearing it
  for later operator updates, so it means latest responsible run rather than any past run.
- Question reads require matching project and `from_agent`; returning every project question was
  rejected because it leaks other agents' operator conversations.

## Constraints and user directives (verbatim)

> “I want you to work on the entire umbrella project with the same parameters that we discussed previously”

> “Ignore the aw-spec skills. I'm using openspec only.”

> “At the end of every implementation run handoff aaand spawn a new run with the skill resume.”

Do not create root AgentWeave project state. Test live product flows only in `testbed/`. Stage paths
explicitly; never use `git add -A`. Continue successors without waiting for approval.

## Dead ends

- Ruff remains unavailable as both executable and Python module.
- `openspec validate` was accidentally invoked from `hub/` and reported unknown item; rerun from
  repository root. The implementation tests in the same command passed.
- `/api/v1/queue` has no GET root; the operator-only read is `/api/v1/queue/settings`.

## Verification

- Focused phase suite: 27 passed.
- `pytest -q tests/test_agent_capability_auth.py tests/test_agent_actions_coordination.py tests/test_messages.py tests/test_tasks.py tests/test_questions.py tests/test_inbound_queue.py tests/test_migrations.py` — 58 passed, 1 skipped.
- `git diff --check` passed.
- Full Hub/CLI/frontend/live regressions not yet run; reserved for closeout.

## Git state

Branch `hub-native-experience`, HEAD `d1c659c`; dirty only with the nine phase-1 code/test/spec paths
listed above plus this handoff and LATEST before commit.

## Next steps

1. Validate OpenSpec from repository root, explicitly stage phase-1 files and commit
   `capability phase 1: derive coordination actors`, then inspect governed Agent and AIJob services.
2. Write phase-2 tests for request-agent and job operations using only run credentials, including
   budget/allowance failures, spoof attempts, and durable create/update run attribution.
3. Implement phase 2 through existing governance services; verify, hand off, and commit.
4. Continue parity/removal and closeout phases, then the next umbrella successor.

## Open questions for the user

None.

## Read on resume

- openspec/changes/agent-capability-plane/design.md
- openspec/changes/agent-capability-plane/tasks.md
- hub/hub/api/v1/agent_actions.py
- hub/hub/api/v1/agents.py
- hub/hub/api/v1/jobs.py
- hub/hub/db/models.py
