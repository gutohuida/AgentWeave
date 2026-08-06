# agent-context-usage Specification

## Purpose
TBD - created by archiving change add-agent-stream-kinds. Update Purpose after archive.
## Requirements
### Requirement: Canonical context-usage sample

The system SHALL represent runner context usage with one canonical sample containing:

- `status`: `measured`, `estimated`, `unsupported`, or `unavailable`;
- optional non-negative `context_tokens`;
- optional positive `limit_tokens`;
- optional `percent` from 0 through 100;
- optional `model` and `session_id`;
- bounded `source`;
- `basis`: `provider_context`, `latest_request_input`, `provider_reported_ratio`, or
  `cumulative_delta`;
- `observed_at`; and
- an optional bounded numeric token breakdown.

When `context_tokens` and `limit_tokens` are present, `percent` SHALL be derived from those values.
When either is absent, `percent` SHALL be absent unless the provider directly reports a ratio.

#### Scenario: Complete measured sample is created
- **WHEN** a provider reports context tokens and an effective limit
- **THEN** the sample SHALL have `status=measured` and a percentage derived from those operands

#### Scenario: Limit is unknown
- **WHEN** context tokens are known but no trustworthy effective limit is available
- **THEN** the sample SHALL retain `context_tokens`, omit `limit_tokens` and `percent`, and SHALL NOT substitute zero

#### Scenario: Provider exposes no usable measurement
- **WHEN** a supported runner exposes neither a trustworthy context count nor ratio
- **THEN** the sample SHALL report `unavailable` without fabricating token values

### Requirement: Latest observation replaces rather than accumulates

Context usage SHALL describe the latest non-cumulative context observation for the active
top-level provider session. A later valid sample SHALL replace the previous sample for that
session; samples from separate steps, turns, or model calls SHALL NOT be summed.

#### Scenario: Cached history appears in a later request
- **WHEN** a later provider request represents previous input as cache-read tokens
- **THEN** the system SHALL replace the prior observation and SHALL NOT add the two requests together

#### Scenario: Provider reports cumulative and per-request totals
- **WHEN** both cumulative invocation usage and a latest-request or provider-context value exist
- **THEN** the latest non-cumulative value SHALL be canonical

### Requirement: Cache breakdowns are counted according to provider semantics

The system SHALL add cache fields only when the provider defines them as exclusive input
components. It SHALL NOT add cache fields to a provider-normalized input or total that already
includes them.

#### Scenario: Exclusive cache components are reported
- **WHEN** Claude or Kimi reports uncached input, cache-read input, and cache-created input as
  exclusive fields
- **THEN** the system SHALL add the applicable components exactly once

#### Scenario: Inclusive cache breakdown is reported
- **WHEN** Codex or Copilot reports cached input as a subset of an inclusive input total
- **THEN** the system SHALL retain the cache value as a breakdown and SHALL NOT add it to context tokens

### Requirement: Claude context mapping

For Claude and Claude-proxy runners, the canonical context source SHALL be the latest
assistant-message request usage. The latest-request measurement SHALL equal:

`input_tokens + cache_read_input_tokens + cache_creation_input_tokens`.

A final-result usage record MAY be used only as a fixture-proven fallback for a supported stream
shape. Unknown model limits SHALL produce a token-only sample.

#### Scenario: Claude reports cached input
- **WHEN** a Claude assistant message reports all three input classes
- **THEN** the sample SHALL add the three fields once and use `basis=latest_request_input`

#### Scenario: Claude final result differs from assistant usage
- **WHEN** both records exist and their usage differs
- **THEN** the assistant-message request usage SHALL take precedence

### Requirement: Codex context mapping

For a non-ephemeral Codex session, the canonical source SHALL be the latest matching rollout
`token_count.info` record. Context tokens SHALL equal
`last_token_usage.total_tokens - last_token_usage.reasoning_output_tokens`, and the effective
limit SHALL be `model_context_window`.

Codex stdout `turn.completed.usage` SHALL be treated as cumulative. A delta from cumulative values
MAY be emitted only as `status=estimated`, `basis=cumulative_delta`, when the exact rollout cannot
be resolved.

