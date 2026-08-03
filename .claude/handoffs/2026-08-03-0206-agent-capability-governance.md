# Handoff: Agent capability plane phase 2 governance

**Date:** 2026-08-03T02:06:00+01:00 · **Branch:** hub-native-experience · **HEAD:** 28dc801
**Agent:** T3 Code / Codex gpt-5.6-sol
**Previous handoff:** .claude/handoffs/2026-08-03-0201-agent-capability-coordination.md
**Status:** chunk complete

## Goal

Complete the whole Hub-native-experience umbrella. The active capability-plane successor must
replace project-wide agent authority with one governed run credential shared by HTTP, MCP, and
commands.

## Current state

Phases 0–2 are complete; phase 2 is verified and pending commit. Run-bound API routes now request
agents through existing template and agent-budget governance, and create/toggle/run/delete jobs
through the existing operator-controlled allowance. Agent, delegation Message, AIJob create/update,
JobRun, and job deletion tombstone rows retain run attribution. Spoofed headers and actor-like body
fields do not override the authenticated actor. Migration head is 0022.

## Files touched

- hub/hub/api/v1/agent_actions.py — governed request-agent and job routes/schemas.
- hub/hub/api/v1/agents.py — requested Agent and delegation Message attribution.
- hub/hub/api/v1/jobs.py — job create/update/run/delete attribution.
- hub/hub/db/models.py — governed attribution columns and deletion tombstone.
- hub/hub/migrations/versions/0022_add_governed_action_attribution.py — additive schema.
- hub/tests/test_agent_actions_governed.py — allowance, budget, spoofing, attribution tests.
- hub/tests/test_migrations.py — head advanced to 0022.
- openspec/changes/agent-capability-plane/tasks.md — phase 2 complete.

## Key decisions

- Agent routes call the existing governed action implementations with server-derived actor values;
  duplicating template/budget/allowance logic was rejected.
- Job deletion writes `AgentJobDeletion` before removing AIJob because EventLog alone is explicitly
  insufficient durable attribution and a deleted row cannot retain its responsible run.
- Manual job execution stores `requested_by_run_id` on JobRun for both scheduler success and durable
  failure. Merely updating AIJob was rejected because it would not identify the specific firing.
- Agent job-create schema omits operator-only `source`; it is fixed to `hub` server-side.

## Constraints and user directives (verbatim)

> “I want you to work on the entire umbrella project with the same parameters that we discussed previously”

> “Ignore the aw-spec skills. I'm using openspec only.”

> “At the end of every implementation run handoff aaand spawn a new run with the skill resume.”

No root AgentWeave state; live tests only under testbed; explicit staging only; continue without
waiting for approval.

## Dead ends

- Ruff executable/module remains unavailable.
- Broad `rg` accidentally included built UI assets and truncated output; constrain searches to
  named source files.

## Verification

- Focused governed suite: 29 passed, 1 optional skip.
- Wider phase suite: 73 passed, 2 skipped.
- `git diff --check` passed.
- Full Hub/CLI/frontend/live checks remain for closeout.

## Git state

Branch `hub-native-experience`, HEAD `28dc801`; dirty only with the eight phase-2 paths above plus
this handoff/LATEST before commit.

## Next steps

1. Validate OpenSpec from root, explicitly stage and commit phase 2 as
   `capability phase 2: govern agent and job actions`, then inspect `hub/hub/mcp_server.py` and
   command/HttpTransport clients.
2. Write parity tests for all allowed operations and typed validation/403/404/409 failures.
3. Switch MCP and bound commands to `AW_RUN_TOKEN` plus `/agent-actions`, preserve typed errors, and
   remove project API key/identity headers from spawned environments.
4. Verify/handoff/commit phase 3, then full closeout/archive and next umbrella successor.

## Open questions for the user

None.

## Read on resume

- openspec/changes/agent-capability-plane/tasks.md
- hub/hub/mcp_server.py
- hub/hub/api/v1/agent_actions.py
- hub/hub/api/v1/agent_trigger.py
- src/agentweave/transport/http.py
- src/agentweave/mcp/server.py
