## 1. Busy-agent policy

- [ ] 1.1 Implement the policy chosen in
  `openspec/changes/investigate-blockers/findings/blocker-2.md`
  (per-agent mutex with queue, skip-if-busy, or coalesce).
- [ ] 1.2 If the policy is mutex with queue, queued triggers SHALL fire in
  arrival order as the agent becomes idle.
- [ ] 1.3 If the policy is coalesce, the coalesced message SHALL preserve
  the most recent trigger's content and SHALL mark the merged triggers
  in the Hub event log.
- [ ] 1.4 If the chosen policy differs per runner (per the findings),
  implement per-runner selection.

## 2. Retry layers

### 2.1 Spawn-failure detection

- [ ] 2.1.1 When the watchdog attempts to spawn an agent subprocess and
  the spawn fails (CLI not found, immediate exit, other spawn error),
  the watchdog SHALL NOT mark the message as consumed.
- [ ] 2.1.2 The watchdog SHALL log a `trigger_failed` event to the Hub
  with the message ID and failure reason.
- [ ] 2.1.3 The watchdog SHALL increment a per-message attempt counter
  and SHALL retry on the next eligible poll subject to `max_attempts`.

### 2.2 Quick-failure window

- [ ] 2.2.1 When the watchdog spawns an agent subprocess and the
  subprocess exits with a non-zero status within
  `trigger.quick_failure_window`, the watchdog SHALL treat this as a
  quick failure.
- [ ] 2.2.2 The watchdog SHALL NOT mark the message as consumed.
- [ ] 2.2.3 The watchdog SHALL log a `trigger_failed` event with
  failure category `quick_failure` and SHALL retry on the next eligible
  poll subject to `max_attempts`.
- [ ] 2.2.4 If the subprocess exits with a non-zero status AFTER the
  quick-failure window, the watchdog SHALL treat the run as healthy
  and SHALL NOT retry based on the exit status.

### 2.3 Startup reconciliation

- [ ] 2.3.1 On watchdog startup, the watchdog SHALL query the Hub for
  unread `user` messages addressed to its agent that arrived within
  the reconciliation lookback window and that have no associated healthy
  trigger event.
- [ ] 2.3.2 For each such message, the watchdog SHALL re-trigger the
  agent with the same retry accounting as a fresh trigger.
- [ ] 2.3.3 The watchdog SHALL log a `trigger_recovered` event to the
  Hub for each recovered message.
- [ ] 2.3.4 Messages that already have a healthy trigger event recorded
  SHALL NOT be re-triggered.

## 3. Exhaustion and escalation

- [ ] 3.1 When a trigger has been retried `max_attempts` times and the
  spawn continues to fail, the watchdog SHALL log a `trigger_stalled`
  event.
- [ ] 3.2 The watchdog SHALL stop retrying and SHALL escalate to the user
  via a Hub question.

## 4. Configuration

- [ ] 4.1 Read `trigger.max_attempts` (default 3),
  `trigger.retry_after_seconds` (default 300),
  `trigger.quick_failure_window` (default 60),
  `trigger.reconcile_on_start` (default true) from configuration.
- [ ] 4.2 Validate configuration at startup; reject values that would
  obviously break the retry loop (for example, `retry_after_seconds` < 10).

## 5. Hub events

- [ ] 5.1 Add `trigger_failed`, `trigger_stalled`, `trigger_recovered`
  event types to the Hub event log schema.
- [ ] 5.2 Surface these events on the dev Hub UI so the user can see
  when retries happen and when escalation is requested.

## 6. Tests

- [ ] 6.1 Test that a spawn failure increments the attempt counter and
  retries on the next eligible poll.
- [ ] 6.2 Test that a quick-failure subprocess triggers retry but a
  long-running subprocess with a late non-zero exit does not.
- [ ] 6.3 Test that watchdog startup reconciles unread `user` messages.
- [ ] 6.4 Test that retry exhaustion escalates to a Hub question and
  stops further retries.
- [ ] 6.5 Test the chosen busy-agent policy against the behaviour
  matrix from the Blocker 2 findings.

## 7. Documentation

- [ ] 7.1 Update the operator guide to describe the retry policy and
  the meaning of each new event type.
- [ ] 7.2 Document how to disable reconciliation for a particular
  watchdog instance if needed.