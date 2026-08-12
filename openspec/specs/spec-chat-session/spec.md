# spec-chat-session Specification

## Purpose
The chat in the Hub's specification workspace: which surface it is, whose conversation it shows,
and what the agent is told about where the operator is looking.

It is deliberately thin. The three requirements it used to carry — session resume, a deliberate
new-session control, and a visible continuity indicator — were removed by
`2026-08-10-one-chat-surface`: each described a mechanism this surface owned, and the point of that
change is that this surface owns no mechanism. Continuity, starting fresh, and saying which of the
two will happen are all properties of the one conversation surface, governed by
`agent-conversation-workspace`.

## Requirements
### Requirement: The specification workspace uses the one composer

The specification workspace's chat SHALL use the same composer, banner stack, and conversation
transcript as an agent conversation, and MUST NOT implement its own message input, run trigger,
output rendering, or **agent selection**.

An operator working with a specification document SHALL be able to answer a permission request,
answer a question the agent asked, and see a checkpoint warning, on that surface.

A second implementation is not a styling difference. The surface this replaced could not render a
permission card, a question card, or a checkpoint banner, so an agent that asked the operator
anything blocked with nothing shown — and the authoring flow this capability exists to serve
depends on the agent being able to ask.

Agent selection is named here because removing one second implementation admitted another: the
replacement surface added its own agent picker beside the one navigation already provides. The
agent is whichever conversation the operator is in.

#### Scenario: The agent asks the operator a question while a document is open

- **WHEN** an agent calls `ask_user` in a conversation with a specification document open
- **THEN** the question is presented on that surface
- **AND** the operator's answer returns to the waiting run

#### Scenario: A tool call requires approval while a document is open

- **WHEN** a run in a conversation with a document open is in a permission posture that routes
  decisions to the operator, and the agent attempts a tool call requiring approval
- **THEN** the approval request is presented on that surface
- **AND** the operator's decision resolves the run

#### Scenario: One trigger path

- **WHEN** a message is sent with a specification document open
- **THEN** it goes through the same run-trigger path every other conversation uses
- **AND** no surface-specific timeout, session-mode handling, or error vocabulary applies to it

#### Scenario: One way to choose an agent

- **WHEN** the operator changes which agent they are working with
- **THEN** they do so through navigation
- **AND** no other surface offers a separate agent selector

### Requirement: The specification workspace reuses the agent's conversation

The specification workspace SHALL show the selected agent's conversation, and SHALL create one on
the first message when the agent has none.

Opening a specification SHALL be possible from within the conversation surface itself, without
navigating away from the conversation first. There SHALL NOT be a separate project destination for
specifications.

Reaching a specification by leaving the conversation, opening the project, and choosing a tab puts
the most-used surface in the product behind three navigations. The control that opens one belongs
where the operator already is.

The Hub MUST NOT record a specification-scoped conversation origin until a specification-scoped
thread has a defined scope.

`Conversation.origin` accepts a specification value that nothing produces. Producing it would
require choosing whether such a thread belongs to a document or to a unit of specification work,
before either is defined — and the direction taken is that a thread's phase derives from the
document open in it, which makes the durable relationship a link rather than an origin value.

#### Scenario: First message with a document open

- **WHEN** the operator sends the first message to an agent that has no conversation
- **THEN** a conversation is created by that message
- **AND** its origin is not a specification-scoped value

#### Scenario: Opening a specification from a conversation

- **WHEN** the operator uses the specification control on the conversation surface
- **THEN** they choose a document without leaving the conversation
- **AND** no separate project destination for specifications exists

### Requirement: The agent is told which document the operator is viewing

When the operator has a specification document open, the Hub SHALL include that document in the
canonical turn context, together with the phase the document is in and the obligation that phase
carries. When no document is open, the Hub SHALL include nothing rather than a guessed value.

The document reference MUST NOT be added to the operator's message.

The phase statement MUST NOT depend on a charter being bound. A charter may make the agent's work
better; it MUST NOT be what makes the agent's work valid.

