## 1. Canonical contracts and safety

- [x] 1.1 Add typed `AgentStreamEvent`, `ContextUsageSample`, `ParsedRunnerLine`, session-change,
  and parser-control models
- [x] 1.2 Define and validate the seven version-1 event kinds and their kind-specific payloads
- [x] 1.3 Define context status and basis enums plus validation for token, limit, percent, source,
  session, model, time, and bounded breakdown fields
- [x] 1.4 Derive context percentage from known operands, omit it when an operand is unknown, and
  preserve directly reported provider ratios only under the provider-ratio basis
- [x] 1.5 Add constructors that always produce meaningful readable stream `content` fallbacks
- [x] 1.6 Add recursive stream-payload redaction using the existing secret-redaction behavior
- [x] 1.7 Add deterministic 64 KiB stream-payload and 8 KiB tool-result excerpt limits with
  truncation metadata
- [x] 1.8 Allowlist numeric context breakdown fields and prevent raw provider objects or message
  content from entering context samples
- [x] 1.9 Add unit tests for both contracts, percentage consistency, unknown limits, nested
  redaction, truncation, cache semantics, and opaque-reasoning exclusion

## 2. Stdout adapters and fixtures

- [x] 2.1 Refactor the Claude parser to return the canonical result and map text, readable
  thinking, tools, lifecycle, errors, and independent assistant-message usage
- [x] 2.2 Implement Claude latest-request arithmetic as input + cache read + cache creation and
  constrain final-result fallback to fixture-proven shapes
- [x] 2.3 Add Claude 2.1.x fixtures covering multiple blocks, tool correlation, completion,
  failure, usage-only data, resumed usage, cached input, and unknown events
- [x] 2.4 Refactor the Codex stdout parser to map agent messages, reasoning, commands, file changes,
  MCP calls, web searches, plans, lifecycle, errors, and cumulative usage metadata
- [x] 2.5 Add Codex 0.145.x stdout fixtures covering official item/turn events, resumed cumulative
  totals, malformed lines, and unknown events
- [x] 2.6 Refactor the OpenCode parser to map supported message, tool, step, lifecycle, diagnostic,
  failure, and usage data
- [x] 2.7 Select only the latest usable OpenCode step sample and compute context as total minus
  separately reported reasoning
- [x] 2.8 Add OpenCode 1.18.x fixtures covering cached resumed steps, multiple steps, reasoning,
  model identity, malformed events, and unknown variants
- [x] 2.9 Refactor the Copilot stream parser to map documented reasoning, message, tool, lifecycle,
  diagnostic, and error events while keeping OTel usage independent
- [x] 2.10 Curate versioned Copilot stream fixtures from official examples and mark them
  documentation-derived until a current installed CLI capture is available — superseded by a
  live Copilot CLI 1.0.75 capture (2026-07-29); fixtures are verified, not documentation-derived
- [x] 2.11 Refactor the Kimi parser around v0.29.x sequential messages, tool IDs, results,
  lifecycle, and errors while preserving existing v1 regression behavior
- [x] 2.12 Add Kimi 0.29.x golden fixtures plus regression coverage for retained v1 compatibility
- [x] 2.13 Add cross-adapter conformance tests proving every adapter returns only canonical event
  kinds and keeps context samples separate

## 3. Auxiliary context collectors

- [x] 3.1 Define a `RunnerUsageCollector` interface with invocation setup, session binding,
  incremental observation, final bounded poll, and cleanup
- [x] 3.2 Implement Codex rollout resolution by active thread/session ID and parse the latest
  matching `token_count.info`
- [x] 3.3 Compute Codex context as last total minus reasoning output, use
  `model_context_window`, and retain cached input only as a breakdown
- [x] 3.4 Implement a guarded Codex cumulative-delta fallback that is always marked estimated and
  never used when exact rollout data is available
- [x] 3.5 Add Codex collector tests for fresh and resumed turns, multiple model calls, partial
  JSONL, missing rollouts, stale sessions, and exact-versus-estimated precedence
- [x] 3.6 Configure a unique bounded Copilot OTel JSONL exporter before each invocation with
  content capture disabled
- [x] 3.7 Select the latest relevant top-level child Copilot `chat` span, excluding aggregate
  `invoke_agent` and subagent calls
- [x] 3.8 Use Copilot `gen_ai.usage.input_tokens` directly and retain cache-read/cache-creation
  fields only as breakdowns
