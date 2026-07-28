## Why

Mission Control exists to show context health for running agents, but it never displays real data — agents have no mechanism to report token usage, so the context bar always shows "No context data". Checkpoints exist as a mechanism but have never been triggered, leaving agents vulnerable to context degradation (worse answers as context fills) with no visibility or intervention.

## What Changes

- Watchdog extracts `input_tokens` from Claude's existing `stream-json` output and writes real context usage to `.agentweave/shared/context_usage/<agent>.json` automatically — no agent cooperation required
- Mission Control context bar populates with real token percentages instead of showing empty
- Watchdog sends automatic checkpoint nudge messages to agents when in-session message count crosses a configurable threshold
- Kimi wire mode integration (separate, later phase) replaces `--print` with `--wire` to get `context_usage` ratio and `CompactionBegin/End` events directly from Kimi
- Mission Control shows session age and last checkpoint time alongside the context bar

## Capabilities

### New Capabilities

- `stream-token-extraction`: Watchdog parses `input_tokens` from Claude's `stream-json` result message and writes `context_usage/<agent>.json` with percent, model, warning flags — feeds existing Mission Control pipeline with real data
- `watchdog-checkpoint-nudge`: Watchdog tracks in-session message count per agent; when threshold crossed, sends a direct inbox message instructing the agent to run `/aw-checkpoint`
- `kimi-wire-mode`: Replace `kimi --print` subprocess handling with `kimi --wire` JSON-RPC 2.0 bidirectional loop; extract `context_usage` ratio and detect compaction events from `StatusUpdate`, `CompactionBegin`, `CompactionEnd`

### Modified Capabilities

## Impact

- `src/agentweave/watchdog.py`: `_parse_claude_stream_line()` extended to extract usage; new threshold tracking and nudge logic; new `_KimiWireParser` class for wire mode
- `src/agentweave/constants.py`: New constants for context window sizes per model, nudge thresholds
- `hub/ui/src/components/agents/MissionControlPage.tsx`: Add session age and last checkpoint time display alongside context bar
- `hub/hub/api/v1/agents.py`: Optionally expose last checkpoint timestamp in `AgentSummary`
- No new dependencies; no breaking changes to existing transports or MCP tools
