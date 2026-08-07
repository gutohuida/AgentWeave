# Tasks

## 1. The setting on the agent

- [ ] 1.1 `Agent` gains `permission_timeout_seconds` and `question_timeout_seconds`, nullable ints,
      in `hub/hub/db/models.py`. `NULL` means the built-in default.
- [ ] 1.2 Migration `0034_add_agent_waiting_settings.py`; head becomes 0034. Guard for a missing
      `agents` table, as 0033 does.
- [ ] 1.3 Update head assertions in `test_migrations.py` and `test_project_persistence.py`.
- [ ] 1.4 `PATCH /agents/{name}` accepts both, bounded 10–600, and returns them. Out of range ⇒ 400.
      `null` clears back to the default.
- [ ] 1.5 The agent list/detail response carries both, so the UI can render current values.
- [ ] 1.6 Tests: set, clear, round-trip, out of range both ends, non-integer.

## 2. Reaching the tools

- [ ] 2.1 `hub/hub/mcp_server.py` reads `AW_DECISION_TIMEOUT` and `AW_QUESTION_TIMEOUT`, falling back
      to today's constants on absent, malformed or out-of-range values.
- [ ] 2.2 `hub/hub/api/v1/agent_trigger.py` puts both in the spawn environment, beside
      `AW_WORKSPACE_DIR`.
- [ ] 2.3 The Codex app-server wait uses the agent's permission value directly rather than the
      module constant.
- [ ] 2.4 Tests: a configured agent's values reach the environment; an unconfigured one sets nothing;
      the tool honours the variable; a malformed variable falls back rather than raising.

## 3. The Settings tab

- [ ] 3.1 Rename the `info` tab's label to "Settings" in `AgentDetailPanel.tsx`.
- [ ] 3.2 Rebuild `AgentInfoTab`'s editable bindings on `SettingsSection` / `SettingsRow`, so the
      agent's settings and the project's read as one system.
- [ ] 3.3 Add a "Waiting for you" section with the two values, `min`/`max` matching the API, and a
      description stating the measured figures.
- [ ] 3.4 `useUpdateAgentWaiting` in `api/agents.ts` (or alongside the existing bind hooks).
- [ ] 3.5 Blank input clears back to the default rather than sending 0.
- [ ] 3.6 Frontend tests: renders current values, saves a change, clears to default, respects bounds.

## 4. Close out

- [ ] 4.1 `pytest hub/tests/ -q`, `pytest tests/ -q`, `npx vitest run`, `npx tsc --noEmit`.
- [ ] 4.2 `ruff check` every touched Python file.
- [ ] 4.3 `npm run build` and sync `hub/hub/static/ui`; verify with `diff -rq`.
- [ ] 4.4 `npx openspec validate --specs --strict`.
- [ ] 4.5 Live-verify: set a short question wait on a real agent, ask a question, and confirm it gives
      up at the configured time rather than at 240s.
