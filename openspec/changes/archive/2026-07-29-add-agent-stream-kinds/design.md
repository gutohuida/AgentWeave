## Context

Five watchdog adapters currently flatten provider streams into strings and return incompatible
tuple shapes. Context tracking is split among generic, Codex, and Kimi writers with incompatible
schemas, while OpenCode and Copilot do not have reliable end-to-end reporting. The Hub accepts an
unvalidated context dictionary, and the UI assumes a different pair of field names from some
writers.

Provider validation against installed Claude Code 2.1.220, Codex CLI 0.145.0, OpenCode 1.18.5,
Kimi Code 0.29.1 source/Wire data, and current Copilot/OTel documentation established that no
single raw token field has the same semantics across all runners:

- Claude exposes additive request input, cache-read, and cache-creation fields.
- Codex stdout usage is cumulative; rollout `last_token_usage` is the current source.
- OpenCode step samples replace rather than accumulate, and their normalized total includes output
  and reasoning.
- Copilot's parent OTel span aggregates calls; the latest child `chat` span is per request, and its
  input total already includes cache breakdowns.
- Kimi `llm.request.maxTokens` is a completion cap, not a context limit; Kimi's own context service
  uses latest-step input/cache/output and model capability metadata.

The design therefore needs a common observation boundary without imposing false arithmetic
uniformity. Stream events and context snapshots share adapter and invocation infrastructure but
have different persistence and rendering semantics.

## Goals / Non-Goals

**Goals:**

- Define one typed runner observation boundary and seven provider-neutral stream event kinds.
- Define one canonical context sample that records measurement status and basis.
- Preserve exact per-run ordering and correlate tool calls with results.
- Collect accurate, non-cumulative context observations from stdout or session-bound auxiliary
  files without scanning an unscoped newest file.
- Deliver both contracts safely through local state, transport, Hub APIs/SSE, and UI.
- Render stream semantics and context availability consistently across current Hub surfaces.
- Preserve rolling compatibility with existing producers, Hubs, database rows, and UI clients.

**Non-Goals:**

- Stopping or cancelling a running process.
- Automatically compacting, resetting, or handing off sessions.
- Adding message threads or changing chat-session routing.
- Reporting cost, billing usage, or provider rate-limit quota.
- Persisting complete provider wire events, OTel content, or hidden chain-of-thought.
- Expanding Kimi v1 protocol support.
- Replacing the existing trace/span model or building generic telemetry ingestion.

## Decisions

### 1. Coordinate two producers at the invocation boundary

The watchdog invocation coordinator owns a stdout adapter and, when needed, an auxiliary usage
collector:

```text
stdout adapter ───────────────┐
                              ├─▶ RunnerObservation
auxiliary usage collector ────┘      ├── events[]
                                     ├── usage_samples[]
                                     ├── session_change?
                                     └── control?
```

An implementation may retain a `ParsedRunnerLine` type and add a `RunnerUsageCollector` protocol
instead of materializing this exact aggregate. The invariant is that both producers return the
same canonical `ContextUsageSample`, and raw provider dictionaries do not cross into writers,
transport, Hub, or UI.

Combining the capabilities here avoids reopening all adapters and the invocation lifecycle.
Keeping their result fields separate prevents context snapshots from becoming `AgentOutput` rows
or stream events.

### 2. Use a small closed stream taxonomy

The only event kinds are:

| Kind | Payload core | Meaning |
|---|---|---|
| `text` | `version`, `text` | User-facing assistant prose |
| `thinking` | `version`, `text` | Provider-exposed readable reasoning/status prose |
| `tool_use` | `version`, `call_id`, `tool`, `category`, `input`, `summary`, `truncated` | Tool invocation |
| `tool_result` | `version`, `call_id`, `tool`, `output`, `summary`, `is_error`, `truncated` | Tool completion |
| `status` | `version`, `phase`, `summary` | Run lifecycle or plan state |
| `diagnostic` | `version`, `stream`, `severity`, `summary` | Operational detail |
| `error` | `version`, `code`, `message`, optional `exit_code`, `retryable` | Run-level failure |

Allowed status phases initially include `queued`, `started`, `plan`, `compacting`, `retrying`,
`completed`, and `skipped`. Payload `version=1` permits additive evolution.

A separate `result` kind is unnecessary: successful results are completion status and failed
results are run errors. A failed tool remains `tool_result` to preserve correlation.

### 3. Define an honest context sample

The canonical sample is conceptually:

