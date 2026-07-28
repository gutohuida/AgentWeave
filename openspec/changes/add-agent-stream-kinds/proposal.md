## Why

AgentWeave currently flattens every runner's structured stream into decorated text. That loses
thinking, tool-call correlation, lifecycle, and error semantics, forces each Hub surface to infer
meaning from string prefixes, and leaves no stable boundary for the adjacent context-usage work.

## What Changes

- Introduce a provider-neutral stream event contract with exactly seven kinds: `text`,
  `thinking`, `tool_use`, `tool_result`, `status`, `diagnostic`, and `error`.
- Give each watchdog invocation a `run_id` and monotonically increasing `sequence`, and correlate
  tool calls and results with provider call IDs.
- Adapt Claude, Codex, OpenCode, GitHub Copilot, and Kimi v0.29.x streams into the common contract
  while retaining readable `content` fallbacks and tolerating unknown provider events.
- Add optional structured fields to Hub agent-output storage, REST responses, chat history, and SSE
  events without breaking older CLI or Hub versions.
- Redact and bound structured payloads before transport and validate them again at the Hub; never
  retain opaque or encrypted reasoning fields or complete raw provider events.
- Replace prefix-sniffing UI behavior with one shared renderer used by agent output, spec chat, and
  agent activity, including collapsible thinking and paired tool activity.
- Correct output history retrieval so the default window returns the newest records in stable
  display order.
- Establish a shared parser result boundary with a separate usage slot so the next
  context-tracking change can add normalized usage samples without redesigning the stream path.
- Add runner fixtures and contract tests for all five supported stream formats.
- Deliberately exclude process cancellation, message threading, and context-percentage
  normalization from this change.

## Capabilities

### New Capabilities

- `agent-stream-events`: Normalized runner events, safe persistence and delivery, backward
  compatibility, deterministic ordering, and consistent rendering across Hub agent surfaces.

### Modified Capabilities

None.

## Impact

- **CLI/watchdog:** runner parsers, invocation lifecycle, output transport calls, redaction, and
  parser tests in `src/agentweave/watchdog.py`, transport modules, and `tests/`.
- **Hub backend:** an additive database migration, agent-output models/schemas/endpoints, SSE
  serialization, chat-history projection, and backend tests.
- **Hub UI:** agent output types and API hooks plus a shared stream renderer consumed by
  `AgentOutputPanel`, `SpecPage`, and `AgentActivityTab`.
- **Compatibility:** existing text-only records and clients remain valid; new fields are nullable
  and readable content remains available as a fallback.
- **Dependencies:** no new CLI runtime dependency is required.
