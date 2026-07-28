## ADDED Requirements

### Requirement: Watchdog tracks in-session message count per agent
The watchdog SHALL count messages sent and received by each agent since the start of their current session, resetting the count when a new session is detected.

#### Scenario: Count increments on new messages
- **WHEN** the watchdog detects a new message in an agent's inbox or outbox
- **THEN** the in-session message counter for that agent SHALL increment by 1

#### Scenario: Count resets on new session
- **WHEN** a new session ID is detected for an agent
- **THEN** the in-session message counter SHALL reset to 0

### Requirement: Watchdog sends checkpoint nudge when threshold crossed
The watchdog SHALL send a direct inbox message to an agent instructing it to run `/aw-checkpoint` when the in-session message count crosses the configured threshold.

#### Scenario: Nudge sent at threshold
- **WHEN** an agent's in-session message count reaches `AW_CONTEXT_NUDGE_THRESHOLD` (default: 20)
- **THEN** the watchdog SHALL send a message to that agent with subject `"Context checkpoint reminder"` and content instructing the agent to run `/aw-checkpoint token_threshold` before continuing

#### Scenario: Nudge sent only once per threshold crossing
- **WHEN** the threshold is crossed
- **THEN** the watchdog SHALL NOT send repeated nudges until the next threshold multiple (e.g., 20, 40, 60...)

#### Scenario: Nudge suppressed when threshold is 0
- **WHEN** `AW_CONTEXT_NUDGE_THRESHOLD` is set to 0
- **THEN** no nudge messages SHALL be sent (feature disabled)

#### Scenario: Nudge threshold configurable via env var
- **WHEN** `AW_CONTEXT_NUDGE_THRESHOLD=30` is set in the environment
- **THEN** the watchdog SHALL use 30 as the threshold instead of the default 20

### Requirement: Mission Control displays session age and last checkpoint time
The Mission Control UI SHALL show each agent's current session age and the time elapsed since its last checkpoint, in addition to the context bar.

#### Scenario: Session age displayed
- **WHEN** an agent has an active session with a known `started_at` timestamp
- **THEN** Mission Control SHALL display the elapsed time since `started_at` in human-readable form (e.g., "2h 14m")

#### Scenario: Last checkpoint time displayed
- **WHEN** a checkpoint file exists at `.agentweave/shared/checkpoints/<agent>-*.md`
- **THEN** Mission Control SHALL display the time elapsed since the most recent checkpoint file's modification time

#### Scenario: No checkpoint indicator
- **WHEN** no checkpoint file exists for an agent
- **THEN** Mission Control SHALL display "No checkpoint" with a warning indicator
