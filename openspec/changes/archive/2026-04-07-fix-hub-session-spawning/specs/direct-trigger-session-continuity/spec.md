## ADDED Requirements

### Requirement: Direct trigger resumes saved session by default
When the Hub UI sends a direct trigger message without an explicit `[NewSession]` marker, the watchdog SHALL load the agent's saved session ID (from `.agentweave/agents/<agent>-session.json`) and pass it to the agent CLI. If no saved session exists, the agent SHALL start a new session.

#### Scenario: Hub sends message in resume mode
- **WHEN** the Hub sends a direct trigger message containing `[Session: <id>]`
- **THEN** the watchdog resumes the specified session by passing `--resume <id>` (or `--session <id>` for kimi)

#### Scenario: Hub sends message in new-session mode
- **WHEN** the Hub sends a direct trigger message containing `[NewSession]`
- **THEN** the watchdog starts the agent without any `--resume`/`--session` flag, creating a new session

#### Scenario: No session tag present — fallback to saved session
- **WHEN** the Hub sends a direct trigger message with neither `[Session: ...]` nor `[NewSession]` in the content
- **THEN** the watchdog loads the saved session ID for the agent and resumes it (if one exists)

#### Scenario: No session tag and no saved session
- **WHEN** the Hub sends a direct trigger message with no session tags and no session file exists for the agent
- **THEN** the watchdog starts the agent without `--resume`/`--session`, creating a new session

### Requirement: Hub backend emits explicit session intent marker
When the Hub backend receives a trigger request with `session_mode == 'new'`, the message content SHALL include the `[NewSession]` marker so the watchdog can distinguish intentional new-session requests from absent tags.

#### Scenario: New session trigger encodes intent
- **WHEN** `POST /api/v1/agent/trigger` is called with `session_mode = "new"`
- **THEN** the created message's `content` field contains `\n\n[NewSession]`

#### Scenario: Resume trigger encodes session ID
- **WHEN** `POST /api/v1/agent/trigger` is called with `session_mode = "resume"` and a valid `session_id`
- **THEN** the created message's `content` field contains `\n\n[Session: <session_id>]` (existing behavior, unchanged)

### Requirement: Hub UI send button disabled while sessions loading
The Hub UI send button SHALL be disabled while session data is loading to prevent messages from being sent before the auto-select effect has run.

#### Scenario: Send disabled during load
- **WHEN** `AgentPromptPanel` is mounted and `isLoadingSessions` is true
- **THEN** the send button is disabled and cannot be activated

#### Scenario: Send enabled after load
- **WHEN** sessions data has finished loading (regardless of whether sessions exist)
- **THEN** the send button is enabled and the correct session mode is shown
