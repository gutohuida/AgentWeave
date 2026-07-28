## Context

AgentWeave already records the pieces of a multi-agent run: tasks, messages, agent output, human questions, scheduled jobs, event logs, and SSE broadcasts. These records are useful individually, but they are not grouped into a durable timeline that explains causality across agents and systems.

The current Hub observability model centers on `EventLog`, which stores `event_type`, `agent`, JSON `data`, `severity`, and `timestamp`. Agent output is stored separately in `AgentOutput`. Tasks, messages, questions, and job runs each have their own models and endpoints. The UI exposes log streams, agent activity, task board state, and agent chat, but not a cross-cutting story for a task/session/job.

This change introduces first-class traces and spans in the Hub. The design treats traces as system-owned correlation records. Agents help by using task IDs and task status transitions correctly, but agents do not create trace IDs or span IDs manually.

## Goals / Non-Goals

**Goals:**

- Persist traces and spans as dedicated Hub database records.
- Automatically create and extend traces from existing Hub and CLI/watchdog activity.
- Support trace roots for task, session, message, and job-run activity in the first version.
- Expose trace list and trace detail APIs.
- Render a Hub timeline that groups spans, events, messages, questions, and output into a readable story.
- Update generated AI instructions to preserve trace continuity through normal AgentWeave practices.
- Keep the model compatible with later OpenTelemetry export.

**Non-Goals:**

- Do not add OpenTelemetry export in this change.
- Do not require agents to call new trace-specific tools.
- Do not replace existing logs, task APIs, message APIs, or SSE events.
- Do not trace every token or every raw output line as its own span.
- Do not change local/manual relay into a fully traced mode; Hub-backed activity is the first-class target.
- Do not introduce an external observability dependency.

## Decisions

### Decision: Add dedicated trace and span tables

Add Hub models similar to:

```text
Trace
  id
  project_id
  root_type: task | session | message | job_run
  root_id
  title
  status: running | completed | failed | cancelled
  started_at
  ended_at
  metadata

Span
  id
  project_id
  trace_id
  parent_span_id
  kind: task | message | agent_run | question | job | output | status | log
  name
  agent
  status: running | completed | failed | cancelled
  started_at
  ended_at
  data
```

Rationale: A dedicated model gives the Hub efficient queries, stable APIs, and a clean path to future OpenTelemetry export. It avoids turning `EventLog.data` into the primary data model.

Alternative considered: only add `trace_id` and `span_id` inside `EventLog.data`. That would be faster but would make timeline queries brittle, difficult to index, and harder to evolve.

### Decision: Keep EventLog, AgentOutput, and domain records as source records

Traces and spans correlate existing records; they do not replace them. Existing write paths should continue to persist their normal domain records, then attach or create trace/span records as part of the same logical operation.

Rationale: Logs and domain APIs are already part of the Hub contract. Preserving them limits regressions and lets the trace UI link back to the source task, message, question, job run, output line, or log entry.

Alternative considered: store all future activity only as spans. That would force a broad rewrite and make existing pages depend on a new abstraction before it has proven stable.

### Decision: Trace correlation is automatic and deterministic

The Hub should derive trace context from available identifiers in this order:

```text
workflow_run_id (future)
  -> job_run_id
    -> task_id
      -> session_id
        -> message_id
```

For the first implementation, task ID, session ID, message ID, and job run ID are supported. When a message includes `task_id`, it joins the task trace. When agent output includes `session_id`, it joins the session trace unless it can be linked to a task-triggered session. Job-triggered work joins the job-run trace and may also link to a task trace if the triggered message creates one.

Rationale: AgentWeave already uses these identifiers. The system can preserve causality without asking agents to invent or carry trace IDs.

Alternative considered: expose a `create_trace` MCP tool and require agents to call it. That would produce inconsistent results and distract agents from their actual work.

### Decision: Add trace context columns where useful

Add nullable `trace_id` and `span_id` references to records that need fast joins or direct navigation, starting with event logs and agent output. For records where migrations are risky or unnecessary, use source-reference tables or span `data` to link source IDs.

Candidate direct references:

- `event_logs.trace_id`, `event_logs.span_id`
- `agent_outputs.trace_id`, `agent_outputs.span_id`
- `messages.trace_id`, `messages.span_id`
- `questions.trace_id`, `questions.span_id`
- `job_runs.trace_id`, `job_runs.span_id`

Rationale: Direct references make trace detail APIs simpler and allow navigation from existing UI screens. Nullable columns preserve backward compatibility for old records.

Alternative considered: use only a generic `span_links` table. That is flexible but adds complexity to every query.

### Decision: The first UI is timeline-first, not analytics-first

The first Hub UI should show trace list and trace detail:

- trace list: title, root type, status, primary agent, started, duration, counts;
- trace detail: ordered spans and related source records;
- source links: task, message, question, agent output, logs, job run;
- navigation entry points from tasks, agent sessions, jobs, and log rows.

Rationale: The immediate user need is understanding what happened. Aggregate dashboards can be added after the trace data proves useful.

Alternative considered: start with charts and metrics. That would be less useful without reliable trace correlation.

### Decision: Instruction changes focus on traceability discipline

Generated instructions should tell agents to:

- always pass `task_id` for task-related messages;
- update task status at meaningful boundaries;
- keep delegation and completion messages linked to the same task;
- include verification commands in completion messages;
- use Hub/MCP tools instead of manual relay when MCP tools are available;
- never invent trace IDs or span IDs.

Rationale: Agents can improve trace quality by using existing AgentWeave tools correctly. They should not become responsible for observability internals.

Alternative considered: instruct agents to write trace summaries in every message. That would pollute communication and still be unreliable.

## Risks / Trade-offs

- Schema growth increases migration complexity -> keep all trace references nullable and add tests for fresh installs and migrated databases.
- Trace correlation may be incomplete for legacy or manual-relay activity -> show partial traces gracefully and mark unknown source links as absent rather than failing.
- High-volume agent output could create too many spans -> group output by agent/session/run and link output rows without making each line a span.
- Existing write paths may miss trace attachment -> centralize trace creation helpers and add tests for each activity type.
- Timeline UI can become noisy -> provide event filtering and span grouping from the first UI version.
- Committing to dedicated tables is more work than JSON correlation -> the added structure is justified by expected future eval/replay and OpenTelemetry needs.

## Migration Plan

1. Add trace/span tables and nullable trace references through Alembic.
2. Deploy with no backfill requirement; existing records remain visible in current views.
3. Begin creating traces for new activity only.
4. Optionally add a later best-effort backfill command for recent tasks/sessions if users need historical timelines.
5. Rollback by leaving trace tables unused; existing task/message/log behavior continues to work independently.

## Open Questions

- Should task traces and session traces be separate but linked, or should task-triggered sessions be folded into the task trace by default?
- Should trace status be derived from the root record status, span status, or both?
- Should the first UI live as a new top-level "Traces" page, or as task/session detail panels with no top-level page?
- How long should trace data be retained relative to event logs and agent output retention?
