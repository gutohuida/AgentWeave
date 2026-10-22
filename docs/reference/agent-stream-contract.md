---
description: How runner output becomes ordered stream events, and how context usage is measured per runner.
---

# Agent stream and context contracts

The Hub normalizes every runner's output as it parses it. Claude Code, Codex and GitHub Copilot
therefore expose the same stream-event contract and the same context-usage contract, even though
their native formats differ.

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
| Claude Code | Latest assistant-message usage; `latest_request_input` | `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` | Resolved model metadata, otherwise absent |
| Codex | App-server token usage; `provider_context` | The thread's reported context tokens | The model's reported context window |
| GitHub Copilot | ACP session usage; `provider_context` | The session's reported context tokens | Resolved model metadata, otherwise absent |

Codex `cached_input_tokens` is already a subset of input and is not added. Codex runs over its
app-server protocol by default. A runner flag `--no-app-server` opts back into `codex exec`.

Copilot usage is recorded in Copilot's own units, **AI credits** and premium requests. These are
never converted to money and never counted against the token budget.

## Compatibility

Every structured output keeps readable `content`. Existing `AgentOutput` rows with null structured
fields render through the UI's single legacy adapter.

Context readers accept the older aliases `tokens_used`, `tokens_limit`, `input_tokens`,
`context_limit`, `max_context_tokens`, and ratio-form `context_usage`. Writers emit only canonical
fields. Ambiguous zeroes and contradictory legacy dictionaries become unavailable or token-only
instead of being presented as trusted measurements.

The following bookkeeping is intentionally omitted when it adds nothing a person would want to see:
provider session initialization and lifecycle chatter, echoes of the user's message, empty start
markers paired with a later completed item, and unknown events with no safe, user-relevant
diagnostic.

## Related

Stopping a turn, accounting and checkpoints are built on these contracts. See
[Conversations](../guides/conversations.md) and [Traceability](../guides/traceability.md).
Context warnings are advisory: you decide whether to checkpoint.
