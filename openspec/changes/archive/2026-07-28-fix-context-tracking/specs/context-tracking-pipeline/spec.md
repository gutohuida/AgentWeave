## ADDED Requirements

### Requirement: Context-tracking pipeline reports the actual agent context percentage

The Hub SHALL persist a context-usage value for each active agent session that is sourced from the agent's CLI stream events when those events exist, and SHALL render that value in the Hub UI in a way that monotonically increases during a single session and resets to a low value when a new session begins.

#### Scenario: Long-running session shows increasing context

- **WHEN** an agent session runs long enough for its context to fill
- **THEN** the Hub UI SHALL display a non-zero context percentage that increases as the session progresses
- **AND** the displayed value SHALL be within a reasonable tolerance of the CLI's reported percentage when a CLI-reported value exists

#### Scenario: New session resets the context display

- **WHEN** an agent starts a fresh session
- **THEN** the Hub UI SHALL display a low context percentage for that session rather than carrying forward the previous session's value

#### Scenario: All runners show context

- **WHEN** the dev loop uses opencode, kimi, and codex
- **THEN** the Hub UI SHALL display a non-stale context percentage for each runner
- **AND** the displayed value SHALL be within a documented tolerance of the CLI's reported percentage, or be marked as an estimate when a CLI-reported value is unavailable

### Requirement: Context-tracking pipeline is tested across all runners

The fix SHALL include tests that exercise the full pipeline (CLI → file → Hub POST → storage → UI) for every runner the dev loop uses.

#### Scenario: All-runner end-to-end test exists

- **WHEN** the fix is shipped
- **THEN** a test SHALL run a long session per runner and assert that the Hub stores and renders a context value matching the CLI's report within a documented tolerance
- **AND** that test SHALL fail if any runner in the pipeline silently swallows context data

#### Scenario: Watchdog restart does not corrupt context state

- **WHEN** the watchdog restarts while an agent session is running
- **THEN** the next context-usage post SHALL reflect the agent's current state rather than carrying forward stale data from before the restart