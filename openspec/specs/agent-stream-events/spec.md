# agent-stream-events Specification

## Purpose
TBD - created by archiving change add-agent-stream-kinds. Update Purpose after archive.
## Requirements
### Requirement: Canonical runner event envelope
The watchdog SHALL normalize supported runner output into a provider-neutral parser result containing
zero or more output events, an independent optional usage sample, optional session changes, and
control flags.

Each output event SHALL contain a `kind`, readable `content`, and versioned structured `payload`.

#### Scenario: One provider line produces multiple events
- **WHEN** a provider line contains multiple independently displayable content blocks
- **THEN** the parser result SHALL preserve those blocks as ordered output events

#### Scenario: Usage arrives without displayable output
- **WHEN** a provider event reports token usage but has no user-readable content
- **THEN** the parser result SHALL preserve the usage sample without fabricating an output event

### Requirement: Closed event-kind taxonomy
Normalized output events SHALL use exactly one of `text`, `thinking`, `tool_use`, `tool_result`,
`status`, `diagnostic`, or `error`.

Successful run completion SHALL be represented as `status`; failed run completion SHALL be
represented as `error`; a failed tool invocation SHALL remain `tool_result` with `is_error=true`.

#### Scenario: Runner completes successfully
- **WHEN** a runner reports successful turn completion
- **THEN** the watchdog SHALL emit a `status` event whose payload phase is `completed`

#### Scenario: Tool returns an error
- **WHEN** a tool result reports failure
- **THEN** the watchdog SHALL emit a `tool_result` event with `is_error=true` rather than a top-level `error`

### Requirement: Versioned kind-specific payloads
Every structured payload SHALL include `version=1` and satisfy the schema for its event kind.

Text and thinking payloads SHALL carry readable text. Tool-use and tool-result payloads SHALL carry
correlation and summary fields. Status payloads SHALL carry a lifecycle phase. Diagnostic payloads
SHALL identify stream and severity. Error payloads SHALL carry a stable code and readable message.

#### Scenario: Event is serialized
- **WHEN** a normalized event is sent to the Hub
- **THEN** its payload SHALL contain `version=1` and the fields required by its kind

#### Scenario: Payload is unavailable
- **WHEN** an old producer submits content without a structured payload
- **THEN** the Hub SHALL accept and preserve the readable content

### Requirement: Tool-call correlation
Tool-use and tool-result events SHALL retain the provider's call identifier as `call_id` whenever
the provider supplies one, and SHALL preserve a readable tool name and summary.

#### Scenario: Tool call has a provider identifier
- **WHEN** a provider emits a tool invocation followed by its result
- **THEN** both normalized events SHALL carry the same `call_id`

#### Scenario: Provider omits a call identifier
- **WHEN** a provider emits tool activity without a call identifier
- **THEN** the events SHALL remain renderable as unpaired tool activity without inventing a provider identifier

### Requirement: Run identity and deterministic ordering
Every watchdog invocation SHALL receive a unique `run_id`, and each emitted event within that
invocation SHALL receive a monotonically increasing `sequence` assigned after normalization.

#### Scenario: Events share an invocation
- **WHEN** multiple output events are emitted by one runner invocation
- **THEN** they SHALL share a `run_id` and have strictly increasing sequence values

#### Scenario: Runner is retried
- **WHEN** the watchdog starts another process attempt after a stale-session or transient failure
- **THEN** the new invocation SHALL receive a new `run_id`

### Requirement: Supported runner normalization
The system SHALL normalize the installed or documented streaming formats for Claude, Codex,
OpenCode, GitHub Copilot, and Kimi into the canonical event contract.

Kimi conformance SHALL target the supported v0.29.x print stream; existing Kimi v1 compatibility
SHALL be preserved but SHALL NOT be expanded by this change.

#### Scenario: Claude emits content blocks
- **WHEN** Claude emits readable thinking, text, tool-use, tool-result, result, or error data
- **THEN** the adapter SHALL map each item to the corresponding canonical event and retain usage separately