```text
ContextUsageSample
├── status: measured | estimated | unsupported | unavailable
├── context_tokens: optional non-negative integer
├── limit_tokens: optional positive integer
├── percent: optional number from 0 through 100
├── model: optional string
├── session_id: optional string
├── source: bounded provider/source identifier
├── basis: provider_context | latest_request_input |
│          provider_reported_ratio | cumulative_delta
├── observed_at: timestamp
└── breakdown: bounded optional token fields
```

`percent` is derived from `context_tokens / limit_tokens` when both are known, clamped only for
display safety. It is absent when either value is unknown. `provider_reported_ratio` may supply a
percentage directly when the provider does not expose both operands. `estimated` and `measured`
must remain distinguishable throughout the pipeline.

The latest valid sample replaces the prior sample for that session. Samples are never summed.
Visible/retained output is included when the provider's own context model includes it; separately
identified transient reasoning is excluded when possible.

### 4. Encode provider-specific accounting explicitly

| Runner | Canonical source | Context mapping | Limit mapping |
|---|---|---|---|
| Claude / Claude proxy | Latest assistant-message usage; tested final-result fallback | `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` | Resolved model metadata; absent if unknown |
| OpenCode | Latest `step_finish.part.tokens` | `total - reasoning`, equivalent to input + cache read + cache write + output | Current model `limit.input`, otherwise effective context fallback |
| Codex | Latest session-bound rollout `token_count.info` | `last_token_usage.total_tokens - reasoning_output_tokens` | `model_context_window` |
| Copilot | Latest top-level child OTel `chat` span | `gen_ai.usage.input_tokens` directly; cache fields are breakdowns | Resolved model metadata; absent if unknown |
| Kimi 0.29.x | Session status, or latest matching main-agent completed-step usage | `inputOther + inputCacheRead + inputCacheCreation + output` | `max_input_tokens ?? max_context_tokens` from model capability |

Codex `cached_input_tokens` is a subset of `input_tokens`; it is never added. Copilot follows the
OTel rule that cache-read and cache-creation values are included in `input_tokens`; they are never
added. OpenCode and Kimi cache classes are exclusive components and are added as shown.

Kimi `llm.request.maxTokens` must never be used as a context denominator because exact 0.29.1
source maps it to the maximum completion budget. `usage.record` is accumulated accounting rather
than the context-size model.

### 5. Bind auxiliary collectors to the active invocation

Collector setup and resolution belong to the invocation coordinator:

- Configure a unique bounded Copilot OTel JSONL path before spawn, leave content capture disabled,
  and select the latest relevant top-level child `chat` span.
- Resolve Codex rollout data by the emitted thread/session identity. A bounded timestamp lookup may
  be used only as a guarded fallback and must verify the session before accepting a sample.
- Resolve Kimi status or main-agent Wire data by the active Kimi session and agent. Never select an
  unscoped newest session directory.
- Use stdout-native samples for Claude and OpenCode, while resolving OpenCode's current model
  capability from its own catalog/configuration rather than a primary hard-coded table.
- Perform a final collector poll after stdout closes so a trailing file record is not lost.

Collectors tolerate partial writes, malformed unrelated records, and absent optional fields.
They expose unavailable/unsupported state instead of fabricating zero.

### 6. Separate run identity from session identity

Every process invocation receives a fresh opaque `run_id`; retries receive a new run. Stream
events receive strictly increasing `sequence` values after normalization.

Context replacement is keyed by agent and active provider session, not only by run. A new session
immediately replaces the previous snapshot with `unavailable` until its first valid sample. A
sample carrying an old session ID, an earlier run binding, or an observation time before the
active invocation boundary is rejected.

A watchdog restart reconstructs the active session binding before accepting auxiliary samples. It
does not carry an in-memory cumulative delta across restarts as if it were measured.

### 7. Normalize storage and transport once

The local context file, HTTP request, Hub validation/storage event, SSE projection,
`AgentSummary.context_usage`, and UI type use the canonical field names from
`ContextUsageSample`.

For rolling compatibility:

- readers may accept current aliases such as `tokens_used`, `tokens_limit`, `input_tokens`,
  `context_limit`, and ratio-form `context_usage`;
- writers emit only the canonical schema after migration;
- old untyped Hub event rows are normalized on read where unambiguous;
- unknown or contradictory legacy dictionaries become `unavailable`, not zero.

The Hub uses a typed Pydantic schema and validates status/basis enums, number ranges, bounded
strings, bounded breakdown keys, and the relationship between tokens, limit, and percentage.
Context remains a latest snapshot carried through the existing agent-event projection unless
implementation evidence requires a dedicated table.

### 8. Store additive nullable stream fields

