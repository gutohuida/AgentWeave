## ADDED Requirements

### Requirement: Watchdog detects spawn failures and retries

When the watchdog attempts to spawn an agent subprocess for a trigger message and the spawn fails, the watchdog SHALL NOT mark the message as consumed. The watchdog SHALL log a `trigger_failed` event to the Hub, SHALL increment a per-message attempt counter, and SHALL retry on a later poll subject to configured limits.

#### Scenario: Spawn failure is detected and logged

- **WHEN** the watchdog attempts to spawn an agent subprocess
- **AND** the spawn fails
- **THEN** the watchdog SHALL log a `trigger_failed` event to the Hub with the message ID and failure reason
- **AND** the watchdog SHALL NOT mark the message as consumed
- **AND** the watchdog SHALL retry the spawn on the next eligible poll subject to the configured max attempts

#### Scenario: Spawn retries respect max attempts

- **WHEN** the watchdog has retried a trigger `max_attempts` times and the spawn continues to fail
- **THEN** the watchdog SHALL log a `trigger_stalled` event to the Hub
- **AND** the watchdog SHALL stop retrying and SHALL escalate to the user via a Hub question

### Requirement: Watchdog detects quick-failure subprocesses and retries

When the watchdog spawns an agent subprocess and the subprocess exits with a non-zero status within the configured quick-failure window, the watchdog SHALL treat this as a quick failure and SHALL retry subject to the same limits as spawn failures.

#### Scenario: Quick failure is detected

- **WHEN** an agent subprocess exits with a non-zero status within the quick-failure window
- **THEN** the watchdog SHALL log a `trigger_failed` event to the Hub with the failure category set to `quick_failure`
- **AND** the watchdog SHALL retry on the next eligible poll

#### Scenario: Long-running run is not a quick failure

- **WHEN** an agent subprocess runs longer than the quick-failure window
- **THEN** the watchdog SHALL treat the run as healthy and SHALL NOT mark the message for retry based on its eventual exit status

### Requirement: Watchdog reconciles missed messages on startup

When the watchdog starts or restarts, it SHALL query the Hub for any unread `user` messages addressed to its agent that arrived within the configured reconciliation lookback window and that have no associated healthy trigger event. For each such message the watchdog SHALL re-trigger the agent.

#### Scenario: Missed message is recovered on startup

- **WHEN** the watchdog starts and finds an unread `user` message older than the reconciliation threshold with no associated trigger event
- **THEN** the watchdog SHALL re-trigger the agent for that message
- **AND** the watchdog SHALL log a `trigger_recovered` event to the Hub

#### Scenario: Already-triggered message is not re-triggered

- **WHEN** the watchdog starts and finds an unread `user` message that already has a healthy trigger event recorded
- **THEN** the watchdog SHALL NOT re-trigger the agent for that message

### Requirement: Per-agent busy policy prevents double-spawn

The watchdog SHALL implement the per-agent busy policy chosen in the Blocker 2 findings (mutex with queue, skip-if-busy, or coalesce) and SHALL guarantee that no second agent subprocess is spawned for the same agent while the first is still within its quick-failure window, unless the chosen policy is coalesce.

#### Scenario: Per-agent mutex prevents double-spawn

- **WHEN** a trigger arrives for an agent whose previous subprocess is still within the quick-failure window
- **THEN** the watchdog SHALL apply the configured busy policy and SHALL NOT spawn a second subprocess unless the policy explicitly allows it

#### Scenario: Queued triggers fire in order

- **WHEN** multiple triggers arrive for an agent that is busy
- **THEN** the watchdog SHALL queue them in arrival order and SHALL fire them sequentially as the agent becomes idle

### Requirement: Trigger retry is configurable

The watchdog SHALL read its trigger retry policy from configuration: `trigger.max_attempts`, `trigger.retry_after_seconds`, `trigger.quick_failure_window`, and `trigger.reconcile_on_start`. Defaults SHALL match the design (3, 300, 60, true).

#### Scenario: Defaults apply when config is absent

- **WHEN** the watchdog starts without explicit trigger retry configuration
- **THEN** the defaults SHALL be 3 attempts, 300s retry delay, 60s quick-failure window, and reconciliation on startup

#### Scenario: Explicit config overrides defaults

- **WHEN** the watchdog configuration sets non-default values for trigger retry options
- **THEN** the watchdog SHALL use those values rather than the defaults