#### Scenario: Codex emits JSONL items
- **WHEN** Codex emits reasoning, agent-message, command, file-change, MCP-call, web-search,
  plan-update, lifecycle, or error events
- **THEN** the adapter SHALL map them to canonical events without exposing raw JSONL as user content

#### Scenario: OpenCode emits JSON events
- **WHEN** OpenCode emits message, tool, step-finish, lifecycle, diagnostic, or failure data
- **THEN** the adapter SHALL map the recognized data and safely ignore or summarize unknown event variants

#### Scenario: Copilot emits stream events
- **WHEN** GitHub Copilot emits assistant reasoning, messages, tool execution, lifecycle, diagnostic, or error data
- **THEN** the adapter SHALL map them to canonical events

#### Scenario: Kimi v0.29 emits sequential messages
- **WHEN** Kimi v0.29.x emits assistant, tool-use, tool-result, lifecycle, or error messages
- **THEN** the adapter SHALL retain readable content and tool identifiers in canonical events

### Requirement: Unknown provider events degrade safely
Runner adapters SHALL tolerate syntactically valid provider events that they do not recognize.
They SHALL either omit non-user-relevant events or emit bounded `diagnostic` events without
terminating the runner stream.

#### Scenario: Provider adds a new event type
- **WHEN** an adapter receives a valid but unknown event type
- **THEN** parsing SHALL continue and later recognized events SHALL still be emitted

#### Scenario: Stream line is malformed
- **WHEN** a runner produces malformed structured output
- **THEN** the watchdog SHALL preserve a bounded diagnostic or readable fallback and continue when safe

### Requirement: Structured payload safety
The watchdog SHALL recursively redact known secret patterns before transport and SHALL NOT persist
complete raw provider events, opaque reasoning blobs, or encrypted reasoning fields.

The serialized payload SHALL be at most 64 KiB, and a retained tool-result excerpt SHALL be at most
8 KiB. Truncated payloads SHALL preserve readable content and set `truncated=true`.

#### Scenario: Tool input contains a secret
- **WHEN** normalized structured input contains a recognized credential or secret
- **THEN** the secret SHALL be redacted before the event leaves the watchdog

#### Scenario: Tool output exceeds its bound
- **WHEN** a tool result is larger than 8 KiB
- **THEN** the stored result excerpt SHALL be bounded, the summary SHALL remain readable, and `truncated` SHALL be true

#### Scenario: Provider emits opaque reasoning
- **WHEN** a provider event contains encrypted or otherwise opaque reasoning data
- **THEN** that field SHALL NOT be copied into content or payload

### Requirement: Additive Hub persistence and transport
Agent output persistence, creation requests, responses, and SSE events SHALL support nullable
`kind`, `payload`, `run_id`, and `sequence` fields in addition to existing content, session, and
timestamp fields.

The Hub SHALL validate allowed kinds and payload bounds independently of watchdog validation.

#### Scenario: New producer posts a structured event
- **WHEN** the Hub receives valid content with structured stream fields
- **THEN** it SHALL persist and return those fields through REST and SSE

#### Scenario: Hub receives an invalid kind or oversized payload
- **WHEN** an output creation request violates the event contract
- **THEN** the Hub SHALL reject the structured fields with a validation response and SHALL NOT persist unsafe payload data

### Requirement: Cross-version compatibility
The system SHALL remain compatible with existing text-only producers, text-only database rows, and
clients that ignore unknown response fields. Every new structured event SHALL retain meaningful
`content` as a plain-text and accessibility fallback.

#### Scenario: Legacy row is read
- **WHEN** an output row has null structured fields
- **THEN** APIs and UI SHALL treat it as ordinary plain text

#### Scenario: New CLI posts to an older Hub
- **WHEN** an older Hub ignores unsupported optional structured fields
- **THEN** readable content SHALL still represent the event

