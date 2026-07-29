## Why

AgentWeave currently flattens every runner's structured stream into decorated text and tracks
context through three incompatible writer paths. The stream loss forces Hub surfaces to infer
thinking, tools, lifecycle, and errors from prefixes. The context paths use conflicting payload
keys and, for several runners, cumulative totals, missing data, or the wrong denominator.

Both problems meet at the runner invocation boundary. Solving them separately would migrate the
same five adapters, fixtures, session binding, and post-run file discovery twice. They should be
implemented together while remaining separate capabilities: display events are append-only output
records, whereas context usage is a replaceable latest-session snapshot.

## What Changes

- Introduce a provider-neutral stream event contract with exactly seven kinds: `text`,
  `thinking`, `tool_use`, `tool_result`, `status`, `diagnostic`, and `error`.
- Introduce a separate canonical context-usage sample with explicit measurement status, basis,
  source, session identity, token count, effective limit, percentage, and bounded breakdown.
- Give each watchdog invocation a `run_id` and monotonically increasing stream `sequence`; reject
  context samples that do not belong to the active session or invocation.
- Adapt Claude, Codex, OpenCode, GitHub Copilot, and Kimi v0.29.x into the two contracts using
  validated provider-specific accounting rules.
- Support both stdout observations and invocation-scoped auxiliary collectors:
  - Codex rollout `token_count` records;
  - Copilot OTel child `chat` spans with content capture disabled;
  - Kimi session status or matching main-agent Wire/model-capability data.
- Normalize local context files, HTTP transport, Hub validation/storage/SSE, `AgentSummary`, and
  UI types to one schema while accepting legacy aliases during rolling upgrades.
- Add optional structured fields to Hub agent-output storage, REST responses, chat history, and SSE
  events without breaking older CLI or Hub versions.
- Redact and bound structured output payloads before transport and validate them again at the Hub;
  never retain opaque reasoning, full provider events, or OTel prompt/response content.
- Replace prefix-sniffing UI behavior with one shared stream renderer used by agent output, spec
  chat, and agent activity.
- Render measured, estimated, unavailable, and unsupported context states honestly; never show an
  unknown limit as zero percent.
- Correct output history retrieval so the default window returns the newest records in stable
  display order.
- Add provider fixtures and end-to-end contract tests for both outputs across all five runners.

## Capabilities

### New Capabilities

- `agent-stream-events`: Normalized runner events, safe persistence and delivery, backward
  compatibility, deterministic ordering, and consistent rendering across Hub agent surfaces.
- `agent-context-usage`: Provider-aware latest-context measurement, session-safe collection,
  normalized delivery, honest availability states, and consistent Hub display.

### Modified Capabilities

None.

## Impact

- **CLI/watchdog:** runner adapters, invocation lifecycle, output transport, auxiliary usage
  collectors, context snapshot writing, stale-session rejection, redaction, and tests in
  `src/agentweave/watchdog.py`, transport modules, and `tests/`.
- **Hub backend:** additive agent-output migration, typed context-usage ingress and projection,
  REST/SSE serialization, chat-history projection, and backend tests.
- **Hub UI:** output and context types, shared stream renderer, agent context indicators, unknown
  and estimated states, and all current agent-output consumers.
- **Runner integration:** per-invocation Copilot OTel configuration, Codex rollout resolution, Kimi
  0.29.x status/Wire resolution, and OpenCode model-limit discovery.
- **Compatibility:** existing text-only output and legacy context payloads remain readable during
  rolling upgrades; new fields are additive and readable content remains a fallback.
- **Dependencies:** no new CLI runtime dependency is required.

## Non-Goals

- Automatic compaction, handoff, or reset policy.
- Process cancellation or a Stop control.
- Message threading or chat-session routing.
- Token cost, billing, or rate-limit dashboards.
- Persisting complete provider events or telemetry content.
- Expanding Kimi v1 support.
- General-purpose telemetry ingestion.
