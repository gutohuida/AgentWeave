## Context

Five watchdog parser paths currently return different tuple shapes and flatten provider streams
into decorated strings. The runner loop posts each string as `AgentOutput.content`; the Hub model,
REST schema, SSE stream, and UI type carry no semantic fields. `SpecPage`, `AgentActivityTab`, and
`AgentOutputPanel` therefore implement different prefix-based interpretations of the same output.

Provider protocols already distinguish messages, readable reasoning, tools, results, lifecycle,
errors, and usage. The stream boundary must preserve those distinctions without coupling the Hub
to provider-specific schemas. It must also remain compatible with existing databases, older Hubs,
and text-only output. Agent-output retention is currently unbounded, so structured payload limits
are required before richer data is persisted.

This design covers Claude 2.1.x, Codex 0.145.x, OpenCode 1.18.x, documented GitHub Copilot stream
events, and Kimi 0.29.x. Kimi v1 parsing is compatibility-only. The next planned change will repair
and expose context usage across the same five adapters.

## Goals / Non-Goals

**Goals:**

- Define one typed parser boundary and seven provider-neutral event kinds.
- Preserve exact per-run ordering and correlate tool calls with results.
- Deliver safe structured data through storage, REST, chat history, and SSE.
- Render stream semantics consistently on all current Hub agent-output surfaces.
- Provide graceful degradation in both directions across CLI/Hub versions.
- Leave an explicit, separate usage slot for the next context-tracking change.

**Non-Goals:**

- Stopping or cancelling a running process.
- Normalizing token windows, context percentages, cost, or compaction behavior.
- Adding message threads or changing chat-session routing.
- Persisting complete provider wire events or hidden chain-of-thought.
- Expanding Kimi v1 protocol support.
- Replacing the existing trace/span model.

## Decisions

### 1. Normalize at runner adapters

Introduce a canonical internal result shaped conceptually as:

```text
ParsedRunnerLine
├── events: list[AgentStreamEvent]
├── usage: optional provider usage sample
├── session_change: optional session metadata
└── control: parser/runner flags
```

`AgentStreamEvent` contains `kind`, readable `content`, and a versioned payload. The runner assigns
`run_id` and `sequence` after normalization, immediately before delivery. This lets one provider
line yield multiple ordered events and lets usage exist without display output.

Normalization belongs in provider adapters because they understand provider wire formats. Doing it
in the Hub would require sending raw provider events, increase exposure of sensitive fields, and
make the server depend on every runner version. Preserving the current tuple variants was rejected
because it would force Change 6 to add yet another incompatible return shape.

### 2. Use a small closed taxonomy

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
`completed`, and `skipped`. Payload `version=1` permits additive evolution without proliferating
database columns.

A separate `result` kind was rejected: successful results are completion status and failed results
are run errors. A tool failure remains `tool_result` because changing it to `error` would destroy
tool correlation.

### 3. Generate run identity in the watchdog

Each process invocation gets a fresh opaque `run_id`; retries start a new run. Events receive
strictly increasing integer `sequence` values in the order they are posted. Provider call IDs are
retained as `call_id` but are not used as run IDs.

This is more reliable than timestamps for grouping live thinking and tools, and it avoids assuming
that provider session IDs identify a single invocation. Database record ID remains the final
tie-breaker for legacy rows and equal timestamps.

### 4. Store additive nullable fields

The next Hub migration adds nullable columns to `AgentOutput`:

- `kind`: bounded string
- `payload`: JSON
- `run_id`: bounded string
- `sequence`: integer

It also adds an index suitable for project/agent/run ordering. The existing `content`,
`session_id`, and timestamp remain authoritative compatibility fields. API create/response models,
SSE serialization, and chat-history projection carry the four optional fields.

Nullable columns allow a rolling upgrade with no backfill. New producers always supply meaningful
content, so an older Hub that ignores unknown fields still stores a usable line. New UI code treats
null-kind rows as legacy text. A separate event table was rejected because output already has the
correct ownership, session, timestamps, and SSE lifecycle.

### 5. Bound and redact before transport, validate again at ingress

Adapters construct only allowlisted fields rather than copying raw provider objects. Existing
recursive secret redaction is applied to both summaries and nested structured values before
transport. Serialized payloads are capped at 64 KiB; tool-result excerpts are capped at 8 KiB.
Truncation retains a summary and marks `truncated=true`. Opaque or encrypted reasoning is discarded.

The Hub independently validates kind membership and serialized size. This defense-in-depth matters
because HTTP endpoints can be called without the watchdog. Storing raw events and redacting only
at render time was rejected because secrets would already be at rest and payload growth would be
uncontrolled.

