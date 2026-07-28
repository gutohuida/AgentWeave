## 1. Data Model & Constants

- [x] 1.1 Add `pilot` (bool, default False) to `session.py` agent config: `get_agent_pilot(agent)`, `set_agent_pilot(agent, enabled)` methods on Session class
- [x] 1.2 Add `pilot` to valid agent config keys in `constants.py`
- [x] 1.3 Add Hub DB migration: `pilot` (Boolean, default False) and `registered_session_id` (String, nullable) columns to Agent model in `hub/hub/db/models.py`

## 2. CLI — Pilot Flag

- [x] 2.1 Add `--pilot` / `--no-pilot` flags to `agentweave agent configure` subparser in `cli.py`
- [x] 2.2 Implement `cmd_agent_configure` pilot handling: call `session.set_agent_pilot()`, save, push to Hub
- [x] 2.3 Ensure `session.save()` includes pilot flag when pushing to Hub via `_push_session_to_hub`

## 3. CLI — Session Registration Command

- [x] 3.1 Add `agentweave session register` subcommand to `cli.py` with `--agent` and `--session` args
- [x] 3.2 Implement registration logic: call Hub endpoint (if HTTP transport) or update local `agents/{agent}-session.json`
- [x] 3.3 After registration, trigger regeneration of `.agentweave/agent-context/{agent}.md`
- [x] 3.4 Print launch command after registration (claude: `--resume` + `--append-system-prompt-file`; kimi: `--session` + prompt note)

## 4. MCP Tool — register_session

- [x] 4.1 Add `register_session(session_id: str)` tool to `src/agentweave/mcp/server.py`
- [x] 4.2 Tool calls Hub `POST /api/v1/agents/{agent}/register-session` (HTTP transport) or updates local file
- [x] 4.3 Tool regenerates agent-context file and returns launch command string
- [x] 4.4 Add `register_session` tool to `hub/hub/mcp_server.py` (Hub-side MCP)

## 5. Watchdog Guard

- [x] 5.1 In `watchdog.py` HTTP poll path (`_check_once_http`), load pilot flag for target agent before CLI execution
- [x] 5.2 Skip CLI execution for pilot agents; log debug message: "Skipping execution for pilot agent {agent}"
- [x] 5.3 Verify stale-message warning still fires for pilot agents (warning only, no execution)

## 6. Hub API

- [x] 6.1 Add `POST /api/v1/agents/{agent}/register-session` endpoint in `hub/hub/api/v1/agents.py`
- [x] 6.2 Endpoint upserts agent record with `registered_session_id`; creates agent if it doesn't exist with `pilot: true`
- [x] 6.3 Update `POST /api/v1/agent/trigger` to check pilot flag: create message in DB but return pilot-mode response, skip execution
- [x] 6.4 Include `pilot` and `registered_session_id` in agent GET response schema

## 7. Hub UI

- [x] 7.1 Add `PILOT` badge to `AgentCard.tsx` alongside runner badge (shown when `pilot: true`)
- [x] 7.2 Add `registered_session_id` display to `AgentInfoTab.tsx` labeled "Active Session" with copy button
- [x] 7.3 Add "Register Session" input form to `AgentInfoTab.tsx` (text input + submit button)
- [x] 7.4 Add `useRegisterSession` mutation hook in `hub/ui/src/api/agents.ts` calling the register-session endpoint
- [x] 7.5 Disable trigger/send button in `AgentPromptPanel.tsx` for pilot agents with tooltip "Pilot mode — agent is manually controlled"
- [x] 7.6 Update `agents.ts` API types to include `pilot: boolean` and `registered_session_id: string | null`

## 8. Tests

- [x] 8.1 Unit test: `Session.get_agent_pilot` / `set_agent_pilot` round-trips correctly
- [x] 8.2 Unit test: watchdog skips CLI execution for pilot agent, fires for non-pilot
- [x] 8.3 Integration test: `agentweave agent configure claude --pilot` updates session.json
- [x] 8.4 Integration test: `agentweave session register` prints correct launch command for claude and kimi
- [x] 8.5 Hub API test: trigger endpoint returns pilot-mode response without executing
- [x] 8.6 Hub API test: register-session endpoint stores session ID and handles upsert
