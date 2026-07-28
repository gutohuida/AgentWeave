## 1. Hub Backend — Emit `[NewSession]` marker

- [ ] 1.1 In `hub/hub/api/v1/agent_trigger.py`, when `session_mode == "new"`, append `\n\n[NewSession]` to `content_parts` (alongside the existing `[Session: <id>]` logic for `'resume'`)
- [ ] 1.2 Verify that `TriggerAgentResponse` and SSE broadcast are unchanged (no schema changes needed)

## 2. Watchdog — Direct trigger session fallback + `[NewSession]` parsing

- [ ] 2.1 In `watchdog.py _make_direct_trigger_callback()`, after parsing the `[Session:...]` tag, add a check for `[NewSession]` in content — if found, set `session_id = None` (explicit new session)
- [ ] 2.2 If neither `[Session:...]` nor `[NewSession]` is found, fall back to `_load_agent_session(recipient)` instead of leaving `session_id = None`
- [ ] 2.3 Update the comment block (lines 1285–1287) to reflect the new three-way logic

## 3. Watchdog — Persistent triggered-message tracking

- [ ] 3.1 Add a helper `_load_triggered_ids(max_age_hours=24) -> Set[str]` that reads `.agentweave/triggered_direct.json`, prunes entries older than 24h, and returns the set of recent IDs
- [ ] 3.2 Add a helper `_save_triggered_id(msg_id: str)` that appends `{msg_id: iso_timestamp}` to `.agentweave/triggered_direct.json`, suppressing exceptions and logging a warning on failure
- [ ] 3.3 In `_make_direct_trigger_callback()`, initialize `seen` from `_load_triggered_ids()` on callback creation (not per poll — load once at startup)
- [ ] 3.4 After successfully adding `msg_id` to `seen` and before spawning the thread, call `_save_triggered_id(msg_id)`

## 4. Hub UI — Disable send while sessions loading

- [ ] 4.1 In `AgentPromptPanel.tsx`, add `isLoadingSessions` to the send button's disabled condition: `disabled={isSending || isAgentRunning || isLoadingSessions || !message.trim()}`
- [ ] 4.2 Optionally show a subtle loading indicator (spinner or greyed placeholder) in the session selector while `isLoadingSessions` is true

## 5. Gitignore

- [ ] 5.1 Add `.agentweave/triggered_direct.json` to `.gitignore` (alongside existing `.agentweave/` runtime exclusions)

## 6. Tests

- [ ] 6.1 Add unit test for `_load_triggered_ids`: verify it returns only IDs within 24h and prunes old entries
- [ ] 6.2 Add unit test for `_save_triggered_id`: verify it writes correctly and suppresses exceptions
- [ ] 6.3 Add test for the updated `_make_direct_trigger_callback` logic: `[Session:...]` → resume, `[NewSession]` → new, no tag → fallback to saved session
- [ ] 6.4 Add test for `agent_trigger.py`: verify `[NewSession]` appears in content when `session_mode == "new"`
