# Exploration — Should context tracking be folded into agent stream kinds?

**Date:** 2026-07-29
**Status:** Complete; proposal work has not started
**Changes considered:** `add-agent-stream-kinds` (Change 4) and
`fix-context-tracking-all-runners` (Change 6)

## Question

Should Change 6 remain a separate adjacent change, or should its context-usage contract and
all-runner implementation be folded into Change 4 before implementation begins?

## Decision

**Fold Change 6 into Change 4, but keep two capability contracts and two implementation phases
inside the combined change.**

The common unit is not "one parser tuple." It is a provider-neutral observation boundary owned by
the runner invocation. That boundary must accept both stdout observations and auxiliary file
observations, emit normalized stream events and normalized context samples independently, and
feed their different downstream paths.

Keeping the capabilities distinct prevents context usage from being stored as an `AgentOutput` or
rendered as a stream event. Keeping them in one change prevents the five adapters, invocation
lifecycle, fixtures, and compatibility behavior from being designed and migrated twice.

The combined proposal should retain `agent-stream-events` and add a separate
`agent-context-usage` capability. It should not absorb session lifecycle, automatic reset,
cancellation, message threading, cost reporting, or general telemetry.

## Evidence checked

### Live repository

- Change 4 is proposed and strictly valid but has 0/47 tasks implemented.
- Its current `ParsedRunnerLine` sketch includes an optional usage slot but deliberately leaves
  the usage schema and persistence undefined.
- The watchdog still has five runner-specific display parsers, three incompatible context writers,
  and runner-specific post-loop branches.
- `AgentOutput` and context usage have deliberately different downstream ownership:
  - stream events are output records delivered through `post_agent_output`;
  - context usage is a latest-session snapshot written locally, posted through
    `post_context_usage`, stored as a Hub event, and projected into `AgentSummary`.
- The Hub context endpoint accepts an unvalidated dictionary. The UI only declares
  `tokens_used`/`tokens_limit`, while the generic and Kimi writers emit
  `input_tokens`/`context_limit`.

### Installed runner versions and live probes

- Claude Code 2.1.220
- Codex CLI 0.145.0
- OpenCode 1.18.5
- Kimi Code 0.29.1
- GitHub Copilot CLI is not installed

Fresh minimal turns, followed by a resume of the same session, were executed for Claude, Codex,
and OpenCode. Only event types, identifiers, and token metadata were inspected:

- Claude's resumed turn reported the same request input/cache fields on the assistant record and
  final result. The final result's output count was larger, so it is not a byte-for-byte substitute
  for the per-request assistant usage record.
- Codex's resumed `turn.completed.usage` was cumulative across both turns. The matching rollout's
  `last_token_usage` described only the latest turn, while `total_token_usage` exactly matched the
  cumulative stdout value.
- OpenCode's second `step_finish` replaced the first context observation: most prior input moved
  into `cache.read`, and `tokens.total` equaled input + cache read + cache write + output +
  reasoning.
- Kimi was invoked, but the provider returned HTTP 403 because the account's billing-cycle quota
  was exhausted. Its installed 0.29.1 behavior was therefore validated from existing local Wire
  records and the exact `@moonshot-ai/kimi-code@0.29.1` source instead of a fresh successful turn.
- Copilot remains documentation-only because it is not installed.

The decisive probe values were:

| Runner | First turn | Resumed turn | What it proves |
|---|---:|---:|---|
| Claude | — | input 2, cache read 30,172, cache creation 17 | The three input classes are additive on a request |
| Codex stdout | input 15,594, output 5 | input 31,204, output 11 | `turn.completed.usage` is cumulative |
| Codex rollout | last total 15,599 | last total 15,616; aggregate total 31,215 | `last_token_usage` is the non-cumulative context source |
| OpenCode | total 12,234 | total 12,267; input 32, cache read 12,217 | Latest step replaces prior context; summing steps double-counts |

### Local, metadata-only checks

- Recent Claude session records contain usage nested on individual assistant messages. This gives
  a per-request source that is more appropriate than blindly trusting a final run aggregate.
