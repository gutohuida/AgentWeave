## MODIFIED Requirements

### Requirement: Handoff checkpoints the selected conversation

The `Handoff` action MUST cause the Hub to produce a checkpoint for the selected conversation, and
MUST NOT depend on the agent invoking a checkpoint workflow of its own.

The prior wording required the action to *"append a checkpoint request"* instructing the agent to
*"invoke its checkpoint workflow with reason `pre_handoff`"* and preserve state *"in the configured
durable checkpoint location"*. No such workflow is installed into any project, and the location lies
outside the agent's own working directory, so the instruction was unsatisfiable on both counts.
Where an artifact appeared at all it came from a skill belonging to the operator's environment
rather than to AgentWeave.

The content and verification of the checkpoint are governed by `conversation-checkpoint`. This
requirement governs only the action that requests one.

The action MAY request brief notes from the agent, but the checkpoint MUST be produced whether or
not the agent responds.

#### Scenario: User requests a handoff

- **WHEN** an automatically managed agent has an existing conversation selected
- **AND** the user activates `Handoff`
- **THEN** the Hub produces a checkpoint for that conversation
- **AND** the workspace is armed to create one successor conversation

#### Scenario: Handoff is being prepared

- **WHEN** the checkpoint is being produced
- **THEN** the UI indicates that the handoff is being prepared
- **AND** handoff controls remain disabled until it settles
- **AND** unrelated running-state logic does not disable ordinary queued composer input

#### Scenario: The agent does not cooperate

- **WHEN** the agent is asked for notes and does not answer, refuses, or returns unusable notes
- **THEN** the checkpoint is still produced
- **AND** the handoff is not reported as failed for that reason alone

#### Scenario: Agent cannot be triggered automatically

- **WHEN** the agent's runner is configured as manual
- **THEN** the `Handoff` action is disabled
- **AND** the UI explains that handoff requires an automatically managed runner

### Requirement: The next conversation resumes the durable handoff

After a handoff is ready, the next user message MUST create exactly one unbound successor
conversation, and the Hub MUST deliver the checkpoint into it rather than instructing the successor
to locate it.

The prior wording required the successor's prompt to instruct the new provider session to *"read the
newest checkpoint for its agent"* at a stated path. Both paths named were wrong: neither existed,
and one of the two runtimes recovered only by abandoning the instruction and searching its whole
working directory. The other appeared to succeed only because it had earlier written to the same
incorrect location, so two errors composed into a working round trip.

The checkpoint is delivered as conversation-scoped queued input. It MUST NOT be delivered through
the agent-scoped canonical context, which writes one file per agent and therefore cannot carry
something belonging to one successor conversation.

The successor's prompt MUST NOT instruct the agent to locate a checkpoint on the filesystem.

#### Scenario: First message after handoff

- **WHEN** the handoff is ready and the user sends the next message
- **THEN** the trigger omits `conversation_id` and returns the new successor `conversation_id`
- **AND** the checkpoint is delivered into that successor as queued input
- **AND** the user's original request remains present

#### Scenario: The successor is not asked to find anything

- **WHEN** the successor conversation receives the checkpoint
- **THEN** no instruction to read a checkpoint from a filesystem path is included

#### Scenario: Successor conversation identity is immediate

- **WHEN** the fresh trigger is accepted
- **THEN** the selector binds to its returned `conversation_id` without waiting for output
- **AND** the UI indicates that it is continuing the successor conversation

#### Scenario: Messages after the resumed handoff

- **WHEN** the user sends another message in the successor conversation
- **THEN** the trigger carries that successor `conversation_id`
- **AND** the checkpoint is not delivered again
- **AND** no further conversation is created

### Requirement: Agent Output distinguishes continuation, fresh start, and handoff

The conversation workspace MUST present existing AgentWeave conversations as resumable choices, a
`New conversation (start fresh)` choice that deliberately creates a new unbound conversation, and a
`Handoff` action that produces a checkpoint before creating a successor conversation.

The prior wording described handoff as preserving context *"through a durable checkpoint"* written
by the agent. Production of the checkpoint is now the Hub's, so the action is a request rather than
an instruction relayed to the agent.

Readiness MUST reflect that a checkpoint exists and passed verification. It MUST NOT be derived from
the agent's run ending, which reported success for a run that produced nothing and returned a
question to the operator.

The normal picker and continuity controls MUST use `conversation_id` and MUST NOT use provider
session IDs as conversation labels or values. The agent-detail header MUST NOT present the legacy
`Compact` and `Reset` actions as primary conversation controls.

#### Scenario: Existing conversation is selected

- **WHEN** the user selects an existing conversation and sends a message
- **THEN** the trigger includes its exact `conversation_id`
- **AND** the server derives provider continuation from that conversation's binding

#### Scenario: User starts fresh without a handoff

- **WHEN** the user selects `New conversation (start fresh)` and sends a message
- **THEN** the trigger omits `conversation_id` so the server creates one synchronously
- **AND** no checkpoint is delivered into it

#### Scenario: Readiness follows the checkpoint, not the run

- **WHEN** a run ends without a verified checkpoint having been produced
- **THEN** the handoff is not reported as ready

#### Scenario: Legacy context actions are absent

- **WHEN** the agent conversation renders
- **THEN** `Compact` and `Reset` buttons do not appear in its primary header
- **AND** durable transitions are initiated through `Handoff`
