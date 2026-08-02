## MODIFIED Requirements

### Requirement: Agent Output distinguishes continuation, fresh start, and handoff

The conversation workspace MUST present existing AgentWeave conversations as resumable choices, a
`New conversation (start fresh)` choice that deliberately creates a new unbound conversation, and
a `Handoff` action that preserves context through a durable checkpoint before creating a successor
conversation.

The normal picker and continuity controls MUST use `conversation_id` and MUST NOT use provider
session IDs as conversation labels or values. The agent-detail header MUST NOT present the legacy
`Compact` and `Reset` actions as primary conversation controls.

#### Scenario: Existing conversation is selected

- **WHEN** the user selects an existing conversation and sends a message
- **THEN** the trigger MUST include its exact `conversation_id`
- **AND** the server MUST derive provider continuation from that conversation's binding

#### Scenario: User starts fresh without a handoff

- **WHEN** the user selects `New conversation (start fresh)` and sends a message
- **THEN** the trigger MUST omit `conversation_id` so the server creates one synchronously
- **AND** it MUST NOT inject handoff-resume instructions into the message

#### Scenario: Legacy context actions are absent

- **WHEN** the agent conversation renders
- **THEN** `Compact` and `Reset` buttons MUST NOT appear in its primary header
- **AND** durable transitions MUST be initiated through `Handoff`

### Requirement: Handoff checkpoints the selected conversation

The `Handoff` action MUST append a checkpoint request to the selected AgentWeave conversation. The
instruction MUST require the agent to invoke its checkpoint workflow with reason `pre_handoff` and
preserve session intent, modified files, decisions and rationale, blockers, exact next steps, and
verification commands in the configured durable checkpoint location.

#### Scenario: User requests a handoff

- **WHEN** an automatically managed agent has an existing conversation selected
- **AND** the user activates `Handoff`
- **THEN** the trigger MUST carry the selected `conversation_id`
- **AND** the prompt MUST request a durable `pre_handoff` checkpoint
- **AND** the workspace MUST be armed to create one successor conversation

#### Scenario: Handoff is being prepared

- **WHEN** the checkpoint turn is queued or running
- **THEN** the UI MUST display `Preparing durable handoff`
- **AND** handoff controls MUST remain disabled until that checkpoint turn settles
- **AND** unrelated running-state logic MUST NOT disable ordinary queued composer input

#### Scenario: Checkpoint turn completes

- **WHEN** the checkpoint turn emits a completed status
- **OR** the agent transitions from running back to idle
- **THEN** the UI MUST display that the handoff is ready
- **AND** the message composer MUST become available for the successor conversation

#### Scenario: Agent cannot be triggered automatically

- **WHEN** the agent's runner is configured as manual
- **THEN** the `Handoff` action MUST be disabled
- **AND** the UI MUST explain that handoff requires an automatically managed runner

### Requirement: The next conversation resumes the durable handoff

After a handoff is ready, the next user message MUST create exactly one unbound successor
conversation. Its prompt MUST instruct the new provider session to read the newest checkpoint for
its agent, treat the checkpoint as authoritative, and continue from its next steps before handling
the user's request.

#### Scenario: First message after handoff

- **WHEN** the handoff is ready and the user sends the next message
- **THEN** the trigger MUST omit `conversation_id` and return the new successor `conversation_id`
- **AND** the message MUST include the handoff-resume instructions
- **AND** the user's original request MUST remain present

#### Scenario: Successor conversation identity is immediate

- **WHEN** the fresh trigger is accepted
- **THEN** the selector MUST bind to its returned `conversation_id` without waiting for output
- **AND** the UI MUST indicate that it is continuing the successor conversation

#### Scenario: Messages after the resumed handoff

- **WHEN** the user sends another message in the successor conversation
- **THEN** the trigger MUST carry that successor `conversation_id`
- **AND** it MUST NOT inject the handoff-resume instructions again
- **AND** it MUST NOT create another conversation

### Requirement: Conversation transition state is visible and scoped to the agent

The conversation workspace MUST visibly distinguish continuing an existing conversation, preparing
a handoff, a ready handoff, starting a fresh conversation, and continuing its successor. Transient
handoff state MUST be cleared when the selected agent changes or the user manually changes the
conversation selection. Provider-binding latency MUST NOT be represented as a pending application
identity state because `conversation_id` is already available.

#### Scenario: User changes agents

- **WHEN** the user selects a different agent
- **THEN** handoff state from the previous agent MUST be cleared
- **AND** the new agent's most recently active conversation MUST be selected when available

#### Scenario: User manually changes conversation

- **WHEN** the user changes the conversation selection during an idle state
- **THEN** any prepared handoff MUST be cancelled
- **AND** the continuity indicator MUST describe the newly selected conversation
