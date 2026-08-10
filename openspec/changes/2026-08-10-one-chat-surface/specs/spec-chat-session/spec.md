## ADDED Requirements

### Requirement: The specification workspace uses the one composer

The specification workspace's chat SHALL use the same composer, banner stack, and conversation
transcript as an agent conversation, and MUST NOT implement its own message input, run trigger, or
output rendering.

An operator working in the specification workspace SHALL be able to answer a permission request,
answer a question the agent asked, and see a checkpoint warning, on that surface.

A second implementation is not a styling difference. The surface it replaced could not render a
permission card, a question card, or a checkpoint banner, so an agent that asked the operator
anything from the specification workspace blocked with nothing shown — and the whole authoring flow
this capability exists to serve depends on the agent being able to ask.

#### Scenario: The agent asks the operator a question from the specification workspace

- **WHEN** an agent working in the specification workspace calls `ask_user`
- **THEN** the question is presented on that surface
- **AND** the operator's answer returns to the waiting run

#### Scenario: A tool call requires approval in the specification workspace

- **WHEN** a run started from the specification workspace is in a permission posture that routes
  decisions to the operator, and the agent attempts a tool call requiring approval
- **THEN** the approval request is presented on that surface
- **AND** the operator's decision resolves the run

#### Scenario: One trigger path

- **WHEN** a message is sent from the specification workspace
- **THEN** it goes through the same run-trigger path an agent conversation uses
- **AND** no surface-specific timeout, session-mode handling, or error vocabulary applies to it

### Requirement: The specification workspace reuses the agent's conversation

The specification workspace SHALL show the selected agent's conversation, and SHALL create one on
the first message when the agent has none.

The Hub MUST NOT record a specification-scoped conversation origin until a specification-scoped
thread has a defined scope.

`Conversation.origin` accepts a specification value that nothing produces. Producing it here would
require choosing whether such a thread belongs to a document or to a unit of specification work,
before either is defined — and the direction taken is that a thread's phase derives from the
document open in it, which makes the durable relationship a link rather than an origin value.
Recording data on an axis that is likely to be wrong is worse than recording none.

#### Scenario: First message from the specification workspace

- **WHEN** the operator sends the first message to an agent that has no conversation
- **THEN** a conversation is created by that message
- **AND** its origin is not a specification-scoped value

### Requirement: The agent is told which document the operator is viewing

When the operator has a specification document open, the Hub SHALL include that document in the
canonical turn context. When no document is open, the Hub SHALL include nothing rather than a
guessed value.

The document reference MUST NOT be added to the operator's message.

Turn context is rebuilt every turn and consumed identically by every runner, so the value tracks the
operator's navigation without being resent and without depending on the runner's own extension
format. Putting it in the message body would make a durable record of what the operator said contain
something they did not say.

#### Scenario: A document is open

- **WHEN** a run is triggered from the specification workspace with a document open
- **THEN** the canonical context for that turn names the document
- **AND** the operator's message is unchanged

#### Scenario: No document is open

- **WHEN** a run is triggered with no document open
- **THEN** the canonical context names no document
