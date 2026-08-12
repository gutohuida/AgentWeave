# spec-chat-session

## MODIFIED Requirements

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

## ADDED Requirements

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