Turn context is rebuilt every turn and consumed identically by every runner, so the value tracks the
operator's navigation without being resent and without depending on the runner's own extension
format. Putting it in the message body would make a durable record of what the operator said contain
something they did not say. The phase belongs in the same place for the same reason, and because a
procedure the Hub states each turn is one the agent cannot be working from a stale copy of.

#### Scenario: A document is open

- **WHEN** a run is triggered from the specification workspace with a document open
- **THEN** the canonical context for that turn names the document, its phase, and what the agent is
  expected to do in that phase
- **AND** the operator's message is unchanged

#### Scenario: No document is open

- **WHEN** a run is triggered with no document open
- **THEN** the canonical context names no document

#### Scenario: The phase statement does not depend on a charter

- **WHEN** a run is triggered with a document open and no charter bound to the agent
- **THEN** the canonical context still names the document, its phase, and the obligation

### Requirement: A specification document opens beside a conversation

A specification document SHALL open as a panel within the conversation view, alongside the
conversation rather than in a separate screen, and the operator SHALL be able to close it and
recover the full width for the conversation.

The open document SHALL be part of the addressed destination, so that reloading or sharing the
location restores both the conversation and the document open in it.

A document panel available in any conversation is what makes the relationship between a thread and
a document a link the operator makes, rather than a category the thread was born into — which is
what "a thread's phase derives from the document open in it" requires. A separate specification
screen forces the opposite: a thread is a specification thread because of where it was opened.

#### Scenario: Opening a document from a conversation

- **WHEN** the operator opens a specification document while in a conversation
- **THEN** the document is shown beside that conversation
- **AND** the conversation remains usable without leaving it

#### Scenario: The location survives a reload

- **WHEN** the operator reloads with a document open beside a conversation
- **THEN** the same conversation and the same document are open

#### Scenario: Closing the document

- **WHEN** the operator closes the document panel
- **THEN** the conversation occupies the full available width
- **AND** no specification navigation remains on screen

### Requirement: The conversation surface is legible at every width it is offered at

Every control the conversation surface presents SHALL be fully within its container and legible at
every width the surface can be shown at, and no two interactive elements SHALL overlap.

A control MUST NOT be removed from the surface as it narrows. Where space is insufficient, controls
SHALL wrap or abbreviate their value while keeping what they control identifiable.

Where a document is shown beside the conversation, the boundary between them SHALL be the
operator's: each pane SHALL be bounded only by a minimum below which it stops being usable, and
neither SHALL carry a maximum that prevents the other from being made smaller.

The surface was previously rendered in a pane far narrower than it was designed for, and its control
row overflowed its container — the permission control, whose current value must be readable before
sending, was clipped mid-word. Presence in the document is not evidence of this requirement being
met; the check is geometric.

#### Scenario: The surface is shown in a narrowed panel

- **WHEN** the conversation surface is shown at its minimum supported width
- **THEN** every control is within its container and none is clipped
- **AND** no interactive element overlaps another

#### Scenario: The permission posture stays readable

- **WHEN** the conversation surface narrows
- **THEN** the permission control still states which posture the run will use

#### Scenario: The operator sizes the boundary

- **WHEN** the operator moves the boundary between the conversation and an open document
- **THEN** either pane can be made the larger one
- **AND** each stops only at the width below which it is no longer usable

### Requirement: The operator can start an exploration by creating a document

The operator SHALL be able to create an empty specification document from the conversation surface,
and that document SHALL open beside the conversation in the `exploring` phase.

Creating the document MUST NOT require naming its requirements, choosing a template, or answering
anything beyond what identifies the document.

An exploration is declared, not detected. The Hub MUST NOT infer that a conversation is an
exploration from its content.

#### Scenario: An exploration begins with an empty document

- **WHEN** the operator starts an exploration from a conversation
- **THEN** an empty document is created in the `exploring` phase
- **AND** it opens beside that conversation

#### Scenario: The document is the subject of every later transition

- **WHEN** the operator later proposes or approves
- **THEN** the subject of that action is the document created at the start
- **AND** no separate step is needed to turn the conversation into a document

#### Scenario: A conversation is not classified as an exploration

- **WHEN** a conversation discusses a change without the operator creating a document
- **THEN** it has no phase
- **AND** the Hub does not treat it as an exploration
