# Handoff: Agent capability plane phase 3 parity cutover

**Date:** 2026-08-03T02:13:00+01:00 · **Branch:** hub-native-experience · **HEAD:** eed33bd
**Agent:** T3 Code / Codex gpt-5.6-sol
**Previous handoff:** .claude/handoffs/2026-08-03-0206-agent-capability-governance.md
**Status:** chunk complete

## Goal

Complete the entire Hub-native-experience umbrella. The active capability-plane successor provides
one least-privilege run-authenticated application contract shared by HTTP, MCP, and commands.

## Current state

Phases 0–3 are complete; phase 3 is verified and pending commit. MCP and bound HttpTransport/CLI
commands now use `AW_RUN_TOKEN`, call only `/api/v1/agent-actions`, omit identity headers/body
fields, and preserve typed application failures. Bound transport creation bypasses project
transport config and creates a keyless HTTP client. Spawned environments inherit no HUB_API_KEY or
HUB_PROJECT_ID even if the parent has them. MCP no longer converts errors into empty/success data.

## Files touched

- hub/hub/mcp_server.py — thin run-token adapter and typed HubAPIError.
- hub/hub/api/v1/agent_actions.py — safe client task IDs for parity.
- hub/hub/api/v1/agent_trigger.py — scrub project credentials and inject only runtime URL/token.
- hub/tests/test_mcp_server.py — path/payload/token/error parity tests.
- hub/tests/test_agent_trigger.py — inherited-secret scrubbing test.
- src/agentweave/transport/http.py — bound agent-action routing, payload stripping, typed failures.
- src/agentweave/transport/config.py — run-bound keyless transport construction.
- src/agentweave/cli.py — agent request requires run token and sends actor-free body.
- tests/test_http_transport.py — command adapter token/payload/error tests.
- tests/test_transport_config.py — proves project config bypass.
- tests/test_agent_tool_surface_phase7.py — new command contract.
- openspec/changes/agent-capability-plane/tasks.md — phase 3 complete.

## Key decisions

- Adapters raise typed failures instead of returning empty collections or success-shaped error
  dictionaries; swallowing errors was rejected because it destroys denied/not-found/conflict meaning.
- Bound `get_transport()` returns a keyless HttpTransport from HUB_URL before reading transport.json;
  loading the operator project key was rejected as unnecessary ambient authority.
- HttpTransport strips every actor-like field and rewrites message recipient shape only at the
  serialization edge. Business rules remain solely in agent-action handlers/services.
- Operator transport behavior is unchanged when AW_RUN_TOKEN is absent.

## Constraints and user directives (verbatim)

> “I want you to work on the entire umbrella project with the same parameters that we discussed previously”

> “Ignore the aw-spec skills. I'm using openspec only.”

> “At the end of every implementation run handoff aaand spawn a new run with the skill resume.”

No root AgentWeave state; live product testing only in testbed; explicit staging; continue successors.

## Dead ends

- Ruff remains unavailable.
- Mixing Hub and CLI files named `test_mcp_server.py` in one pytest process causes module-name
  collection collisions; run Hub and root suites as separate commands.

## Verification

- Hub parity/security regression: 100 passed, 1 skipped.
- CLI adapter/command regression: 90 passed.
- Earlier focused parity runs: 25 Hub and 58 CLI passed.
- Full Hub, full CLI, frontend, migration, OpenSpec, and real live spawn remain for phase 4.

## Git state

Branch `hub-native-experience`, HEAD `eed33bd`; dirty only with twelve phase-3 code/test/spec paths
plus this handoff/LATEST before commit.

## Next steps

1. Validate OpenSpec, explicitly stage and commit `capability phase 3: unify agent adapters`.
2. Run full Hub tests, full CLI tests, UI tests/build, all strict OpenSpec validation, and focused
   secret scans.
3. Live-verify a real spawned run from testbed using the injected plane with no project key; capture
   evidence without exposing the token.
4. Sync authoritative specs, archive/reconcile umbrella/tool-surface, final handoff/commit, then
   select and begin the next umbrella successor.

## Open questions for the user

None.

## Read on resume

- openspec/changes/agent-capability-plane/tasks.md
- openspec/changes/agent-capability-plane/specs/agent-capability-plane/spec.md
- hub/hub/mcp_server.py
- hub/hub/api/v1/agent_trigger.py
- src/agentweave/transport/http.py
- openspec/changes/2026-07-30-hub-native-experience/tasks.md
