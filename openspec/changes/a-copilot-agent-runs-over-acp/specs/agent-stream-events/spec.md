## MODIFIED Requirements

### Requirement: Supported runner normalization
The system SHALL normalize the installed or documented streaming formats for Claude, Codex and Copilot into
the canonical event contract.

#### Scenario: Claude emits content blocks
- **WHEN** Claude emits readable thinking, text, tool-use, tool-result, result, or error data
- **THEN** the adapter SHALL map each item to the corresponding canonical event and retain usage separately

#### Scenario: Codex emits JSONL items
- **WHEN** Codex emits reasoning, agent-message, command, file-change, MCP-call, web-search,
  plan-update, lifecycle, or error events
- **THEN** the adapter SHALL map them to canonical events without exposing raw JSONL as user content

#### Scenario: Copilot emits ACP session updates
- **WHEN** Copilot emits message chunks, thought chunks, tool calls and their updates, or plan updates over the Agent Client Protocol
- **THEN** the adapter SHALL map each contiguous run of message chunks to one `text` event and each contiguous run of thought chunks to one `thinking` event
- **AND** SHALL map each tool call to one `tool_use` event and its terminal update to one `tool_result` event with the same call id
- **AND** SHALL map a plan update to a plan `status` event, emitting an unchanged plan only once

#### Scenario: Copilot reports its own errors and warnings as message text
- **WHEN** Copilot sends message text beginning `Error:`, `Warning:` or `Info:` that matches a session error, warning or info event of the same turn
- **THEN** the adapter SHALL emit an `error` event for an error and a `diagnostic` event for a warning or info, instead of a `text` event
- **AND** message text beginning the same way that matches no such event SHALL remain a `text` event

#### Scenario: Copilot runs a different model than the one requested
- **WHEN** a Copilot turn requested a named model and Copilot reports that it is running another
- **THEN** the adapter SHALL emit one `diagnostic` event naming both models and the models the plan allows

### Requirement: Stream contract conformance tests
The repository SHALL include representative fixtures and tests for every supported runner adapter,
event persistence and delivery, legacy compatibility, payload bounds and redaction, ordering, and
shared UI rendering behavior.

Copilot's fixtures SHALL be taken from captured Copilot transcripts, in the order Copilot sent them,
including the prompt response arriving after the turn's session updates.

#### Scenario: Provider fixture suite runs
- **WHEN** the stream adapter tests execute
- **THEN** fixtures for Claude, Codex and Copilot SHALL produce the expected canonical events

#### Scenario: UI contract tests run
- **WHEN** the Hub UI test or build verification executes
- **THEN** structured and legacy records SHALL type-check and render through the shared component

## ADDED Requirements

### Requirement: A resumed Copilot session's history is not rendered again

The Hub SHALL NOT turn the history Copilot replays when a session is loaded into new timeline events, and SHALL begin mapping a Copilot turn's session updates only once that turn's prompt has been sent.

A loaded Copilot session replays its earlier messages as ordinary message updates. Rendering them
again would show the operator every earlier turn a second time, attributed to the new run.

When a session the conversation is bound to no longer exists in Copilot, the Hub SHALL start a new
session and bind the conversation to it. It SHALL say so in the run's timeline rather than fail the
turn. Any other failure to load SHALL fail the turn.

#### Scenario: A resumed turn shows only its own output

- **WHEN** a conversation bound to a Copilot session receives a second turn and Copilot replays the first turn while loading
- **THEN** the second run's timeline contains only events produced after its prompt was sent

#### Scenario: A bound session Copilot no longer has

- **WHEN** a conversation's bound Copilot session cannot be found by Copilot
- **THEN** the Hub starts a new session, binds the conversation to it, and the run's timeline says a new session was started
