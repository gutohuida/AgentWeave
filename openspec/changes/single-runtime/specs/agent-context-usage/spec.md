## MODIFIED Requirements

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

---

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

---

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

---

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

## REMOVED Requirements

### Requirement: OpenCode context mapping

**Reason**: The OpenCode runner is dropped by single-runtime (`openspec/changes/single-runtime`) —
it was never ported off the deleted watchdog's execution path. There is no OpenCode invocation left
to produce a context sample from.

**Migration**: None. OpenCode support may return later as its own change if there is demand; this
requirement would be re-added at that point.

### Requirement: Copilot context mapping

**Reason**: The GitHub Copilot runner is dropped by single-runtime, for the same reason as OpenCode
above.

**Migration**: None. Copilot support may return later as its own change if there is demand.

### Requirement: Kimi 0.29 context mapping

**Reason**: The Kimi runner is dropped by single-runtime, for the same reason as OpenCode above.

**Migration**: None. Kimi support may return later as its own change if there is demand.
