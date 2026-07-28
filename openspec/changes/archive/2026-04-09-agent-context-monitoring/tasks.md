## 1. Claude Token Extraction (Phase 1)

- [x] 1.1 Add `CLAUDE_CONTEXT_LIMITS` dict to `constants.py` mapping known model name substrings to token limits, and a `_get_context_limit(model: str) -> int` helper with 200K default
- [x] 1.2 Extend `_parse_claude_stream_line()` in `watchdog.py` to detect `msg_type == "result"` and extract `usage.input_tokens`; return the usage data alongside the display string
- [x] 1.3 In the watchdog ping loop, when a result line is parsed and contains token data, write `.agentweave/shared/context_usage/<agent>.json` with percent, model, input_tokens, context_limit, warning (>=70%), critical (>=90%) fields
- [x] 1.4 On new session detection (`[NewSession]` marker or new session ID), write `{"agent": "<name>", "percent": 0, "warning": false, "critical": false}` to the context_usage file to reset the display
- [ ] 1.5 Verify the full pipeline end-to-end: run a Claude agent turn, confirm `context_usage/<agent>.json` is written, confirm Mission Control context bar populates in the Hub UI

## 2. Watchdog Checkpoint Nudge (Phase 2)

- [x] 2.1 Add `AW_CONTEXT_NUDGE_THRESHOLD` env var constant to `constants.py` (default: 20); read it in watchdog startup
- [x] 2.2 Add per-agent in-session message counter to watchdog state; increment on each new message detected in the agent's inbox/outbox, reset on new session detection
- [x] 2.3 After incrementing, check if count is a non-zero multiple of the threshold; if so, send a message to the agent via the transport with subject `"Context checkpoint reminder"` and content instructing the agent to run `/aw-checkpoint token_threshold`
- [ ] 2.4 Verify nudge is sent exactly once at threshold 20, again at 40, not in between; verify it is suppressed when threshold is 0

## 3. Mission Control UI Enhancements (Phase 3)

- [x] 3.1 Extend Hub `AgentSummary` schema and `agents.py` endpoint to include `session_started_at` (from `sessions[0].started_at`) and `last_checkpoint_at` (mtime of most recent `checkpoints/<agent>-*.md` file, served via a new Hub endpoint or included in agent summary)
- [x] 3.2 Update `MissionControlPage.tsx` to display session age below the context bar (e.g., "Session: 2h 14m") derived from `session_started_at`
- [x] 3.3 Add last checkpoint display: show elapsed time since `last_checkpoint_at`, or "No checkpoint ⚠" if absent
- [ ] 3.4 Verify Mission Control renders session age and checkpoint time correctly for agents with and without checkpoints

## 4. Kimi Wire Mode (Phase 4 — separate)

- [x] 4.1 Research Kimi wire mode session resumption: confirm the `--session` flag or equivalent works with `--wire`, document the exact launch command
- [x] 4.2 Implement `_KimiWireParser` class: JSON-RPC 2.0 event parser for `ContentPart`, `ToolCall`, `ToolResult`, `StatusUpdate`, `CompactionBegin`, `TurnEnd` events
- [x] 4.3 Wire `_KimiWireParser` into `_run_agent_subprocess`: replace `_KimiParser` when wire mode enabled, extract `context_usage` from `StatusUpdate` and write `context_usage/<agent>.json`
- [x] 4.4 On `CompactionBegin`, reset `context_usage/<agent>.json` to `percent: 0`
- [x] 4.5 Capture new session ID from wire mode turn completion and persist to `agents/<agent>-session.json`
- [ ] 4.6 Verify full Kimi wire mode streaming: run a Kimi agent turn, confirm output streams to Hub, confirm context bar populates, confirm session resumption works