### 6. Map each runner explicitly and test with golden fixtures

- **Claude:** readable thinking and text blocks map directly; `tool_use.id` pairs with
  `tool_result.tool_use_id`; result messages produce terminal status or error; usage remains in the
  separate slot.
- **Codex:** support official JSONL lifecycle plus agent messages, reasoning, commands, file
  changes, MCP calls, web searches, plan updates, `turn.failed`, and error events.
- **OpenCode:** consume `--format json` events for messages, tools, step completion, lifecycle,
  diagnostics, and failures. Fixtures are captured from the supported 1.18.x shape because its raw
  event schema is less fully documented.
- **Copilot:** map documented assistant reasoning/message, tool execution, lifecycle, diagnostic,
  and error events. Fixtures are documentation-derived until the CLI is available in the test
  environment.
- **Kimi:** target the installed 0.29.x sequential assistant/tool stream and retain tool IDs.
  Existing v1 branches remain covered only to prevent regression.

Unknown valid events do not fail the stream. User-relevant unknowns become bounded diagnostics;
irrelevant bookkeeping can be omitted. Malformed lines retain a safe diagnostic or readable
fallback where possible.

### 7. Use one shared UI renderer

A shared stream renderer accepts normalized output records and is embedded by the agent output
panel, spec chat, and activity view. It provides:

- grouped live thinking, auto-collapsed on first text or terminal status, with elapsed duration;
- tool-use/result pairing by `run_id` and `call_id`, compact by default and expandable;
- prominent run errors and failed tool state;
- a diagnostics visibility control independent from errors and tool failures;
- a legacy adapter for null-kind records and existing prefixes.

Structured records never rely on prefix sniffing. Prefix compatibility remains at a single legacy
boundary so historical rows do not suddenly change visibility.

### 8. Retrieve the newest bounded window correctly

For a request without a cursor, the backend selects the newest N rows using descending stable keys,
then reverses them for chronological display. Incremental cursor requests remain ascending.
Ordering prefers timestamp, then available run sequence, then record ID. This fixes the current
ascending-limit behavior that returns the oldest N records.

### 9. Emit lifecycle without implying cancellation

The watchdog emits started, retrying, completed, and failure state when those transitions are
known. The UI does not expose a Stop control because the framework has no process registry or
cancellation endpoint. Lifecycle semantics are useful independently and can support cancellation
in a later change without falsely promising it now.

## Risks / Trade-offs

- **[Provider schemas drift]** → Keep normalization isolated per provider, tolerate unknown events,
  and use representative golden fixtures with explicit version notes.
- **[Payloads leak secrets]** → Build from allowlisted fields, recursively redact before transport,
  discard opaque reasoning, bound excerpts, and validate again in the Hub.
- **[Structured data increases storage and SSE traffic]** → Enforce hard payload limits, avoid raw
  events, and keep tool details collapsed in the UI.
- **[Rolling upgrades lose structure]** → Preserve readable content on every event and make all new
  fields optional; loss of structure degrades to current text behavior.
- **[Tool pairing is incomplete]** → Pair only with actual provider call IDs and render unmatched
  events independently instead of guessing.
- **[Thinking duration is approximate]** → Derive it from persisted timestamps within one run and
  omit a precise duration when boundaries are unavailable.
- **[Change 6 needs provider usage details]** → Preserve usage separately in the parser result now,
  but defer its normalized schema and persistence until that change.

## Migration Plan

1. Add canonical event types, payload safety helpers, and adapter fixture tests without changing
   transport behavior.
2. Migrate all five adapters and the runner loop to the shared parser result while retaining
   readable output.
3. Add optional transport parameters and the next Hub database migration; update schemas,
   endpoints, SSE, chat history, and backend tests.
4. Correct recent-output query ordering.
5. Add the shared UI types and renderer, migrate all three consumers, and retain legacy handling.
6. Run CLI tests, Hub tests, UI type-check/build, and migration upgrade tests.

Rollback is additive: older application code can continue using `content` while the nullable
columns remain. If the migration itself must be reversed, remove the new index and columns only
after confirming no deployed client depends on structured fields.

## Open Questions

- The exact current Copilot CLI JSON fixture must be confirmed in an environment with that CLI
  installed before implementation is considered complete; official event documentation defines
  the required semantic mapping in the meantime.
- OpenCode fixture capture may reveal additional bookkeeping variants; they should be classified
  as omitted or diagnostic without expanding the seven-kind taxonomy.