- [x] 3.9 Add Copilot OTel fixtures and tests for multiple chat spans, aggregate parents,
  subagents, cache fields, malformed/partial lines, absent limits, and content exclusion —
  live-verified against Copilot CLI 1.0.75 (plain reply, tool-call turn, task-tool subagent
  turn); cache_creation.input_tokens handling stays synthetic, never observed live
- [x] 3.10 ~~Implement Kimi 0.29.x session-status collection when the status service is
  available~~ — investigated live against Kimi Code CLI 0.29.1 and intentionally not
  implemented: `kimi web`'s `GET /api/v1/sessions/:id/status` only reflects accurate usage for
  sessions actively driven through that same running server process. A headless `kimi -p`
  invocation (how AgentWeave always runs Kimi) never registers with it — confirmed with a real
  session that had used 28,915 tokens reporting `context_tokens: 182`, stable across repeated
  queries and even with a `kimi web` server already running concurrently during the `-p` call.
  No resume/attach/reload action exists (`"unsupported action"` for all tried), and the endpoint
  is undocumented. Decision confirmed with the user; the Wire fallback (3.11) is the only source
  confirmed accurate for a headless invocation.
- [x] 3.11 Implement the session-bound Kimi fallback from latest main-agent completed-step usage
  and active model capability metadata
- [x] 3.12 Compute Kimi context from inputOther + cache read + cache creation + output and use
  `max_input_tokens ?? max_context_tokens`
- [x] 3.13 Explicitly reject `llm.request.maxTokens` as a context denominator and accumulated
  `usage.record` as the context-size source
- [x] 3.14 Add Kimi tests for status, Wire fallback, missing capabilities, completion maxTokens,
  accumulated usage records, partial files, and stale session directories — live-verified against
  Kimi Code CLI 0.29.1 (single-turn and 3-turn wire.jsonl captures, provider catalog JSON); status
  path has no tests since it was not implemented (see 3.10)
- [x] 3.15 Resolve OpenCode model limits from the active model catalog/configuration, preferring
  its declared effective input limit and using the context fallback only when needed
- [x] 3.16 Add OpenCode limit tests for declared input limits, fallback limits, model switches,
  and unknown model metadata

## 4. Invocation lifecycle and canonical context delivery

- [x] 4.1 Generate a fresh opaque `run_id` for every runner process invocation, including retries
- [x] 4.2 Assign strictly increasing stream sequence values after adapter normalization and
  before output delivery
- [x] 4.3 Emit canonical started, retrying, completed, skipped, and run-error lifecycle events at
  known runner boundaries
- [x] 4.4 Update the runner loop to deliver zero or more normalized events and zero or more
  independent context samples without fabricating either output
- [x] 4.5 Bind collectors to the active agent, run, and provider session and reject mismatched or
  pre-invocation observations
- [x] 4.6 Reset a new session's context snapshot to `unavailable` before its first measurement
- [x] 4.7 Reconstruct active session binding after watchdog restart without carrying stale
  in-memory cumulative deltas
- [x] 4.8 Replace the generic, Codex, and Kimi context writers with one atomic canonical snapshot
  writer
- [x] 4.9 Add legacy context readers for `tokens_used`, `tokens_limit`, `input_tokens`,
  `context_limit`, and ratio-form `context_usage`
- [x] 4.10 Normalize contradictory legacy values to unavailable or token-only state instead of
  trusted zero
- [x] 4.11 Extend transport interfaces to post canonical context samples and optional structured
  stream fields while preserving old call sites
- [x] 4.12 Add local and HTTP transport tests for structured events, canonical context,
  text-only fallback, legacy aliases, redacted data, and older-Hub degradation
- [x] 4.13 Add watchdog tests for new-session reset, late old-session writes, retries, process
  failure, restart recovery, final collector polling, and simultaneous output/usage records

## 5. Hub stream persistence and APIs

- [x] 5.1 Add the next Alembic migration for nullable AgentOutput kind, JSON payload, run ID,
  sequence, and the run-ordering index
- [x] 5.2 Update SQLAlchemy models and Pydantic creation/response schemas with bounded optional
  structured stream fields
- [x] 5.3 Validate allowed kinds and serialized payload size at Hub ingress and add rejection
  tests
- [x] 5.4 Persist and serialize structured fields through agent-output REST endpoints and SSE
- [x] 5.5 Preserve structured fields when AgentOutput records are projected into per-agent chat
  history
- [x] 5.6 Correct the default output query to select the newest N records and return them in
  stable chronological order
