## 1. Data Model

- [x] 1.1 Add Hub SQLAlchemy models for traces and spans with project scoping, root metadata, status, timestamps, parent span links, and JSON metadata/data fields.
- [x] 1.2 Add Alembic migration for trace/span tables and nullable trace/span references on event logs, agent output, messages, questions, and job runs where the current schema supports direct references.
- [x] 1.3 Add Pydantic schemas for trace summary, trace detail, span detail, and related source references.
- [x] 1.4 Add indexes for project trace lookup, trace root lookup, span ordering, span parent lookup, and source-record trace references.

## 2. Trace Correlation Service

- [x] 2.1 Create a Hub trace service/helper that resolves or creates traces from task ID, session ID, message ID, and job run ID.
- [x] 2.2 Add span creation/update helpers for task, message, agent-run, question, job, output, status, and log activity.
- [x] 2.3 Define status derivation rules for running, completed, failed, and cancelled traces/spans.
- [x] 2.4 Ensure trace helpers are project-scoped and cannot attach records across projects.

## 3. Hub Write-Path Integration

- [x] 3.1 Attach trace context when tasks are created or task status changes.
- [x] 3.2 Attach trace context when messages are created, read, or linked to tasks.
- [x] 3.3 Attach trace context when agent trigger requests start new or resumed sessions.
- [x] 3.4 Attach trace context when agent output is ingested with a session ID.
- [x] 3.5 Attach trace context when human questions are asked and answered.
- [x] 3.6 Attach trace context when AI jobs fire and job runs complete or fail.
- [x] 3.7 Attach trace context when CLI/watchdog logs are pushed to `/api/v1/logs`.

## 4. Trace APIs

- [x] 4.1 Add authenticated trace list endpoint with filters for root type, status, agent, search text, and pagination.
- [x] 4.2 Add authenticated trace detail endpoint returning trace metadata, ordered spans, related events, and source references.
- [x] 4.3 Add source navigation fields so tasks, sessions, job runs, logs, and agent activity can link to their related trace.
- [x] 4.4 Ensure trace APIs enforce project isolation and return not found or denied for another project's trace.

## 5. Hub UI

- [x] 5.1 Add trace API client hooks and TypeScript types.
- [x] 5.2 Add trace list view with root type, title, status, primary agent, start time, duration, and activity counts.
- [x] 5.3 Add trace detail timeline with grouped spans, related event/log/output/message/question rows, status styling, and source links.
- [x] 5.4 Add navigation links from task details, agent sessions/activity, jobs, and log rows to the related trace when trace context exists.
- [x] 5.5 Add timeline filtering or grouping controls so noisy traces remain readable.

## 6. Agent Instructions

- [x] 6.1 Update generated AI context with a traceability discipline section.
- [x] 6.2 Update collaboration protocol instructions to require task-linked delegation and completion messages when work belongs to a task.
- [x] 6.3 Update relevant skill templates so delegate/done/status/checkpoint flows preserve task IDs and verification commands.
- [x] 6.4 State clearly that agents must not invent trace IDs or span IDs because AgentWeave assigns them.

## 7. Tests

- [x] 7.1 Add Hub migration tests for fresh databases and upgraded databases.
- [x] 7.2 Add trace service unit tests for task, session, message, and job-run trace resolution.
- [x] 7.3 Add Hub API tests for trace list, trace detail, filtering, and project isolation.
- [x] 7.4 Add write-path tests covering task, message, trigger, output, question, job, and pushed-log trace attachment.
- [x] 7.5 Add UI tests for trace list/detail rendering if the current Vitest setup supports the required components.
- [x] 7.6 Add CLI/watchdog/logging tests for forwarding task/session/message/job context where applicable.

## 8. Documentation And Verification

- [x] 8.1 Document trace timeline behavior in the Hub dashboard guide or a new observability guide.
- [x] 8.2 Update API reference documentation for trace endpoints and trace-related response fields.
- [x] 8.3 Run backend Hub tests for trace functionality.
- [x] 8.4 Run affected CLI tests for logging/watchdog context.
- [x] 8.5 Run UI tests or build checks for the Hub UI.
- [x] 8.6 Run `openspec status --change add-trace-timeline` and confirm the change is apply-ready.
