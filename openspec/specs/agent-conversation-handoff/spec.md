# agent-conversation-handoff Specification

## Purpose

Durable conversation transitions from the Hub Agent Output screen: preserve the
current runner session in a checkpoint, start one fresh session, resume from the
checkpoint, and then continue that new session normally.

## Requirements

### Requirement: Agent Output distinguishes continuation, fresh start, and handoff

The Agent Output screen MUST present existing conversation IDs as resumable
conversations, a `New conversation (start fresh)` choice that deliberately
discards prior conversational context, and a `Handoff` action that preserves
context through a durable checkpoint before starting fresh.

The agent-detail header MUST NOT present the legacy `Compact` and `Reset`
actions as primary conversation controls.

#### Scenario: Existing conversation is selected

- **WHEN** the user selects an existing conversation ID and sends a message
- **THEN** the trigger MUST use `session_mode: "resume"`
- **AND** it MUST include the selected conversation ID as `session_id`

#### Scenario: User starts fresh without a handoff

- **WHEN** the user selects `New conversation (start fresh)` and sends a message
- **THEN** the trigger MUST use `session_mode: "new"`
- **AND** it MUST NOT inject handoff-resume instructions into the message

#### Scenario: Legacy context actions are absent

- **WHEN** the Agent detail screen renders
- **THEN** `Compact` and `Reset` buttons MUST NOT appear in its primary header
- **AND** durable transitions MUST be initiated through `Handoff`

### Requirement: Handoff checkpoints the selected conversation

The `Handoff` action MUST resume the selected conversation and instruct that
session to invoke its `aw-checkpoint` workflow with reason `pre_handoff`. The
instruction MUST require the checkpoint to preserve session intent, modified
files, decisions and rationale, blockers, exact next steps, and verification
commands under `.agentweave/shared/checkpoints/`.

#### Scenario: User requests a handoff

- **WHEN** an automatically managed agent has an existing conversation selected
- **AND** the user clicks `Handoff`
- **THEN** the Hub MUST trigger the selected conversation with
  `session_mode: "resume"` and its exact `session_id`
- **AND** the prompt MUST request a durable `pre_handoff` checkpoint
- **AND** the conversation selector MUST be armed for one fresh conversation

#### Scenario: Handoff is being prepared

- **WHEN** the checkpoint turn is queued or running
- **THEN** the UI MUST display `Preparing durable handoff`
- **AND** the selector and message composer MUST remain disabled

#### Scenario: Checkpoint turn completes

- **WHEN** the checkpoint turn emits a completed status
- **OR** the agent transitions from running back to idle
- **THEN** the UI MUST display that the handoff is ready
- **AND** the message composer MUST become available for the fresh conversation

#### Scenario: Agent cannot be triggered automatically

- **WHEN** the agent is in pilot mode
- **OR** its runner is configured as manual
- **THEN** the `Handoff` action MUST be disabled
- **AND** the UI MUST explain that handoff requires an automatically managed runner

### Requirement: The next conversation resumes the durable handoff

After a handoff is ready, the next user message MUST start exactly one fresh
runner session. Its prompt MUST instruct the new session to read the newest
checkpoint for its agent, then `.agentweave/shared/context.md`, treat the
checkpoint as authoritative, and continue from its `Next Steps` before handling
the user's request.

#### Scenario: First message after handoff

- **WHEN** the handoff is ready and the user sends the next message
- **THEN** the trigger MUST use `session_mode: "new"`
- **AND** the message MUST include the handoff-resume instructions
- **AND** the user's original request MUST remain present

#### Scenario: New conversation identity becomes available

- **WHEN** output or the session list reveals a conversation ID not present
  before the fresh trigger
- **THEN** the selector MUST automatically bind to that new conversation ID
- **AND** the UI MUST indicate that it is continuing the new conversation

#### Scenario: Messages after the resumed handoff

- **WHEN** the user sends another message after the new conversation is bound
- **THEN** the trigger MUST use `session_mode: "resume"` with the new
  conversation ID
- **AND** it MUST NOT inject the handoff-resume instructions again
- **AND** it MUST NOT create another fresh conversation

### Requirement: Conversation transition state is visible and scoped to the agent

The Agent Output screen MUST visibly distinguish continuing an existing
conversation, preparing a handoff, a ready handoff, starting a fresh
conversation, and continuing the newly bound conversation. Transient handoff
and pending-session state MUST be cleared when the selected agent changes or
the user manually changes the conversation selection.

#### Scenario: User changes agents

- **WHEN** the user selects a different agent
- **THEN** handoff and pending-new-conversation state from the previous agent
  MUST be cleared
- **AND** the new agent's most recent conversation MUST be selected when available

#### Scenario: User manually changes conversation

- **WHEN** the user changes the conversation selector during an idle state
- **THEN** any prepared handoff or pending new-conversation binding MUST be cancelled
- **AND** the continuity indicator MUST describe the newly selected choice
