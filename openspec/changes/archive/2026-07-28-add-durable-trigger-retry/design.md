## Context

The Blocker 2 findings from `investigate-blockers` document the current behaviour when the watchdog spawns a second trigger for a busy agent, and recommend one of: per-agent mutex with queue, skip-if-busy, or coalesce. This change implements that policy together with three layers of retry that ensure trigger messages are never silently lost.

The exact policy and any per-runner quirks come from the findings.

## Goals / Non-Goals

**Goals:**

- Implement the busy-agent policy chosen in the findings.
- Implement the three retry layers: spawn-failure detection, quick-failure window, startup reconciliation.
- Add Hub events `trigger_failed`, `trigger_stalled`, `trigger_recovered` and surface them on the dev Hub UI.
- Add watchdog configuration: `trigger.max_attempts`, `trigger.retry_after_seconds`, `trigger.quick_failure_window`, `trigger.reconcile_on_start`.

**Non-Goals:**

- Touch the auto-reset behaviour (that is the add-auto-reset-mode change).
- Touch the context-tracking pipeline (that is the fix-context-tracking change).
- Replace the existing `retry_after` watchdog parameter; this change adds new options alongside it.

## Decisions

### Decision: Three-layer retry, one retry counter

All three retry layers share a single per-message attempt counter. A spawn failure, a quick-failure exit, and a startup-reconciliation retry all increment the same counter. When the counter reaches `max_attempts`, the watchdog escalates and stops retrying.

### Decision: Hub events are first-class

`trigger_failed`, `trigger_stalled`, and `trigger_recovered` are persisted on the Hub and surfaced on the dev Hub UI. This lets the user see retry activity without reading watchdog logs.

### Decision: Startup reconciliation is opt-out, not opt-in

Reconciliation runs by default on watchdog startup. Operators can disable it via `trigger.reconcile_on_start: false` if they have a reason to. The default-on behaviour is required because watchdog downtime can cause silent message loss otherwise.

### Decision: Busy-agent policy is per-agent, not global

The chosen policy (mutex, skip, or coalesce) is configured per agent in `agentweave.yml`. Different agents may need different policies if the findings identify per-runner quirks.

## Open Questions

- The specific policy and any per-runner quirks come from the findings.
- Whether to add a backoff multiplier between retries (e.g., exponential backoff) or keep flat retry interval. Default: flat, per the design.md. The implementing agent can introduce backoff if testing shows it's needed.