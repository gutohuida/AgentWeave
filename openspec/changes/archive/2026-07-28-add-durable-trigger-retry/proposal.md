## Why

The investigation change (`investigate-blockers`) has documented the current behaviour when the watchdog spawns a second trigger for a busy agent, and has recommended a busy-agent policy (mutex with queue, skip-if-busy, or coalesce). This change implements that policy together with three layers of retry that ensure trigger messages are never silently lost: spawn-time check, quick-failure window, and startup reconciliation.

The retry layers are required because the dev loop is autonomous — there is no human watching the watchdog's log for errors. A trigger that fires but does not produce work is a missed token budget and a missed opportunity for the loop to make progress.

## What Changes

- Implement the busy-agent policy chosen in the investigation findings.
- Add the three retry layers: spawn-failure detection, quick-failure window, and startup reconciliation.
- Add Hub events `trigger_failed`, `trigger_stalled`, and `trigger_recovered` and surface them on the dev Hub UI.
- Add watchdog configuration keys for retry policy: `trigger.max_attempts`, `trigger.retry_after_seconds`, `trigger.quick_failure_window`, `trigger.reconcile_on_start`.

## Capabilities

### New Capabilities

- `durable-trigger-retry`: Watchdog and Hub mechanisms that detect spawn failures, quick-failure subprocesses, missed messages from watchdog downtime, and exhausted retries, and that either retry automatically or escalate to the user.

### Modified Capabilities

None.

## Impact

- CLI/watchdog: new configuration keys, new code paths for the three retry layers, new code path for the busy-agent policy.
- Hub backend: possibly new event types; surface new events on the dev Hub UI.
- Tests: new tests for each retry layer plus the busy-agent policy per runner.
- Depends on: `investigate-blockers` being shipped (policy and grace windows come from the findings).