#### Scenario: Resumed Codex turn reports cumulative stdout usage
- **WHEN** resumed-turn stdout totals include previous turns
- **THEN** the collector SHALL use matching rollout `last_token_usage` instead

#### Scenario: Codex reports cached input
- **WHEN** `last_token_usage` contains `cached_input_tokens`
- **THEN** that value SHALL remain a breakdown and SHALL NOT be added to `input_tokens`

#### Scenario: Rollout is unavailable
- **WHEN** no matching rollout record can be resolved but consecutive cumulative observations are available
- **THEN** any delta sample SHALL be visibly estimated and SHALL NOT be presented as measured

### Requirement: Auxiliary collectors are invocation and session bound

Auxiliary usage collectors SHALL be configured and resolved by the runner invocation coordinator.
Codex rollout sources SHALL be associated with the active provider session and SHALL NOT be
selected through an unscoped newest-file heuristic.

Collectors SHALL tolerate partial records and perform a final bounded poll after stdout closes.

#### Scenario: Multiple provider sessions exist on disk
- **WHEN** auxiliary files for multiple sessions are present
- **THEN** the collector SHALL accept records only from the active session or a strictly verified bounded fallback

#### Scenario: Auxiliary record is written after final stdout
- **WHEN** a matching token record arrives while the process is closing
- **THEN** the final bounded collector poll SHALL make it eligible for delivery

#### Scenario: Auxiliary JSONL has a partial final line
- **WHEN** the collector observes a record still being written
- **THEN** it SHALL skip or retry that record without terminating the runner

### Requirement: Session isolation and reset

Context snapshots SHALL be keyed to the active agent and provider session. Starting a new session
SHALL immediately replace the prior display with `unavailable` until a valid sample for the new
session arrives.

Samples tied to an old session, earlier invocation boundary, or mismatched agent SHALL be rejected.

#### Scenario: User starts a new session
- **WHEN** the Hub launches a run without resuming the prior provider session
- **THEN** the old context percentage SHALL disappear before the new session's first sample

#### Scenario: Old file receives a late write
- **WHEN** a late observation belongs to the previous provider session
- **THEN** it SHALL NOT overwrite the active session's context snapshot

### Requirement: Canonical context persistence and delivery

The pipeline SHALL use the canonical context sample schema for the local context file, HTTP
transport request, Hub validation/storage event, SSE projection, `AgentSummary.context_usage`, and
UI API type.

The Hub SHALL validate enums, numeric ranges, bounded identifiers, bounded breakdown keys, and
percentage consistency. Invalid payloads SHALL be rejected rather than stored as arbitrary
dictionaries.

#### Scenario: Hub-triggered run posts a measured sample
- **WHEN** a canonical sample reaches the Hub
- **THEN** the Hub SHALL preserve its status, basis, operands, percentage, source, session, model, and observation time

#### Scenario: Payload has an invalid percentage
- **WHEN** a context request contains a percentage outside 0 through 100 or inconsistent with known operands
- **THEN** the Hub SHALL reject the invalid payload

#### Scenario: SSE updates agent context
- **WHEN** the Hub stores a new valid context snapshot
- **THEN** subsequent agent summaries and real-time updates SHALL expose the same normalized fields

### Requirement: Legacy context compatibility

During rolling upgrades, readers SHALL normalize unambiguous legacy aliases including
`tokens_used`, `tokens_limit`, `input_tokens`, `context_limit`, and ratio-form `context_usage`.
Canonical writers SHALL emit only canonical fields.

Contradictory or incomplete legacy values SHALL become `unavailable` or token-only samples rather
than a fabricated zero percentage.

#### Scenario: Existing local file uses legacy token keys
- **WHEN** a reader encounters an unambiguous legacy context dictionary
- **THEN** it SHALL normalize the values into the canonical sample

#### Scenario: Legacy data claims zero without a limit
- **WHEN** a legacy payload cannot distinguish unknown from a real zero measurement
- **THEN** the UI SHALL show unavailable rather than a trusted zero-percent bar

### Requirement: Context state presentation

All Hub surfaces that present agent context SHALL consume the normalized context type and render
measured, estimated, token-only, unavailable, and unsupported states consistently.

