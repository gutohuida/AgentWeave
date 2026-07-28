## ADDED Requirements

### Requirement: Kimi agents run via wire mode when configured
The watchdog SHALL launch Kimi agents using `kimi --wire` instead of `kimi --print` when wire mode is enabled, communicating via JSON-RPC 2.0 over stdin/stdout.

#### Scenario: Prompt sent via stdin JSON-RPC
- **WHEN** the watchdog pings a Kimi agent
- **THEN** it SHALL write `{"jsonrpc": "2.0", "method": "prompt", "id": "<uuid>", "params": {"user_input": "<prompt>"}}` to the subprocess stdin

#### Scenario: ContentPart events streamed to Hub
- **WHEN** the Kimi subprocess emits a `ContentPart` event with type `text`
- **THEN** the watchdog SHALL extract the `text` field and post it to the Hub as agent output, preserving streaming behaviour identical to the current `--print` mode

#### Scenario: ThinkPart events rendered with prefix
- **WHEN** the Kimi subprocess emits a `ContentPart` event with type `think`
- **THEN** the watchdog SHALL prefix each line with `💭` and post it to the Hub

#### Scenario: ToolCall events rendered
- **WHEN** the Kimi subprocess emits a `ToolCall` event
- **THEN** the watchdog SHALL render it as `🔧 <name>(<args>)` and post to Hub

### Requirement: Context usage extracted from Kimi StatusUpdate
The watchdog SHALL extract `context_usage` from Kimi `StatusUpdate` events and write `context_usage/<agent>.json`, using the same format as the Claude token extraction.

#### Scenario: StatusUpdate with context_usage populates context file
- **WHEN** a `StatusUpdate` event is received with a non-null `context_usage` field (0–1 float)
- **THEN** the watchdog SHALL write `.agentweave/shared/context_usage/<agent>.json` with `percent` = `context_usage * 100`, `context_tokens`, `max_context_tokens`, and appropriate `warning`/`critical` flags

#### Scenario: CompactionBegin event resets context usage
- **WHEN** a `CompactionBegin` event is received
- **THEN** the watchdog SHALL write `{"agent": "<name>", "percent": 0, "warning": false, "critical": false}` to the context_usage file

### Requirement: Kimi session resumption preserved in wire mode
The watchdog SHALL resume existing Kimi sessions in wire mode using the stored session ID.

#### Scenario: Session ID passed to wire mode
- **WHEN** a saved session ID exists for a Kimi agent
- **THEN** the watchdog SHALL include the session resumption parameter in the wire mode launch command

#### Scenario: New session ID captured from wire mode events
- **WHEN** a wire mode turn completes and a session ID is available in the response
- **THEN** the watchdog SHALL persist the session ID to `.agentweave/agents/<agent>-session.json`
