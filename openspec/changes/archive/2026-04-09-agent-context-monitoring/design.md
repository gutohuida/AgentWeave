## Context

AgentWeave's Mission Control screen renders a context bar per agent using `AgentSummary.context_usage`, which is populated from the Hub's `EventLog` table (`context_warning` events). The watchdog fires those events when it reads `context_usage/<agent>.json` files from disk — but nothing ever writes those files. The pipeline is complete except for the source.

Separately, the checkpoint system (`/aw-checkpoint` skill, `save_checkpoint` MCP tool) has never been exercised. Agents are expected to self-trigger checkpoints, but have no external forcing function.

The watchdog already streams and parses every line of Claude's `--output-format stream-json --verbose` output. The `result` JSONL message at the end of each call contains `usage.input_tokens` — the total tokens sent to the API for that turn, which equals the current context window fill. This data is already flowing; it just isn't being extracted.

For Kimi, the current `--print` mode outputs Python-repr events with no token data. Kimi's `--wire` mode (JSON-RPC 2.0) emits `StatusUpdate` events with `context_usage` (0–1 ratio), `context_tokens`, and `max_context_tokens`, plus `CompactionBegin`/`CompactionEnd` events. Wire mode requires bidirectional stdin/stdout communication vs the current one-way pipe.

## Goals / Non-Goals

**Goals:**
- Populate Mission Control context bars with real token data for Claude/claude_proxy/native agents
- Automatically nudge agents via inbox message when in-session activity crosses a threshold
- Mission Control shows session age and time since last checkpoint
- Kimi wire mode integration that preserves full Hub output streaming

**Non-Goals:**
- Real-time token counting mid-turn (we update on turn completion, not during)
- Changing the Hub API or database schema for the Claude phase
- Replacing the checkpoint mechanism itself — just triggering it more reliably
- Supporting manual-runner agents (no stream to parse)

## Decisions

### D1: Extract tokens from existing Claude stream rather than adding a new reporting mechanism

The `result` JSONL message already flows through `_parse_claude_stream_line()`. Extracting `usage.input_tokens` there and writing `context_usage/<agent>.json` requires ~20 lines of code and no new protocols, MCP tools, or agent cooperation.

**Alternative considered:** Add a `report_context_usage` MCP tool that agents call. Rejected — requires agents to self-report, which they demonstrably don't do, and agents can't reliably know their own token count anyway.

### D2: Context window size as a constants map, not queried from API

Map known model names (e.g. `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5`) to their context limits in `constants.py`. Default to 200K for unknown Claude models (all current Claude 3.x/4.x are 200K).

**Alternative considered:** Query the Anthropic API for model info. Rejected — adds a network call, adds a dependency, and the values rarely change.

### D3: Checkpoint nudge threshold based on in-session message count, not session age or task count

Session age is misleading (a QA agent registered months ago can have a fresh context). Task count is misleading (one large task can consume as much context as ten small ones). Message count since session start correlates directly with API calls made and is readily available from existing message files.

Default threshold: 20 messages in the current session. Configurable via `AW_CONTEXT_NUDGE_THRESHOLD` env var.

**Alternative considered:** Time-based threshold. Rejected — an agent can be idle for hours in the same session. Activity-based is more accurate.

### D4: Kimi wire mode as a separate, self-contained phase

Wire mode requires replacing the current one-way `kimi --print` subprocess with a bidirectional JSON-RPC 2.0 loop (write prompts to stdin, read events from stdout). This is a non-trivial refactor of `_agent_ping_cmd` and the ping loop in `watchdog.py`. Decoupling it from the Claude phase means the Claude fix (low risk, high value) ships first, and Kimi wire mode can be validated independently.

**Alternative considered:** Do both in one change. Rejected — failure in Kimi wire mode shouldn't block the Claude context bar fix.

### D5: Write context_usage files from the watchdog, not from a new background thread

The watchdog already runs the parse loop. Writing the JSON file at the end of a turn (when we see the `result` message) is synchronous and cheap. No new threads or async coordination needed.

## Risks / Trade-offs

- **`input_tokens` ≠ remaining context** — `input_tokens` is what was sent this turn; it grows as the conversation grows. It's the right metric for "how full is the context window" but it resets to 0 on a new session. If an agent starts a new session without the watchdog catching the reset, Mission Control may show stale high-percentage data until the next turn completes. → Mitigation: on `[NewSession]` marker detection (already handled in watchdog), clear the `context_usage/<agent>.json` file or write `{"percent": 0}`.

- **Model name not always available** — The session config has `runner.model` but it may be absent for default agents. → Mitigation: default to 200K when model is unknown; log a debug warning.

- **Kimi wire mode is bidirectional** — If the subprocess hangs waiting for stdin input (e.g. approval), the watchdog's read loop could block. → Mitigation: implement a timeout; wire mode phase includes integration tests with subprocess management.

- **Nudge messages may be ignored** — Agents receive the checkpoint nudge via inbox but may not act on it. → Mitigation: this is acceptable for now; the visibility gain (Mission Control showing real data) is independent of whether agents checkpoint. A follow-up can enforce checkpoint-before-compact via hooks.

## Migration Plan

1. Deploy Claude token extraction (watchdog change only) — no Hub changes, no UI changes, context bars start populating immediately.
2. Deploy Mission Control session age + last checkpoint time display — Hub API + UI change, additive only.
3. Deploy watchdog nudge logic — watchdog change only, no Hub/UI changes.
4. Kimi wire mode — coordinated watchdog refactor + integration tests.

No rollback complexity: all changes are additive. Disabling token extraction means reverting the watchdog — Mission Control falls back to "No context data" (current state).

## Open Questions

- **What threshold feels right for nudge messages?** 20 messages proposed; needs calibration from real session data once checkpoint is tested.
- **Should the nudge message block work or just inform?** Currently designed as an informational inbox message. Could be made blocking via `ask_user` if stricter enforcement is desired.
- **Kimi wire mode session resumption** — wire mode may handle `--session` differently. Needs verification against Kimi CLI docs before implementation.