The next Hub migration adds nullable `kind`, `payload`, `run_id`, and `sequence` columns to
`AgentOutput`, plus an index suitable for project/agent/run ordering. Existing `content`,
`session_id`, and timestamp remain compatibility fields. API create/response models, SSE, and chat
history carry the four optional fields.

New producers always supply meaningful readable content. Older Hubs may ignore structure while
preserving that fallback; new UIs treat null-kind records as legacy text.

### 9. Bound and redact before transport, validate at ingress

Adapters construct only allowlisted fields. Existing recursive secret redaction applies to
summaries and nested structured values before transport. Serialized stream payloads are capped at
64 KiB; tool-result excerpts are capped at 8 KiB. Opaque or encrypted reasoning is discarded.

Context breakdowns use a small allowlist of numeric fields and never contain messages or raw
provider objects. Copilot OTel content capture remains disabled. The Hub independently validates
stream and context bounds because endpoints can be called without the watchdog.

### 10. Map runners with golden fixtures

- **Claude:** map readable thinking, text, tools, lifecycle, errors, and independent per-request
  usage.
- **Codex:** map official item/turn events; collect exact context from the matching rollout rather
  than cumulative stdout totals.
- **OpenCode:** map JSON messages/tools/steps and take only the latest step usage sample.
- **Copilot:** map documented stream events and independently collect the latest child `chat` span.
  Documentation-derived fixtures are permitted until a current CLI fixture is available.
- **Kimi:** target 0.29.x sequential messages and exact 0.29.1 status/Wire semantics. Existing v1
  branches remain regression-only.

Unknown valid stream events do not terminate processing. User-relevant unknowns become bounded
diagnostics; irrelevant bookkeeping may be omitted.

### 11. Use one shared stream renderer

A shared renderer is embedded by agent output, spec chat, and activity. It groups live thinking,
pairs tools by `run_id` and `call_id`, keeps errors prominent, supports diagnostic visibility, and
uses a single legacy-prefix adapter for historical rows.

### 12. Render context state explicitly

Agent cards, detail, overview, and status surfaces consume the same normalized context object:

- measured percentage shows normal warning/critical treatment;
- estimated percentage is labeled as estimated;
- token-only samples show the count with an unknown limit and no percentage;
- unavailable and unsupported states show distinct neutral text;
- a new session never displays the previous session's bar while awaiting its first sample.

Estimated samples are displayable but do not trigger automatic warning/critical policy in this
change. Automatic reset/handoff policy remains outside scope.

### 13. Retrieve the newest output window correctly

Without a cursor, the backend selects the newest N output rows using descending stable keys, then
reverses them for chronological display. Cursor requests remain ascending. Ordering prefers
timestamp, then run sequence, then record ID.

## Risks / Trade-offs

- **Provider schemas drift:** isolate normalization by provider, tolerate unknown events, and
  version golden fixtures.
- **Auxiliary file races:** use invocation-scoped paths/session IDs, tolerate partial records, and
  perform a final bounded poll.
- **A model limit is unavailable:** retain a token-only sample with absent percentage instead of
  guessing.
- **Structured data leaks secrets:** allowlist, recursively redact, disable telemetry content, and
  enforce payload bounds at both producer and Hub.
- **Rolling upgrades lose structure:** keep readable stream content and accept legacy context
  aliases during migration.
- **Tool pairing is incomplete:** render unmatched events independently instead of inventing IDs.
- **Provider context bases differ:** expose `basis` and `source` rather than presenting estimates as
  identical measurements.

## Migration Plan

1. Add canonical event/context types, validators, payload-safety helpers, and fixtures without
   changing delivery.
2. Migrate all five stdout adapters and add session-bound auxiliary collectors.
3. Replace the three context writers with one canonical snapshot writer and normalize transport.
4. Add optional output persistence fields and typed context ingress/projection in the Hub.
5. Correct recent-output ordering and migrate chat/SSE projections.
6. Add the shared stream renderer and normalized context UI states.
7. Run provider fixtures, CLI/Hub/UI suites, migration tests, and installed-runner smoke tests.

Rollback is additive. Older code can continue using readable output content and legacy context
aliases while nullable structured columns remain. Auxiliary collectors can be disabled per runner
without corrupting stored output.

## Open Questions

- A current Copilot CLI fixture is still required before Copilot implementation is considered
  fully verified; official GitHub and OTel field semantics define the contract in the meantime.
- If the Kimi REST session-status service is unavailable to the watchdog, implementation must
  choose the least invasive session-bound way to obtain model capability metadata. Missing
  capability data yields a token-only sample; it never permits use of completion `maxTokens`.
- Claude's final-result fallback must be accepted only for stream shapes covered by fixtures; the
  assistant-message usage remains canonical.
