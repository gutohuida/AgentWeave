## MODIFIED Requirements

### Requirement: Canonical runner event envelope
The Hub's direct-execution path SHALL normalize supported runner output into a provider-neutral parser result containing
zero or more output events, an independent optional usage sample, optional session changes, and
control flags.

Each output event SHALL contain a `kind`, readable `content`, and versioned structured `payload`.

#### Scenario: One provider line produces multiple events
- **WHEN** a provider line contains multiple independently displayable content blocks
- **THEN** the parser result SHALL preserve those blocks as ordered output events

#### Scenario: Usage arrives without displayable output
- **WHEN** a provider event reports token usage but has no user-readable content
- **THEN** the parser result SHALL preserve the usage sample without fabricating an output event

---

### Requirement: Closed event-kind taxonomy
Normalized output events SHALL use exactly one of `text`, `thinking`, `tool_use`, `tool_result`,
`status`, `diagnostic`, or `error`.

Successful run completion SHALL be represented as `status`; failed run completion SHALL be
represented as `error`; a failed tool invocation SHALL remain `tool_result` with `is_error=true`.

#### Scenario: Runner completes successfully
- **WHEN** a runner reports successful turn completion
- **THEN** the Hub SHALL emit a `status` event whose payload phase is `completed`

#### Scenario: Tool returns an error
- **WHEN** a tool result reports failure
- **THEN** the Hub SHALL emit a `tool_result` event with `is_error=true` rather than a top-level `error`

---

### Requirement: Run identity and deterministic ordering
Every Hub-triggered run SHALL receive a unique `run_id`, and each emitted event within that
run SHALL receive a monotonically increasing `sequence` assigned after normalization.

#### Scenario: Events share an invocation
- **WHEN** multiple output events are emitted by one runner invocation
- **THEN** they SHALL share a `run_id` and have strictly increasing sequence values

#### Scenario: Runner is retried
- **WHEN** the Hub starts another process attempt after a stale-session or transient failure
- **THEN** the new invocation SHALL receive a new `run_id`

---

### Requirement: Supported runner normalization
The system SHALL normalize the installed or documented streaming formats for Claude and Codex into
the canonical event contract.

#### Scenario: Claude emits content blocks
- **WHEN** Claude emits readable thinking, text, tool-use, tool-result, result, or error data
- **THEN** the adapter SHALL map each item to the corresponding canonical event and retain usage separately

#### Scenario: Codex emits JSONL items
- **WHEN** Codex emits reasoning, agent-message, command, file-change, MCP-call, web-search,
  plan-update, lifecycle, or error events
- **THEN** the adapter SHALL map them to canonical events without exposing raw JSONL as user content

---

### Requirement: Unknown provider events degrade safely
Runner adapters SHALL tolerate syntactically valid provider events that they do not recognize.
They SHALL either omit non-user-relevant events or emit bounded `diagnostic` events without
terminating the runner stream.

#### Scenario: Provider adds a new event type
- **WHEN** an adapter receives a valid but unknown event type
- **THEN** parsing SHALL continue and later recognized events SHALL still be emitted

#### Scenario: Stream line is malformed
- **WHEN** a runner produces malformed structured output
- **THEN** the Hub SHALL preserve a bounded diagnostic or readable fallback and continue when safe

---

### Requirement: Structured payload safety
The Hub SHALL recursively redact known secret patterns before transport and SHALL NOT persist
complete raw provider events, opaque reasoning blobs, or encrypted reasoning fields.

The serialized payload SHALL be at most 64 KiB, and a retained tool-result excerpt SHALL be at most
8 KiB. Truncated payloads SHALL preserve readable content and set `truncated=true`.

#### Scenario: Tool input contains a secret
- **WHEN** normalized structured input contains a recognized credential or secret
- **THEN** the secret SHALL be redacted before the event leaves the Hub's direct-execution path

#### Scenario: Tool output exceeds its bound
- **WHEN** a tool result is larger than 8 KiB
- **THEN** the stored result excerpt SHALL be bounded, the summary SHALL remain readable, and `truncated` SHALL be true

#### Scenario: Provider emits opaque reasoning
- **WHEN** a provider event contains encrypted or otherwise opaque reasoning data
- **THEN** that field SHALL NOT be copied into content or payload

---

### Requirement: Additive Hub persistence and transport
Agent output persistence, creation requests, responses, and SSE events SHALL support nullable
`kind`, `payload`, `run_id`, and `sequence` fields in addition to existing content, session, and
timestamp fields.

The Hub SHALL validate allowed kinds and payload bounds independently of upstream parser validation.

#### Scenario: New producer posts a structured event
- **WHEN** the Hub receives valid content with structured stream fields
- **THEN** it SHALL persist and return those fields through REST and SSE

#### Scenario: Hub receives an invalid kind or oversized payload
- **WHEN** an output creation request violates the event contract
- **THEN** the Hub SHALL reject the structured fields with a validation response and SHALL NOT persist unsafe payload data

---

### Requirement: Shared stream renderer
The Hub UI SHALL use one shared structured-event renderer for the agent output panel, spec chat,
and agent activity views. Rendering logic SHALL use `kind` and payload fields rather than string
prefix inspection when structured fields are present.

#### Scenario: Same event appears on different surfaces
- **WHEN** a structured event is shown in agent output, spec chat, and agent activity
- **THEN** all surfaces SHALL use the same semantic label, severity, and content treatment

#### Scenario: Legacy prefixed content appears
- **WHEN** a text-only legacy event contains an existing pre-canonical content prefix
- **THEN** compatibility handling SHALL preserve current visibility behavior without affecting structured events

---

### Requirement: Stream contract conformance tests
The repository SHALL include representative fixtures and tests for every supported runner adapter,
event persistence and delivery, legacy compatibility, payload bounds and redaction, ordering, and
shared UI rendering behavior.

#### Scenario: Provider fixture suite runs
- **WHEN** the stream adapter tests execute
- **THEN** fixtures for Claude and Codex SHALL produce the expected canonical events

#### Scenario: UI contract tests run
- **WHEN** the Hub UI test or build verification executes
- **THEN** structured and legacy records SHALL type-check and render through the shared component

