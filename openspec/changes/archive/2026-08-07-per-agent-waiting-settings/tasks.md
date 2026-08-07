# Tasks

## 1. The setting on the agent

- [x] 1.1 `Agent` gains `permission_timeout_seconds` and `question_timeout_seconds`, nullable ints,
      in `hub/hub/db/models.py`. `NULL` means the built-in default.
- [x] 1.2 Migration `0034_add_agent_waiting_settings.py`; head becomes 0034. Guard for a missing
      `agents` table, as 0033 does.
- [x] 1.3 Update head assertions in `test_migrations.py` and `test_project_persistence.py`.
- [x] 1.4 `PATCH /agents/{name}` accepts both, bounded 10–600, and returns them. Out of range ⇒ 400.
      `null` clears back to the default.
- [x] 1.5 The agent list/detail response carries both, so the UI can render current values.
- [x] 1.6 Tests: set, clear, round-trip, out of range both ends, non-integer.

## 2. Reaching the tools

- [x] 2.1 `hub/hub/mcp_server.py` reads `AW_DECISION_TIMEOUT` and `AW_QUESTION_TIMEOUT`, falling back
      to today's constants on absent, malformed or out-of-range values.
- [x] 2.2 `hub/hub/api/v1/agent_trigger.py` puts both in the spawn environment, beside
      `AW_WORKSPACE_DIR`.
- [x] 2.3 The Codex app-server wait uses the agent's permission value directly rather than the
      module constant.
- [x] 2.4 Tests: a configured agent's values reach the environment; an unconfigured one sets nothing;
      the tool honours the variable; a malformed variable falls back rather than raising.

## 3. The Settings tab

- [x] 3.1 Rename the `info` tab's label to "Settings" in `AgentDetailPanel.tsx`. **Done, but
      inert:** `AgentsPage` — the only thing that renders `AgentDetailPanel` — is imported
      nowhere outside its own file and the tests, so that tabbed surface is unrouted in the
      current navigation. The reachable surface is the "Agent details" drawer
      (`ConversationControls.tsx:224`), which renders `AgentInfoTab` directly under a
      "{agent} details" heading and has no tab label to rename. Left in place for whenever
      that page is restored; see Follow-ups.
- [x] 3.2 Rebuild `AgentInfoTab`'s editable bindings on `SettingsSection` / `SettingsRow`, so the
      agent's settings and the project's read as one system.
- [x] 3.3 Add a "Waiting for you" section with the two values, `min`/`max` matching the API, and a
      description stating the measured figures.
- [x] 3.4 `useUpdateAgentWaiting` in `api/agents.ts` (or alongside the existing bind hooks).
- [x] 3.5 Blank input clears back to the default rather than sending 0.
- [x] 3.6 Frontend tests: renders current values, saves a change, clears to default, respects bounds.

## 4. Close out

- [x] 4.1 `pytest hub/tests/ -q`, `pytest tests/ -q`, `npx vitest run`, `npx tsc --noEmit`.
- [x] 4.2 `ruff check` every touched Python file.
- [x] 4.3 `npm run build` and sync `hub/hub/static/ui`; verify with `diff -rq`.
- [x] 4.4 `npx openspec validate --specs --strict`.
- [x] 4.5 Live-verify: set a short question wait on a real agent, ask a question, and confirm it gives
      up at the configured time rather than at 240s.

## Follow-ups found while doing this

- [ ] `AgentsPage` and `AgentDetailPanel` are unreachable — nothing imports `AgentsPage`. Either
      restore a route to them or delete them; right now they are tested, maintained, and dead.