- [x] 5.7 Add Hub tests for migration upgrade, structured round trips, legacy rows, chat
  projection, SSE data, rejection behavior, and newest-window ordering

## 6. Hub context validation and projection

- [x] 6.1 Replace the unvalidated context dictionary ingress with a typed canonical Pydantic
  request schema
- [x] 6.2 Validate status/basis enums, numeric ranges, percentage consistency, bounded strings,
  observation time, and allowlisted breakdown fields
- [x] 6.3 Normalize accepted legacy context payloads at the Hub boundary during rolling upgrades
- [x] 6.4 Store the canonical latest snapshot through the existing agent-event path unless
  implementation evidence requires a dedicated migration
- [x] 6.5 Project the canonical context object without field drift through agent summaries and
  real-time updates
- [x] 6.6 Ensure session identity and observation ordering prevent an older snapshot from
  replacing a newer active-session snapshot
- [x] 6.7 Add Hub tests for measured, estimated, token-only, unavailable, unsupported, invalid,
  legacy, stale-session, and out-of-order samples

## 7. Shared stream UI

- [x] 7.1 Extend UI API types and normalization helpers for optional stream kind, payload, run ID,
  and sequence
- [x] 7.2 Build one shared stream renderer with a plain-text legacy adapter for null-kind records
- [x] 7.3 Implement per-run thinking grouping, live state, automatic collapse, manual expansion,
  and timestamp-based duration labels
- [x] 7.4 Implement tool-use/result pairing by run ID and call ID with expandable safe inputs,
  outputs, completion state, and failure state
- [x] 7.5 Implement distinct status, diagnostic, and error treatments plus diagnostic visibility
  that never hides errors
- [x] 7.6 Replace raw/prefix-based rendering in `AgentOutputPanel` with the shared renderer
- [x] 7.7 Replace stream prefix filtering and rendering in `SpecPage` with the shared renderer
- [x] 7.8 Replace activity prefix classification in `AgentActivityTab` with the shared renderer's
  semantic projection
- [x] 7.9 Add component or deterministic renderer tests for structured events, legacy prefixes,
  incomplete tool pairs, thinking transitions, errors, and diagnostic filtering

## 8. Context UI

- [x] 8.1 Replace the current UI context type with the canonical status, operands, percent, model,
  session, source, basis, time, and breakdown fields
- [x] 8.2 Add one context normalization/presentation helper shared by AgentCard,
  AgentDetailPanel, AgentsPage, OverviewPage, and StatusBar
- [x] 8.3 Render measured context percentages and warning/critical visual states consistently
- [x] 8.4 Label estimated samples and prevent them from triggering automatic warning/critical
  policy
- [x] 8.5 Render token-only samples without inventing a percentage
- [x] 8.6 Render unavailable and unsupported states distinctly and neutrally
- [x] 8.7 Ensure a new session cannot display the previous session's context bar while waiting for
  its first sample
- [x] 8.8 Add UI tests for every context status, unknown limits, legacy normalization,
  thresholds, estimates, and new-session replacement

## 9. Verification and documentation

- [ ] 9.1 Run focused watchdog, collector, safety, legacy-normalization, and transport tests for
  all five runners
- [ ] 9.2 Run the full CLI pytest suite plus ruff, black check, and mypy for affected Python code
- [ ] 9.3 Run Hub backend tests including migration upgrade, structured output, typed context,
  ordering, and SSE coverage
- [ ] 9.4 Run Hub UI type-check/build and all available renderer/context tests
- [ ] 9.5 Smoke-test metadata-only fresh/resumed flows with installed Claude, Codex, OpenCode, and
  Kimi; document provider quota or availability failures without inspecting prompt content
- [ ] 9.6 Record Copilot as documentation-derived until a current CLI fixture can be captured,
  then run the same metadata-only smoke test when available
- [ ] 9.7 Manually verify live structured output in agent output, spec chat, and activity with at
  least two installed runners
- [ ] 9.8 Manually verify measured, token-only, unavailable, and new-session context states through
  the Hub
- [ ] 9.9 Document the seven-kind output contract, context sample schema, provider formulas,
  auxiliary data sources, compatibility behavior, and payload limits
- [ ] 9.10 Record fixture provider/CLI versions and intentionally omitted bookkeeping events
- [ ] 9.11 Confirm context samples never become AgentOutput rows and raw provider/OTel content is
  never persisted
- [ ] 9.12 Confirm the change introduces no process cancellation, message threading, automatic
  reset/handoff policy, cost reporting, or Kimi v1 expansion
