## ADDED Requirements

### Requirement: Spec tab continues the agent's most recent session

The Hub Spec tab's embedded agent chat MUST continue the selected agent's most
recent session rather than starting a new one on every message. It MUST request
this by sending `session_mode: "resume"` with no `session_id`, so the trigger
endpoint emits no session tag and the watchdog resolves the agent's last saved
session.

#### Scenario: Second message continues the first conversation

- **WHEN** the user sends a message to an agent that has a saved session
- **THEN** the agent MUST continue that session
- **AND** the agent MUST retain the context of the earlier turns in that session

#### Scenario: First message to an agent with no saved session

- **WHEN** the user sends a message to an agent that has no saved session
- **THEN** a new session MUST be started
- **AND** no error MUST be surfaced to the user

#### Scenario: Warm agent pulled into the Spec tab

- **WHEN** the user selects an agent whose most recent session was started outside
  the Spec tab
- **THEN** that session MUST be continued
- **AND** the agent MUST retain the context of the work it was previously doing

#### Scenario: Runner independence

- **WHEN** the selected agent uses any supported runner
- **THEN** the resume behaviour MUST be identical
- **AND** the Spec tab MUST NOT contain any runner-specific session handling

### Requirement: Deliberate new session

The Spec tab MUST let the user start a fresh session for the selected agent
without leaving the Spec tab, so a long or derailed session can be abandoned.

#### Scenario: User starts a new session

- **WHEN** the user chooses to start a new session and sends a message
- **THEN** that message MUST be sent with `session_mode: "new"`
- **AND** the agent MUST start a session with no prior context

#### Scenario: New session applies once

- **WHEN** the user has started a new session and sends a further message
- **THEN** that message MUST continue the newly created session
- **AND** it MUST NOT start another new session

### Requirement: Session continuity is visible

The Spec tab MUST make it apparent whether the next message will continue an
existing session or begin a new one, so the user is never surprised by lost
context.

#### Scenario: Continuing an existing session

- **WHEN** the selected agent has a saved session
- **THEN** the Spec tab MUST indicate that the conversation will continue

#### Scenario: No session yet

- **WHEN** the selected agent has no saved session
- **THEN** the Spec tab MUST indicate that the next message starts a new session
