## Why

AgentWeave records tasks, messages, questions, agent output, jobs, and log events, but it does not yet provide a single correlated story for why an agent ran, what triggered it, what it did, and how the work ended. A first-class trace timeline will make multi-agent work easier to debug, review, replay, and eventually evaluate.

## What Changes

- Add a dedicated trace/span observability model for Hub-backed projects.
- Correlate tasks, messages, agent triggers, questions, jobs, agent output, and log events into trace timelines.
- Add Hub APIs to list traces and inspect a trace with its spans and related events.
- Add a Hub UI timeline view that shows the full story of a task, session, job run, or message-driven delegation.
- Update AgentWeave-generated AI instructions so agents preserve correlation by using task IDs, task status transitions, and Hub/MCP tools consistently.
- Keep trace IDs and span IDs system-assigned; agents must not manually invent trace identifiers.
- Leave OpenTelemetry export for a later change, but choose field names and relationships that do not block it.

## Capabilities

### New Capabilities

- `trace-timeline`: Persistent trace/span timelines for multi-agent work, including automatic correlation, APIs, Hub UI, and agent traceability instructions.

### Modified Capabilities

None.

## Impact

- Hub database: new trace/span tables and trace correlation columns or relationships for existing activity records.
- Hub API: new trace list/detail endpoints and updates to existing write paths that create messages, tasks, questions, jobs, agent triggers, logs, and agent output.
- Hub UI: new trace timeline view and navigation from tasks, sessions, jobs, agents, and logs.
- CLI/watchdog/logging: include task/session/message/job context when forwarding events to Hub.
- Templates/context: update generated agent instructions and collaboration protocol guidance for traceability discipline.
- Tests: new Hub backend tests for trace creation/correlation, UI tests for timeline rendering where the current test setup supports it, and focused CLI/watchdog tests for forwarded trace context.
