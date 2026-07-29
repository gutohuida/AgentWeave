## ADDED Requirements

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

### Requirement: OpenCode context mapping

For OpenCode, the canonical source SHALL be the latest usable `step_finish.part.tokens` sample.
Context tokens SHALL equal `tokens.total - tokens.reasoning`. The collector SHALL use the current
model's effective input limit when declared, otherwise its effective context fallback.

The collector SHALL NOT accumulate token values across step-finish events and SHALL NOT depend
primarily on an AgentWeave hard-coded model-limit table.

#### Scenario: OpenCode performs a second model step
- **WHEN** the second step moves prior input into `cache.read`
- **THEN** the second step SHALL replace the first context sample

#### Scenario: OpenCode reports reasoning separately
- **WHEN** a step total includes separately reported reasoning tokens
- **THEN** reasoning tokens SHALL be excluded from the retained context count

#### Scenario: OpenCode model metadata includes an input limit
- **WHEN** the active model declares both context and input limits
- **THEN** the effective input limit SHALL be used for the context percentage

### Requirement: Copilot context mapping

For GitHub Copilot, the watchdog SHALL configure an invocation-unique OTel JSONL exporter before
process spawn with prompt/response content capture disabled. The canonical source SHALL be the
latest relevant top-level child `chat` span, not the aggregate `invoke_agent` span.

`gen_ai.usage.input_tokens` SHALL be used directly with `basis=latest_request_input`.
`gen_ai.usage.cache_read.input_tokens` and
`gen_ai.usage.cache_creation.input_tokens` SHALL be retained only as breakdowns because OTel
defines them as included in the input total.

#### Scenario: Copilot emits an aggregate parent and child chat spans
- **WHEN** an invocation contains one parent `invoke_agent` span and multiple child `chat` spans
- **THEN** the latest relevant top-level child chat span SHALL provide the sample

#### Scenario: Copilot telemetry contains cache attributes
- **WHEN** the selected chat span contains input and cache token attributes
- **THEN** cache fields SHALL NOT be added to `gen_ai.usage.input_tokens`

#### Scenario: Copilot content capture is disabled
- **WHEN** the watchdog configures token telemetry
- **THEN** prompt, response, system instruction, and tool-definition content SHALL NOT be enabled or persisted

### Requirement: Kimi 0.29 context mapping

For Kimi 0.29.x, the canonical source SHALL be session status or the latest matching main-agent
completed-step usage plus model capability metadata. Context tokens SHALL equal:

`inputOther + inputCacheRead + inputCacheCreation + output`.

The effective limit SHALL be `max_input_tokens ?? max_context_tokens` from the active model
capability. `llm.request.maxTokens` SHALL NOT be used as a context limit, and accumulated
`usage.record` accounting SHALL NOT replace the latest context-size observation.

#### Scenario: Kimi session status is available
- **WHEN** status supplies context tokens, effective limit, and ratio for the active session
- **THEN** the collector SHALL normalize those values as the measured provider-context sample

#### Scenario: Kimi status service is unavailable
- **WHEN** the collector can resolve a matching completed step and model capability
- **THEN** it SHALL reproduce Kimi 0.29.x context-size arithmetic from those values

#### Scenario: Only completion maxTokens is present
- **WHEN** a Kimi Wire request contains `llm.request.maxTokens` but no model context capability
- **THEN** the collector SHALL omit the limit and percentage rather than treating completion capacity as context capacity

### Requirement: Auxiliary collectors are invocation and session bound

Auxiliary usage collectors SHALL be configured and resolved by the runner invocation coordinator.
Codex rollout, Copilot OTel, and Kimi status/Wire sources SHALL be associated with the active
provider session and SHALL NOT be selected through an unscoped newest-file heuristic.

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
A watchdog restart SHALL reconstruct session binding before accepting auxiliary observations.

#### Scenario: User starts a new session
- **WHEN** the watchdog launches without resuming the prior provider session
- **THEN** the old context percentage SHALL disappear before the new session's first sample

#### Scenario: Old file receives a late write
- **WHEN** a late observation belongs to the previous provider session
- **THEN** it SHALL NOT overwrite the active session's context snapshot

#### Scenario: Watchdog restarts
- **WHEN** the watchdog resumes an existing provider session after restart
- **THEN** the next accepted sample SHALL reflect that session without relying on stale in-memory deltas

### Requirement: Canonical context persistence and delivery

The pipeline SHALL use the canonical context sample schema for the local context file, HTTP
transport request, Hub validation/storage event, SSE projection, `AgentSummary.context_usage`, and
UI API type.

The Hub SHALL validate enums, numeric ranges, bounded identifiers, bounded breakdown keys, and
percentage consistency. Invalid payloads SHALL be rejected rather than stored as arbitrary
dictionaries.

#### Scenario: Watchdog posts a measured sample
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

Installed-runner smoke tests SHALL inspect only event and token metadata and SHALL document runners
that could not be executed. Copilot implementation completion SHALL require a current real fixture
when the CLI becomes available.

#### Scenario: Provider arithmetic suite runs
- **WHEN** context adapter tests execute
- **THEN** Claude, Codex, OpenCode, Copilot, and Kimi 0.29.x fixtures SHALL produce their specified canonical samples without cache double-counting

#### Scenario: Full normalized pipeline is tested
- **WHEN** the context pipeline integration suite executes
- **THEN** a canonical sample SHALL survive local writing, HTTP validation, Hub storage/projection, and UI normalization without field-name drift

#### Scenario: Runner cannot provide a measured sample
- **WHEN** a fixture represents missing telemetry, missing limit, or an unsupported runner
- **THEN** the pipeline SHALL preserve the appropriate honest status instead of silently swallowing the state