- Recent Codex rollout files contain `last_token_usage`, `model_context_window`,
  `total_token_usage`, cached-input fields, and reasoning/output fields.
- Recent Kimi 0.29.x `agents/main/wire.jsonl` files contain `usage.record` records with
  `usageScope="turn"`, `inputOther`, `inputCacheRead`, and `inputCacheCreation`. They also contain
  `llm.request.maxTokens`, but exact source inspection proves that field is the maximum completion
  budget, not the model context limit.
- Only field names and event kinds were inspected; prompt and response content was not read into
  the exploration.

### Current primary documentation

- Anthropic documents cached prompt accounting as
  `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`.
- OpenTelemetry specifies that `gen_ai.usage.input_tokens` should already include cache-read and
  cache-creation input. Those cache attributes are breakdowns, not additional terms.
- GitHub documents Copilot OTel `chat` spans as one span per LLM request with input, cache-read,
  cache-creation, model, conversation, and turn identifiers. The parent `invoke_agent` span is an
  aggregate across all LLM calls and is therefore the wrong source for current context.
- GitHub documents `COPILOT_OTEL_FILE_EXPORTER_PATH` as an opt-in JSONL file exporter that can be
  enabled before process spawn without enabling content capture.
- Kimi documents per-session `agents/*/wire.jsonl` files as the persisted Wire event stream.
- Current Codex public evidence confirms that `turn.completed.usage` does not expose the CLI's
  current context-window value, while rollout `token_count` records contain
  `last_token_usage` and `model_context_window`.
- The exact Kimi 0.29.1 source computes measured context as
  `inputCacheRead + inputCacheCreation + inputOther + output`. Its session status divides that
  value by `max_input_tokens ?? max_context_tokens`; both limits come from model capability
  metadata.

References:

- https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference
- https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/
- https://moonshotai.github.io/kimi-code/en/guides/sessions.html
- https://github.com/openai/codex/issues/21295
- https://github.com/openai/codex/issues/19022
- https://github.com/openai/codex/issues/2825
- https://github.com/MoonshotAI/kimi-code/tree/%40moonshot-ai/kimi-code%400.29.1

## Corrections to the 2026-07-28 exploration

### OpenCode samples must not be accumulated across steps

The prior exploration said to sum OpenCode input and cache tokens across steps. That would
double-count context already represented by a later step's cache read. The correct rule is to
retain the latest usable `step_finish` sample:

```text
context_tokens = tokens.total - tokens.reasoning
               = input + cache.read + cache.write + output
```

This matches OpenCode 1.18.5's normalized token fields and includes the just-produced visible
output in the context while excluding separately identified reasoning. The runner's own model
catalog supplies `limit.input` and `limit.context`; a hard-coded AgentWeave model table should not
be the primary source.

### Codex cumulative delta is only a fallback, not the canonical source

Subtracting consecutive `turn.completed.usage.input_tokens` totals fixes the obvious monotonic
growth bug for simple turns, but a turn can contain multiple model calls. Its delta can still be
larger than the final request context and does not include a runner-reported context limit.

The canonical source for supported non-ephemeral Codex sessions is the latest rollout
`token_count.info.last_token_usage` together with `model_context_window`. Context occupancy follows
the Codex CLI's own calculation:

```text
context_tokens = last_token_usage.total_tokens
                 - last_token_usage.reasoning_output_tokens
```

`cached_input_tokens` is already a subset of `input_tokens` and must not be added. A cumulative
delta may be reported as an explicitly estimated fallback only when the rollout sample cannot be
resolved. It must not be presented as exact.

### Copilot must use child `chat` spans

The parent `invoke_agent` OTel span aggregates all calls in an agent invocation. The collector must
select the latest relevant `chat` span for the top-level conversation, not sum spans and not use
the parent aggregate. Per the OTel semantic convention followed by those fields,
`gen_ai.usage.input_tokens` should already include cached input; cache-read and cache-creation
attributes are breakdowns and must not be added. Content capture remains disabled.