Estimated samples SHALL be visibly labeled. Unknown limits SHALL not render a percentage.
Estimated samples SHALL NOT trigger automatic warning or critical policy in this change.

#### Scenario: Measured percentage crosses a display threshold
- **WHEN** a measured sample reaches a configured warning or critical display threshold
- **THEN** every context surface SHALL apply the corresponding consistent visual state

#### Scenario: Estimated percentage is shown
- **WHEN** only an estimated sample is available
- **THEN** the UI SHALL label it as estimated and SHALL NOT present it as exact

#### Scenario: Token-only sample is shown
- **WHEN** context tokens are known but the limit is unknown
- **THEN** the UI SHALL show the token count without a percentage bar value

### Requirement: Context usage is not a stream event

Context samples SHALL be delivered as replaceable agent/session snapshots and SHALL NOT be stored
as `AgentOutput`, assigned a stream event kind, or rendered by the shared stream-event renderer.

#### Scenario: One provider record contains text and usage
- **WHEN** normalization produces both a text event and a context sample
- **THEN** output persistence SHALL receive the text event and context delivery SHALL independently receive the sample

### Requirement: Context conformance and pipeline tests

The repository SHALL include versioned provider fixtures and tests for arithmetic, cache
inclusion, latest-sample selection, model limits, session binding, stale rejection, legacy
normalization, typed Hub delivery, SSE/summary projection, and UI state rendering.

#### Scenario: Provider arithmetic suite runs
- **WHEN** context adapter tests execute
- **THEN** Claude and Codex fixtures SHALL produce their specified canonical samples without cache double-counting

#### Scenario: Full normalized pipeline is tested
- **WHEN** the context pipeline integration suite executes
- **THEN** a canonical sample SHALL survive local writing, HTTP validation, Hub storage/projection, and UI normalization without field-name drift

#### Scenario: Runner cannot provide a measured sample
- **WHEN** a fixture represents missing telemetry or missing limit
- **THEN** the pipeline SHALL preserve the appropriate honest status instead of silently swallowing the state

### Requirement: Context-window size is resolved in a stated order

The size of the context window used to express usage SHALL be resolved in this order:

1. the window the provider itself reports for the model that ran the turn;
2. the window the model catalog declares for that model;
3. unknown.

A window MUST NOT be resolved from a default that does not describe the model in use.

#### Scenario: A self-reported window wins

- **WHEN** the provider reports the context window for the model that ran the turn
- **THEN** usage is expressed against that reported window

#### Scenario: The catalog fills a missing report

- **WHEN** the provider reports no context window and the catalog declares one for that model
- **THEN** usage is expressed against the catalog's declared window

#### Scenario: A substitute default is not used

- **WHEN** neither the provider nor the catalog supplies a window for the model that ran the turn
- **THEN** no window is assumed

### Requirement: Unknown context usage is reported as unknown

When the context window for a turn cannot be resolved, the Hub SHALL report usage as unknown. It
MUST NOT present a proportion, a percentage, or a pressure state derived from an unresolved window.

A condition that pauses autonomous turns MUST NOT be raised from an unresolved window.

#### Scenario: No percentage is shown for an unknown window

- **WHEN** the context window for a model cannot be resolved
- **THEN** the interface reports usage as unknown rather than as a proportion

#### Scenario: An unresolved window does not pause execution

- **WHEN** the context window for a model cannot be resolved
- **THEN** no context-pressure condition is raised for that turn

#### Scenario: Reported usage never exceeds its own window

- **WHEN** usage is expressed as a proportion of a context window
- **THEN** that window is one the provider reported or the catalog declared for the model that ran
  the turn

### Requirement: A conversation whose model changed reports usage per turn

Usage SHALL be attributed to the model that ran each turn, because a conversation may contain turns
run under different models with different context windows.

A conversation-level figure MUST NOT assume that every turn shares one context window.

#### Scenario: Turns are measured against their own model

- **WHEN** a conversation contains turns run under two models with different context windows
- **THEN** each turn's usage is expressed against the window of the model that ran it

#### Scenario: The current pressure describes the current model

- **WHEN** the operator changes a conversation's model and sends a further message
- **THEN** the reported context pressure describes the newly chosen model

