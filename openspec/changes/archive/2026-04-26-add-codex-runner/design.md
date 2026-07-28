## Context

AgentWeave has a pluggable runner system defined in `constants.py` (`RUNNER_CONFIGS`) and dispatched by the watchdog. Adding a new runner means: (1) declaring its CLI shape in `RUNNER_CONFIGS`, (2) teaching the watchdog to build and parse its commands, and (3) wiring up Hub UI controls. The OpenCode runner (`opencode`) is the closest precedent — it also uses a subcommand (`run`), a `--file` context flag, and JSON output.

Codex CLI research (validated via live testing) established:
- Headless: `codex exec --json "<prompt>"`
- Resume: `codex exec resume <thread_id> "<prompt>"` — thread_id comes from `{"type":"thread.started","thread_id":"<uuid>"}` (first JSONL event)
- Thread ID is stable across resumes when the process completes normally; rotating only when killed prematurely
- Context injection: `-c model_instructions_file=<path>`
- MCP: `codex mcp add <name> -- <server_cmd>` (identical pattern to Claude)
- Memory (cross-session): `-c memory_mode=disabled` to turn off
- Compaction: automatic server-side (OpenAI encrypted blob) — no manual trigger
- Stderr noise: `"failed to record rollout items"` is harmless and expected

## Goals / Non-Goals

**Goals:**
- Full watchdog automation: auto-ping, session resumption, context injection
- MCP setup via `agentweave mcp-setup`
- `runner_options` config block in `agentweave.yml` (Codex-specific: `memory`)
- Context bar in Mission Control fed from `turn.completed` token usage
- Mission Control Compact adapted (auto-managed badge) and Reset Context adapted (watchdog-direct path)
- `codex` color badge in AgentCard

**Non-Goals:**
- Codex interactive/TUI mode — watchdog only drives headless `exec`
- Supporting Codex's `--output-schema`, skills system, or sub-agents
- Gemini or other new runners (this change is Codex only)
- Exposing Codex's memory contents or summaries in the Hub UI

## Decisions

### D1: Session ID field name — `thread_id` not `session_id`

Codex emits `{"type":"thread.started","thread_id":"..."}`. The existing watchdog JSONL parser looks for `session_id`. Rather than adding a special case inline, we introduce `session_id_field` and `session_event_type` keys in `RUNNER_CONFIGS` so the parser stays data-driven.

**Alternative considered**: Hardcode Codex-specific parsing in `_parse_jsonl_session_id()`. Rejected — couples the parser to runner names.

### D2: Context injection via `-c model_instructions_file=<path>`

The `-c key=value` pattern differs from kimi's `--agent-file <path>` and opencode's `--file <path>`. We introduce a `context_flag` shape that can be either `["--flag", "{path}"]` (existing) or `["-c", "key={path}"]` (new). The watchdog command builder checks the shape and expands accordingly.

**Alternative considered**: Prepend context file contents directly into the prompt. Rejected — makes prompts very large and loses the structured injection benefit.

### D3: `runner_options` as a new agentweave.yml key

Rather than adding a flat `codex_memory` key (which only makes sense for Codex), we introduce a `runner_options` dict. This sets a pattern for future runner-specific config (e.g., Gemini's `thinking_budget`, OpenCode's `ollama_host`). The watchdog reads `runner_options` and maps known keys to CLI flags per runner.

**Alternative considered**: Flat `codex_memory: bool` key. Rejected — doesn't scale, pollutes the shared config key namespace.

### D4: Compact button replaced, not hidden

Showing "Auto-managed" (disabled badge with tooltip) is more informative than hiding the button. Users shouldn't think the feature is missing — they should understand Codex handles it differently. The button renders as a static badge when `agent.runner === 'codex'`.

### D5: Reset Context bypasses inbox for Codex

For Claude agents, Reset Context sends a message to the agent's inbox and relies on the agent to cooperate (save checkpoint, etc.). Codex agents don't poll their inbox between turns — the watchdog owns the session lifecycle entirely. Reset Context for Codex deletes `.agentweave/agents/<agent>-session.json` directly. The watchdog detects a `new_session_request` event and dispatches differently based on runner type.

**Alternative considered**: Send inbox message anyway and let user manually trigger. Rejected — Codex won't read it until the next watchdog ping, creating confusion.

### D6: Context limit constants per Codex model

`turn.completed` provides token counts but not the limit. We add `CODEX_MODEL_CONTEXT_LIMITS` in `constants.py` (e.g., `{"gpt-5.5": 272000, "gpt-4o": 128000}`). If the model is unknown, fall back to 128000 (conservative). The watchdog computes `percent = (input_tokens + output_tokens) / limit` and writes the context_usage file.

## Risks / Trade-offs

- **Codex JSONL schema is undocumented** — no formal spec exists (open GitHub issue). We rely on observed behavior. → Mitigation: parse defensively; log and skip unknown event types rather than crashing.
- **`"failed to record rollout items"` stderr noise** — harmless but could confuse users reading raw output. → Mitigation: watchdog stderr filter suppresses this specific line for Codex runner.
- **thread_id rotation on premature kill** — if the process is SIGPIPEd (e.g., piped through `head`), the session isn't saved and resume creates a new thread silently. → Mitigation: watchdog always reads stdout to completion before processing; never uses piped subprocesses that could kill Codex early.
- **Memory system may conflict with injected context** — Codex's cross-session memory may reinforce stale project assumptions. → Mitigation: `runner_options.memory: false` is the opt-out, documented in the agent setup guide.
- **Auto-compaction bug** — known OpenAI issue where auto-compression doesn't always trigger. → Mitigation: document as known limitation; Reset Context is the manual escape hatch.

## Migration Plan

No breaking changes. Existing runners are unaffected. `runner_options` is an additive key — agents without it behave identically. New `codex` entries in constants are additive. Hub UI changes are conditional on `agent.runner === 'codex'`.

Deployment: CLI update only (PyPI bump). Hub Docker image rebuild for UI changes.

## Open Questions

- Should `runner_options` keys be validated against a per-runner allow-list, or accepted freely? (Current proposal: free-form dict, validated at runtime when building CLI flags.)
- Should the context bar show cached tokens separately (Codex reports `cached_input_tokens` in `turn.completed`)? Could be useful for cost visibility.