### Kimi `maxTokens` is not a context limit

The earlier mapping paired `usage.record` with `llm.request.maxTokens`. Exact Kimi 0.29.1 source
shows two errors in that mapping:

- `llm.request.maxTokens` is `provider.maxCompletionTokens`.
- `usage.record` feeds accumulated billing/accounting state; it is not the context-size model.

Kimi's context-size service instead replaces its measurement from the latest completed model step
and computes `inputCacheRead + inputCacheCreation + inputOther + output`. Its session-status path
returns `context_tokens`, `max_context_tokens`, and `context_usage`, using the effective limit
`modelCapabilities.max_input_tokens ?? modelCapabilities.max_context_tokens`. A collector should
prefer that status contract when available, or reproduce it from the matching latest step and
capability metadata. It must never interpret `llm.request.maxTokens` as the denominator.

## Normalized semantic contract

Context usage means:

> The provider's latest non-cumulative measurement of tokens occupying the active top-level
> session's effective context budget, divided by the provider-reported effective limit.

When a provider exposes only request input rather than post-response retained context, the sample
may use the latest request's total input, but it must declare that measurement basis. It does not
mean lifetime billing tokens, all model calls in an invocation, or remaining rate-limit quota.

A canonical sample should carry at least:

```text
ContextUsageSample
├── status: measured | estimated | unsupported | unavailable
├── context_tokens: optional integer
├── limit_tokens: optional integer
├── percent: optional number derived from the two fields
├── model: optional string
├── session_id: optional string
├── source: provider/source identifier
├── basis: provider_context | latest_request_input | provider_reported_ratio | cumulative_delta
├── observed_at: timestamp
└── breakdown: bounded optional input/cache fields
```

Rules:

- `percent` is absent, not zero, when tokens or limit are unknown.
- Runner-reported limits win over model tables.
- The latest valid sample replaces the previous sample for a session; samples are not summed.
- Cache fields are additive only when the provider explicitly defines its base input field as
  excluding them. Provider-normalized totals such as Codex `input_tokens`, Copilot OTel
  `input_tokens`, and OpenCode `tokens.total` must not have cache added again.
- Visible/retained output is included when the provider's own context measure includes it;
  separately identified transient reasoning is excluded when possible.
- New-session detection resets to `unavailable` until the first new measured sample.
- Session IDs are used to reject stale samples from an old run or file.
- Estimated samples are visibly distinguishable and never silently promoted to measured.
- Manual runners and genuinely unavailable sources use `unsupported` or `unavailable`.

## Provider mapping

| Runner | Canonical source | Mapping |
|---|---|---|
| Claude / Claude proxy | Latest assistant-message usage in the stream; final result only as a tested fallback | Latest-request basis: `input + cache_read + cache_creation`; latest request replaces prior |
| OpenCode | Latest `step_finish.part.tokens` plus current model metadata | Provider-context basis: `total - reasoning`; do not accumulate steps; prefer model `limit.input`, then `limit.context` |
| Codex | Latest matching rollout `token_count.info` record | Provider-context basis: `last.total_tokens - last.reasoning_output_tokens`; `model_context_window` is the limit; cached input is a breakdown only |
| Copilot | Latest top-level OTel child `chat` span written to a per-invocation JSONL file | Latest-request basis: use `gen_ai.usage.input_tokens` directly; cache fields are breakdowns; ignore aggregate `invoke_agent` spans |
| Kimi 0.29.x | Session status, or latest matching main-agent completed-step usage plus model capability | Provider-context basis: `inputOther + inputCacheRead + inputCacheCreation + output`; limit is `max_input_tokens ?? max_context_tokens`; never use `llm.request.maxTokens` |

Kimi v1.x is not a supported target. Existing compatibility branches may remain regression-tested,
but the proposal must not add v1 features or use the obsolete v1 wire-mode path as the design
center.

## Revised architecture

The current Change 4 sketch is too narrow:

```text
ParsedRunnerLine(events, usage?, session_change?, control?)
```

