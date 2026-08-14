# agent-context-onboarding

## ADDED Requirements

### Requirement: A turn bound to a task names the specification that task implements

The system SHALL name, in the turn context, the specification document a bound task implements, and SHALL say how to read it.

An agent given a task and no document path cannot reach the thing it is supposed to build against.
It will guess paths, fail, and fall back to whatever summary it was handed — which is how an
implementation quietly stops matching what was approved.

The wording SHALL treat the document as what the work implements, not as something the operator
happens to be looking at. The two are different claims, and the second one tells an agent not to act
on it.

The system SHALL NOT present a task-derived document as an instruction to author a specification. A
turn spent writing a document instead of implementing one is worse than a turn with no document at
all.

Where the operator is also viewing that same document, the system SHALL render one statement rather
than two. Saying the same thing twice in two framings invites the agent to pick the weaker one.

#### Scenario: A task-bound turn names its document

- **WHEN** an agent's turn is bound to a task that implements a document
- **THEN** the context names that document
- **AND** says how to read it

#### Scenario: The framing is to implement, not to observe

- **WHEN** the context names a document a task implements
- **THEN** it does not describe it as what the operator is viewing

#### Scenario: A task-derived document does not start an authoring turn

- **WHEN** the document was derived from the bound task rather than opened by the operator
- **THEN** the turn is not framed as a specification-authoring turn

#### Scenario: One statement when both would name the same document

- **WHEN** the operator is viewing the same document the bound task implements
- **THEN** the context names it once

### Requirement: An agent granted a capability is told it has it

The system SHALL tell an agent, in its turn context, which operator-conferred capabilities it holds.

A capability an agent does not know it has is one it does not use. An agent that guesses instead is
refused in the middle of a turn, having already spent it.

#### Scenario: A granted agent is told

- **WHEN** an agent has been granted evidence acceptance
- **THEN** its turn context says so

#### Scenario: An ungranted agent is not told it has it

- **WHEN** an agent has not been granted evidence acceptance
- **THEN** its turn context does not claim it has
