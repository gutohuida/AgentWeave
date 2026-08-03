## Why

AgentWeave already renders the newest context-window sample reported by a runner, but that sample
is transient context pressure, not durable accounting. The active Hub-native umbrella requires a
separate record of how many tokens each completed turn consumed, totals per agent and project, and
a project budget that pauses autonomous work without taking control away from the operator.

This is the dependency-independent accounting slice identified as ready to propose in
`openspec/changes/archive/2026-08-02-agent-conversation-workspace/design.md`. It closes phase 9 of
`2026-07-30-hub-native-experience` through a focused successor change.

## What Changes

- Persist exactly one normalized usage record per Hub-owned run. A runner that reports no usable
  token telemetry produces an explicit unavailable record, never a fabricated zero.
- Parse turn totals from Claude Code result telemetry, Codex turn/token-count telemetry, and
  OpenCode step telemetry into one runner-neutral shape.
- Expose per-agent and project aggregates. Monetary telemetry remains optional and is always
  labelled an API-equivalent estimate; reported rate-limit allowance takes display precedence.
- Add an optional per-project token budget and expose its used/remaining/exhausted state.
- Classify turns as operator-initiated or autonomous. Once a project budget is exhausted, queued
  agent-to-agent and scheduled-job work remains durable but does not start; operator input still
  starts and can carry queued work with it.
- Surface accounting availability and budget exhaustion in the operator UI.

## Capabilities

### New Capabilities

- `usage-accounting`: durable per-turn token accounting, aggregation, presentation semantics, and
  autonomous-turn budget enforcement.

### Modified Capabilities

(none)

## Impact

- Hub database models and a migration for turn usage, project token budgets, and run initiator.
- Runner parsing and the direct-run recording loop.
- Queue/scheduler classification of operator, agent, and scheduled-job entries.
- A project-scoped accounting API and React Query consumer.
- Project/conversation UI budget state.