Three accurate sources are auxiliary files, not stdout parser lines. The combined design should
instead define two producers behind one invocation coordinator:

```text
stdout adapter ───────────────┐
                              ├─▶ RunnerObservation
auxiliary usage collector ────┘      ├── events[]
                                     ├── usage_samples[]
                                     ├── session_change?
                                     └── control?
```

An implementation may keep `ParsedRunnerLine` and add a `RunnerUsageCollector` protocol rather
than literally constructing `RunnerObservation`. The invariant is that both producers emit the
same `ContextUsageSample`; raw provider dictionaries never reach writers, transport, Hub, or UI.

The invocation coordinator owns:

- run and sequence assignment for stream events;
- session identity and stale-sample rejection for context usage;
- collector setup before spawn (especially Copilot OTel);
- final file polling/tailing after session discovery (Codex and Kimi);
- latest-sample selection;
- independent delivery of events and context snapshots.

## Fold versus separate

| Criterion | Separate adjacent changes | Combined change |
|---|---|---|
| Parser/fixture work | Claude and OpenCode reopened; other lifecycle paths revisited | One adapter and fixture pass |
| Accurate file sources | Added later, forcing the invocation boundary to change again | Designed into the boundary before implementation |
| Review size | Smaller individual changes | Larger, but separable by capability and phase |
| Ability to ship stream UI alone | Higher | Preserved through phased commits and additive contracts |
| Risk of placeholder usage model becoming permanent | High | Low |
| End-to-end runner matrix | Split across two acceptance suites | One conformance matrix |

The combined change is larger than the current 47-task proposal, but the extra size is bounded:
context usage does not need to become an `AgentOutput`, does not need a second agent-output
migration, and does not require a new visualization beyond correcting the existing context bar and
unknown/estimated states.

## Proposal guardrails

The revised proposal should:

1. Keep two normative capability specs:
   `agent-stream-events` and `agent-context-usage`.
2. Replace the parser-only usage slot with a canonical usage-sample contract plus auxiliary
   collector protocol.
3. Specify exact-vs-estimated status and stale-session rejection.
4. Use the provider-context/latest-request basis above and include regression fixtures that prove
   cached tokens are neither dropped nor double-counted.
5. Target Kimi 0.29.x only.
6. Configure Copilot OTel per invocation with content capture disabled and a unique bounded file.
7. Resolve Codex and Kimi files by the known session/run, never by an unscoped "newest file"
   heuristic.
8. Normalize the local file, HTTP payload, Hub validation, SSE event, `AgentSummary`, and UI type
   to one schema.
9. Preserve older Hub/CLI compatibility and existing text-only output behavior.
10. Split implementation into two merge-safe phases:
    - Phase A: canonical contracts, adapters/collectors, fixtures, invocation coordination;
    - Phase B: stream persistence/rendering plus normalized context delivery and UI state.

## Explicit non-goals

- Session lifecycle and handoff prompting
- Automatic compaction or reset policy
- Process cancellation
- Message threading
- Token cost or rate-limit dashboards
- Persisting raw provider events or OTel content
- Supporting Kimi v1.x
- General-purpose telemetry ingestion

## Remaining proposal-time questions

These do not block the fold decision, but the proposal must settle them:

- Whether Codex rollout discovery can always bind directly to `thread_id`, or needs a bounded
  post-run index lookup with strict timestamp and session checks.
- Whether Claude's final result usage is an aggregate in every supported 2.1.x shape; fixtures
  should establish when it is safe as a fallback.
- The exact Copilot OTel file envelope from an installed current CLI. Official field semantics are
  sufficient for proposal requirements, but implementation completion still requires a fixture.
- How the watchdog will obtain Kimi's effective model capability when the REST session-status path
  is not running. A missing limit must produce a token-only sample with absent percent, never a
  guessed limit or the completion `maxTokens`.
- Whether `estimated` context samples may trigger warning/critical automation. Default answer:
  display them, but do not trigger automatic policy until a later session-lifecycle change decides
  explicitly.
