## Context

AgentWeave already has several foundations for diagnostics: structured Python logging, a local JSONL event log, Hub log forwarding, watchdog heartbeats, agent output streaming, and Hub status pages. The problem is that these pieces are not applied consistently across setup, activation, runner readiness, automatic watchdog execution, transport failures, and scheduled jobs.

Common user-facing failures currently include:

- Proxy agents configured successfully even when the required provider API key is not available.
- Watchdog launching an agent subprocess even when preconditions are known to be missing.
- Hub direct triggers reporting that the watchdog will execute work even when the watchdog is stale or absent.
- Non-fatal setup and sync failures appearing only as transient CLI warnings or being suppressed entirely.
- Hub Logs filtering by a hardcoded agent list rather than actual project agents.
- Job failures being hard to distinguish from idle or skipped jobs.

The implementation should preserve AgentWeave's zero-runtime-dependency CLI constraint and build on the existing logging and transport abstractions.

## Goals / Non-Goals

**Goals:**

- Provide a reusable readiness model for CLI, watchdog, Hub, runners, transports, context files, proxy credentials, MCP setup, and jobs.
- Add `agentweave doctor` as the main user entry point for diagnosing project health.
- Add low-cost preflight checks to existing commands and automatic execution paths.
- Make degraded, skipped, unavailable, and failed states visible through CLI output, local logs, Hub logs, Hub status/agent surfaces, and agent output when applicable.
- Keep automatic behavior conservative: skip launches that cannot succeed when a deterministic precondition is missing.
- Keep diagnostics actionable without exposing secret values.

**Non-Goals:**

- Replacing the existing logging infrastructure.
- Adding new CLI runtime dependencies.
- Making Hub mandatory for local or git workflows.
- Guaranteeing provider credentials are valid by calling external model APIs.
- Redesigning the agent runner system.

## Decisions

### Decision: Add a shared readiness checker instead of command-local checks

Implement a small internal diagnostics module, for example `src/agentweave/diagnostics.py`, that returns structured check results:

```python
{
    "id": "proxy_api_key",
    "target": "minimax",
    "status": "fail",
    "severity": "error",
    "message": "MINIMAX_API_KEY is not set",
    "hint": "Add MINIMAX_API_KEY to .env or export it before starting the watchdog",
}
```

Rationale: `agent configure`, `activate`, `start`, `doctor`, and watchdog execution need the same checks. A shared checker reduces drift and makes tests straightforward.

Alternative considered: add inline checks to each command. This is faster initially but would duplicate logic and likely produce inconsistent messages.

### Decision: Separate configuration validity from runtime readiness

Continue to let `agentweave.yml` validation check shape and supported values. Add readiness checks for runtime state such as environment variables, CLI availability, fresh watchdog heartbeat, Hub reachability, and context files.

Rationale: a committed config can be valid even when a local machine is not ready to run it.

Alternative considered: make config loading fail on missing env vars. That would make committed project config less portable and break workflows where only some machines run certain agents.

### Decision: Use structured diagnostic event names

Emit stable event types such as:

- `diagnostic_check_failed`
- `diagnostic_check_warn`
- `proxy_api_key_missing`
- `watchdog_unavailable`
- `agent_launch_skipped`
- `agent_launch_failed`
- `transport_unavailable`
- `hub_auth_failed`
- `job_run_failed`

Rationale: stable names let Hub UI expose useful filters and let users search logs without parsing arbitrary strings.

Alternative considered: rely only on existing `transport_error` and `watchdog_agent_exit` events. Those are useful but too generic for readiness and usability workflows.

### Decision: Skip known-impossible watchdog launches

When watchdog-triggered execution detects deterministic missing prerequisites, such as a missing proxy API key or missing runner CLI, it should not start the subprocess. It should post a clear agent output line to Hub if HTTP transport is active, emit a structured log event, and update heartbeat back to `idle` or an appropriate degraded status.

Rationale: launching a process that is known to fail creates noisy downstream errors and hides the actual fix.

Alternative considered: continue launching and rely on provider or CLI errors. That preserves current behavior but produces worse diagnostics.

### Decision: Keep diagnostics secret-safe

Diagnostic output MUST identify missing variable names and configuration keys, but MUST NOT print secret values or full commands containing prompt text or credentials.

Rationale: diagnostics are shown in CLI output, local logs, Hub logs, and UI surfaces.

Alternative considered: print full subprocess environment or command for easier debugging. This is unsafe for a collaboration tool that handles API keys and prompts.

### Decision: Hub trigger responses should report queue confidence

The Hub trigger endpoint should still queue messages even when watchdog state is unknown, but the response and event log should distinguish:

- queued and watchdog healthy
- queued but watchdog stale
- queued but no watchdog heartbeat observed
- queued but target agent appears unavailable or pilot/manual

Rationale: the Hub cannot directly control host-side CLIs, so queueing remains useful. The user still needs honest feedback about whether execution is likely.

Alternative considered: reject triggers when watchdog is stale. That could block valid cases where the watchdog polls after a delay or has not emitted a heartbeat yet.

### Decision: Improve Hub logs through metadata, not a separate log system

Keep the existing `/api/v1/logs` endpoint and `EventLog` model as the main durable log surface. Add or derive metadata for category and actual agent filters in the UI.

Rationale: this avoids duplicating logs and keeps the change scoped.

Alternative considered: add a dedicated diagnostics table. This may be useful later, but current needs can fit the existing event log.

## Risks / Trade-offs

- Readiness checks can become noisy -> Use severity levels and show warnings separately from blocking failures.
- Some checks are machine-local and cannot be fully known by the Hub -> Make Hub responses explicit about confidence rather than claiming certainty.
- Skipping subprocess launches changes current behavior -> Limit skips to deterministic failures and preserve queueing behavior.
- Adding `doctor` could become a dumping ground -> Keep check IDs stable and group output by subsystem.
- Structured logs could leak sensitive data if implemented carelessly -> Add tests that assert secret values are not emitted.

## Migration Plan

1. Add the diagnostics data model and check helpers.
2. Add `agentweave doctor` with local-only checks first.
3. Wire proxy env checks into `agent configure`, `activate`, `start`, and watchdog execution.
4. Add structured diagnostic logging for previously silent or transient failures.
5. Improve Hub trigger confidence reporting and logs.
6. Improve Hub Logs filters and failure category display.
7. Add job failure diagnostics and durable run summaries.

Rollback is straightforward because this change adds checks and surfaces rather than changing persistent data contracts significantly. If a check causes false blocking, it can be downgraded from error to warning while preserving diagnostic output.

## Open Questions

- Should watchdog heartbeat support an explicit `degraded` or `error` status, or should diagnostics remain only in logs and latest status messages?
- Should `agentweave activate` return a non-zero exit code when readiness errors exist, or complete with warnings after writing configuration?
- Should `agentweave doctor --json` be included in the first implementation for automation and tests?
- Should Hub persist diagnostic category as a first-class column or derive it from event type in the API/UI?