### Requirement: Chat history preserves stream semantics
When agent output is projected into per-agent chat history, the projection SHALL retain available
stream kind, payload, run identity, sequence, and timestamp rather than flattening the record back
to content alone.

#### Scenario: Structured output appears in spec chat
- **WHEN** chat history includes a thinking or tool event
- **THEN** the chat response SHALL provide the fields required by the shared renderer

### Requirement: Recent output retrieval
The default bounded output query SHALL return the newest N matching records and present those
records in chronological order with deterministic tie-breaking.

Incremental queries SHALL continue from their cursor in chronological order.

#### Scenario: More than N output rows exist
- **WHEN** a client requests output without a cursor and more than N matching rows exist
- **THEN** the response SHALL contain the newest N rows ordered oldest-to-newest

#### Scenario: Timestamps are equal
- **WHEN** two matching records have equal timestamps
- **THEN** run sequence and record ID SHALL provide stable ordering

### Requirement: Shared stream renderer
The Hub UI SHALL use one shared structured-event renderer for the agent output panel, spec chat,
and agent activity views. Rendering logic SHALL use `kind` and payload fields rather than string
prefix inspection when structured fields are present.

#### Scenario: Same event appears on different surfaces
- **WHEN** a structured event is shown in agent output, spec chat, and agent activity
- **THEN** all surfaces SHALL use the same semantic label, severity, and content treatment

#### Scenario: Legacy prefixed content appears
- **WHEN** a text-only legacy event contains an existing watchdog prefix
- **THEN** compatibility handling SHALL preserve current visibility behavior without affecting structured events

### Requirement: Thinking presentation
Consecutive thinking events in one run SHALL render as a grouped live section. The section SHALL
automatically collapse when the first text event or terminal lifecycle event for that run arrives,
and SHALL remain user-expandable with a duration summary when timestamps permit.

#### Scenario: Thinking transitions to answer
- **WHEN** a run emits thinking followed by text
- **THEN** the thinking group SHALL collapse and the text SHALL remain visible

#### Scenario: Thinking is still live
- **WHEN** the latest event in an active run is thinking
- **THEN** the current thinking group SHALL remain visibly active

### Requirement: Tool and diagnostic presentation
Correlated tool-use and tool-result events SHALL render as a compact paired activity that can
expand to safe input and result details. Errors SHALL remain prominent, while diagnostics SHALL be
visually distinct and hideable without hiding errors or tool failures.

#### Scenario: Tool pair is rendered
- **WHEN** tool-use and tool-result events share a call ID
- **THEN** the UI SHALL present one expandable tool activity with its completion or failure state

#### Scenario: User hides diagnostics
- **WHEN** diagnostic visibility is disabled
- **THEN** diagnostic events SHALL be hidden while error events and failed tool results remain visible

### Requirement: Stream contract conformance tests
The repository SHALL include representative fixtures and tests for every supported runner adapter,
event persistence and delivery, legacy compatibility, payload bounds and redaction, ordering, and
shared UI rendering behavior.

#### Scenario: Provider fixture suite runs
- **WHEN** the stream adapter tests execute
- **THEN** fixtures for Claude, Codex, OpenCode, Copilot, and Kimi v0.29.x SHALL produce the expected canonical events

#### Scenario: UI contract tests run
- **WHEN** the Hub UI test or build verification executes
- **THEN** structured and legacy records SHALL type-check and render through the shared component

### Requirement: Independent context-usage boundary
The canonical runner observation SHALL keep context-usage samples separate from display events.
Context samples SHALL use the `agent-context-usage` contract and SHALL NOT be persisted as
`AgentOutput` rows or rendered as stream event kinds.

#### Scenario: Parser reports output and usage
- **WHEN** one provider event contains both readable output and token usage
- **THEN** the parser SHALL return output events and the usage sample in separate result fields

#### Scenario: Collector reports usage without output
- **WHEN** an auxiliary provider collector reports a context sample
- **THEN** the invocation coordinator SHALL deliver the context snapshot without fabricating a stream event

