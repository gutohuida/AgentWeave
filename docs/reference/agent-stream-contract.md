# Agent stream and context contracts

AgentWeave normalizes runner output before it reaches a transport or the Hub. Claude, Codex,
OpenCode, GitHub Copilot, and Kimi therefore expose the same stream-event contract and the same
context-usage contract even though their native formats differ.

Stream events and context usage are deliberately separate:

- Stream events are ordered, append-only output records.
- Context usage is a replaceable latest-session snapshot.
- A context sample is never stored as `AgentOutput` or assigned a stream-event kind.

## Stream events

Every structured output event contains readable `content` for compatibility and may include:

| Field | Meaning |
|---|---|
| `kind` | One of the seven closed kinds below |
| `payload` | A redacted, bounded object with `version: 1` |
| `run_id` | Opaque ID for one process invocation; retries receive a new ID |
| `sequence` | Strictly increasing position within the run |

The seven kinds are:

| Kind | Meaning | Important payload fields |
|---|---|---|
| `text` | User-facing assistant prose | `text` |
| `thinking` | Provider-exposed readable reasoning or status prose | `text` |
| `tool_use` | Tool invocation | `call_id`, `tool`, `category`, `input`, `summary` |
| `tool_result` | Tool completion | `call_id`, `tool`, `output`, `summary`, `is_error` |
| `status` | Run lifecycle or plan state | `phase`, `summary` |
| `diagnostic` | Operational detail | `stream`, `severity`, `summary` |
| `error` | Run-level failure | `code`, `message`, `exit_code`, `retryable` |

Supported status phases are `queued`, `started`, `plan`, `compacting`, `retrying`, `completed`,
and `skipped`.

`tool_use` and `tool_result` are paired only when both `run_id` and provider-supplied `call_id`
match. Events without a trustworthy call ID remain independently renderable.

### Safety and size limits

Agent adapters use allowlisted constructors before transport:

- nested secrets are redacted from readable content and payloads;
- opaque or encrypted reasoning is not accepted as `thinking`;
- serialized payloads are limited to 64 KiB;
- tool input/output and diagnostic/error text are limited to 8 KiB;
- Hub output `content` is validated at 10,000 characters;
- the Hub independently validates kinds, payload version, payload size, run IDs, and sequences.

Unknown provider events do not stop the stream. User-relevant unknown events may become bounded
diagnostics; irrelevant bookkeeping is omitted.

## Context usage

The canonical context snapshot is:

```text
status: measured | estimated | unsupported | unavailable
source: provider/source identifier
basis: provider_context | latest_request_input |
       provider_reported_ratio | cumulative_delta
context_tokens: optional non-negative integer
limit_tokens: optional positive integer
percent: optional number from 0 through 100
model: optional model identifier
session_id: optional provider session identifier
observed_at: Unix timestamp
breakdown: optional allowlisted token counts
```

Allowed breakdown keys are `input_tokens`, `output_tokens`, `cache_read_tokens`,
`cache_creation_tokens`, `reasoning_tokens`, and `cached_input_tokens`.

When both operands are known, percentage is derived from
`context_tokens / limit_tokens` and rounded to two decimal places. A provider-reported ratio may
supply percentage directly. Missing limits produce token-only samples; AgentWeave never guesses a
denominator or fabricates zero.

The latest valid observation replaces the previous observation for the active provider session.
A new session first publishes `unavailable`, preventing the previous session's bar from remaining
visible. Old-session, stale-run, and pre-invocation observations are rejected.

Only measured percentages trigger the automatic visual warning policy:

- warning at 70%;
- critical at 90%.

Estimated percentages remain visible and explicitly labeled, but do not trigger that policy.
`unavailable` and `unsupported` are distinct neutral states.

## Provider accounting

| Runner | Source and basis | Context calculation | Limit |
|---|---|---|---|
| Claude / Claude proxy | Latest assistant-message usage; `latest_request_input` | `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` | Resolved model metadata, otherwise absent |
| Codex | Session-bound rollout `token_count.info`; `provider_context` | `last_token_usage.total_tokens - reasoning_output_tokens` | `model_context_window` |
| OpenCode | Latest usable `step_finish.part.tokens`; `provider_context` | `total - reasoning` (equivalent to input + cache read + cache write + output) | Active model `limit.input`, then effective context fallback |
| GitHub Copilot | Latest relevant top-level child OTel `chat` span; `latest_request_input` | `gen_ai.usage.input_tokens` directly | Resolved model metadata, otherwise absent |
| Kimi 0.29.x | Session-bound latest main-agent completed-step Wire usage; `provider_context` | `inputOther + inputCacheRead + inputCacheCreation + output` | `max_input_tokens`, then `max_context_tokens` |

Codex `cached_input_tokens` is already a subset of input and is not added. Copilot cache-read and
cache-creation fields are also breakdowns already included in `input_tokens`. OpenCode and Kimi
cache classes are exclusive components and are included in the calculations shown above.

Codex stdout cumulative usage is only a guarded `estimated`/`cumulative_delta` fallback. Copilot
stdout has no usage data, so AgentWeave creates a unique invocation-scoped OTel JSONL export with
message-content capture explicitly disabled. Kimi's `llm.request.maxTokens` is a completion budget,
not a context limit, and `usage.record` is accumulated accounting rather than context size.

## Compatibility

Rolling upgrades retain readable `content` on every structured output. If an older Hub rejects
the optional structured fields, the HTTP transport retries with the legacy text-only body.
Existing `AgentOutput` rows with null structured fields use the UI's single legacy-prefix adapter.

Context readers accept the older aliases `tokens_used`, `tokens_limit`, `input_tokens`,
`context_limit`, `max_context_tokens`, and ratio-form `context_usage`. Writers emit only canonical
fields. Ambiguous zeroes and contradictory legacy dictionaries become unavailable or token-only
instead of being presented as trusted measurements.

## Fixture and smoke-test versions

The adapter fixtures target:

| Runner | Evidence |
|---|---|
| Claude Code | 2.1.x fixtures; fresh/resume smoke-tested with 2.1.220 |
| Codex CLI | Live 0.145.0 stdout and rollout shapes |
| OpenCode | Live 1.18.5 stdout and model-catalog shapes |
| GitHub Copilot CLI | Live 1.0.75 stdout and OTel captures |
| Kimi Code | Live 0.29.1 stdout, Wire, and provider-catalog captures |

The July 29, 2026 metadata-only smoke run confirmed fresh and resumed session continuity for all
five installed CLIs. Copilot OTel exports contained usage attributes and no prompt, response,
message, or content fields.

The following bookkeeping is intentionally omitted when it does not add user-visible meaning:

- provider session initialization and ordinary session lifecycle chatter;
- user-message echoes;
- empty start markers that are paired with a later completed item;
- Copilot MCP/skills/tools setup notifications and usage checkpoints;
- Kimi metadata wrappers and unknown roles;
- unknown events that contain no safe, user-relevant diagnostic.

Retained Kimi v1 parsing is regression compatibility only. This contract does not expand Kimi v1
support.

## Non-goals

These contracts do not add process cancellation, message threading, cost reporting, automatic
context reset/handoff decisions, or broader Kimi v1 protocol support. Context warnings remain
advisory; the user or an existing workflow chooses whether to compact or start a new session.
