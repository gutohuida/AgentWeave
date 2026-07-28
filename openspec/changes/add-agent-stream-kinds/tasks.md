## 1. Canonical Stream Contract

- [ ] 1.1 Add typed `AgentStreamEvent` and `ParsedRunnerLine` models with events, usage, session-change, and control fields
- [ ] 1.2 Define and validate the seven event kinds and version-1 kind-specific payload schemas
- [ ] 1.3 Add constructors that always produce meaningful readable `content` fallbacks
- [ ] 1.4 Add recursive payload redaction using the existing secret-redaction behavior
- [ ] 1.5 Add deterministic 64 KiB payload and 8 KiB tool-result excerpt limits with truncation metadata
- [ ] 1.6 Add unit tests for constructors, schema validation, nested redaction, truncation, and opaque-reasoning exclusion

## 2. Runner Adapters and Fixtures

- [ ] 2.1 Refactor the Claude parser to return the canonical result and map text, readable thinking, tools, lifecycle, errors, and usage
- [ ] 2.2 Add Claude stream fixtures covering multiple blocks, tool correlation, completion, failure, usage-only data, and unknown events
- [ ] 2.3 Refactor the Codex parser to map agent messages, reasoning, commands, file changes, MCP calls, web searches, plans, lifecycle, errors, and usage
- [ ] 2.4 Add Codex JSONL fixtures covering official item and turn event types, malformed lines, and unknown events
- [ ] 2.5 Refactor the OpenCode parser to map supported JSON message, tool, step, lifecycle, diagnostic, failure, and usage data
- [ ] 2.6 Capture or curate OpenCode 1.18.x golden fixtures and test recognized, unknown, and malformed event behavior
- [ ] 2.7 Refactor the Copilot parser to map documented reasoning, message, tool, lifecycle, diagnostic, error, and usage events
- [ ] 2.8 Curate Copilot fixtures from a current installed CLI when available, otherwise from official event examples with the source/version recorded
- [ ] 2.9 Refactor the Kimi parser around v0.29.x sequential messages, tool IDs, results, lifecycle, errors, and usage while preserving existing v1 behavior
- [ ] 2.10 Add Kimi v0.29.x golden fixtures plus regression coverage for retained v1 compatibility
- [ ] 2.11 Add cross-adapter conformance tests proving every adapter returns only canonical kinds and keeps usage separate

## 3. Watchdog Lifecycle and Transport

- [ ] 3.1 Generate a fresh opaque run ID for every runner process invocation, including retry attempts
- [ ] 3.2 Assign strictly increasing sequence values after adapter normalization and before output delivery
- [ ] 3.3 Emit canonical started, retrying, completed, skipped, and run-error lifecycle events at known runner boundaries
- [ ] 3.4 Update the runner loop to deliver zero or more normalized events from each parser result without fabricating output for usage-only lines
- [ ] 3.5 Extend `post_agent_output` transport interfaces with optional kind, payload, run ID, and sequence fields while preserving old call sites
- [ ] 3.6 Add local and HTTP transport tests for structured output, text-only fallback, redacted data, and older-Hub degradation

## 4. Hub Persistence and APIs

- [ ] 4.1 Add the next Alembic migration for nullable AgentOutput kind, JSON payload, run ID, sequence, and the run-ordering index
- [ ] 4.2 Update SQLAlchemy models and Pydantic creation/response schemas with bounded optional structured fields
- [ ] 4.3 Validate allowed kinds and serialized payload size at Hub ingress and add rejection tests
- [ ] 4.4 Persist and serialize structured fields through agent-output REST endpoints and SSE events
- [ ] 4.5 Preserve structured fields when AgentOutput records are projected into per-agent chat history
- [ ] 4.6 Correct the default output query to select the newest N records and return them in stable chronological order
- [ ] 4.7 Add Hub tests for migration upgrade, structured round trips, legacy rows, chat projection, SSE data, and stable newest-window ordering

## 5. Shared Hub UI

- [ ] 5.1 Extend UI API types and normalization helpers for optional kind, payload, run ID, and sequence fields
- [ ] 5.2 Build one shared stream renderer with a plain-text legacy adapter for null-kind records
- [ ] 5.3 Implement per-run thinking grouping, live state, automatic collapse, manual expansion, and timestamp-based duration labels
- [ ] 5.4 Implement tool-use/result pairing by run ID and call ID with expandable safe inputs, outputs, completion state, and failure state
- [ ] 5.5 Implement distinct status, diagnostic, and error treatments plus a diagnostic visibility control that never hides errors
- [ ] 5.6 Replace raw/prefix-based rendering in `AgentOutputPanel` with the shared renderer
- [ ] 5.7 Replace stream prefix filtering and rendering in `SpecPage` with the shared renderer
- [ ] 5.8 Replace activity prefix classification in `AgentActivityTab` with the shared renderer's semantic projection
- [ ] 5.9 Add component tests or deterministic rendering tests for structured events, legacy prefixes, incomplete tool pairs, thinking transitions, and diagnostics filtering

## 6. Verification and Documentation

- [ ] 6.1 Run focused watchdog and transport unit tests for all runner adapters and payload safety
- [ ] 6.2 Run the full CLI pytest suite plus ruff, black check, and mypy for affected Python code
- [ ] 6.3 Run Hub backend tests including migration upgrade and output API coverage
- [ ] 6.4 Run Hub UI type-check/build and the available renderer tests
- [ ] 6.5 Manually verify live structured output in agent output, spec chat, and activity using at least two installed runners
- [ ] 6.6 Document the structured output API fields, seven-kind payload contract, compatibility behavior, and payload limits
- [ ] 6.7 Record provider fixture versions and any intentionally omitted provider bookkeeping events
- [ ] 6.8 Confirm no Stop control, message-threading behavior, or context-percentage normalization was introduced
