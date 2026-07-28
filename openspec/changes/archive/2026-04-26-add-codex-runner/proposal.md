## Why

AgentWeave supports Claude Code, Kimi, and OpenCode as automated runners, but lacks support for OpenAI's Codex CLI — the most direct competitor to Claude Code and a tool many users already have. Adding Codex as a native runner expands AgentWeave's reach to OpenAI users and makes multi-provider teams (e.g., Claude as principal, Codex as delegate) practical out of the box.

## What Changes

- Add `codex` as a new runner type in `RUNNER_TYPES` and `RUNNER_CONFIGS` with full watchdog automation
- Watchdog builds and executes `codex exec --json` commands, parses `thread.started` events for session IDs, and resumes via `codex exec resume <thread_id>`
- Context injection via `-c model_instructions_file=<path>` (per-agent `.agentweave/agents/<agent>.md`)
- MCP registration via `codex mcp add <name> -- <server_cmd>` (same pattern as Claude)
- Add `runner_options` as a new top-level agent config key in `agentweave.yml` for runner-specific options; initial use: `memory: false` disables Codex's built-in cross-session memory via `-c memory_mode=disabled`
- Mission Control context bar populated from `turn.completed` JSONL usage events
- Mission Control Compact button replaced with "Auto-managed" badge for Codex agents (compaction is server-side/automatic in Codex)
- Mission Control Reset Context triggers watchdog to clear stored `thread_id` directly, bypassing inbox (Codex doesn't poll inbox between turns)
- `codex` added to `AgentCard` and `RUNNER_CONFIG` with OpenAI green color

## Capabilities

### New Capabilities

- `codex-runner`: Codex CLI runner — headless execution, session resumption, context injection, MCP setup, and watchdog automation
- `runner-options`: Per-agent runner-specific config block in `agentweave.yml` (generalises beyond Codex for future runners)
- `codex-mission-control`: Mission Control adaptations for Codex — context bar from JSONL token usage, Auto-managed compact, direct-watchdog Reset Context

### Modified Capabilities

- `opencode-runner`: `runner_options` block replaces any future ad-hoc config keys; no requirement changes to existing opencode behaviour

## Impact

- `src/agentweave/constants.py` — new runner type, config, model→context-limit map
- `src/agentweave/session.py` — `runner_options` key handling, `get_runner_options()` accessor
- `src/agentweave/watchdog.py` — Codex command builder, JSONL parser for `thread.started` / `turn.completed`, context usage reporting, new-session reset path
- `src/agentweave/validator.py` — allow `runner_options` in `VALID_AGENT_CONFIG_KEYS`
- `src/agentweave/cli.py` — `agentweave agent configure codex`, `mcp-setup` codex branch
- `hub/hub/api/v1/agents.py` — expose `runner_options` in agent response; adapt `/compact` and `/new-session` for Codex runner
- `hub/ui/src/api/agents.ts` — `AgentSummary.runner_options` field
- `hub/ui/src/components/agents/AgentCard.tsx` — add `codex` to `RUNNER_CONFIG`
- `hub/ui/src/components/agents/MissionControlPage.tsx` — conditional Compact / Auto-managed rendering
- New env var dependency: `CODEX_API_KEY`
