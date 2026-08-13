# spec-document-authority

## ADDED Requirements

### Requirement: A specification turn is announced with the turn, not only before it

Where a specification document is open, the Hub SHALL state the governing procedure in the turn's
own prompt, alongside the operator's message, in addition to the canonical context.

The canonical context is assembled and read before the operator's message exists, and is weighed
once, generally. A competing procedure the agent already holds is matched against the operator's
own words at the moment they arrive. Delivering the countermeasure only as standing context puts it
in a different channel from the thing it competes with, and it loses: with the phase block, the
precedence statement, the conversational floor and the tool list all verified present in the
delivered context, an agent announced it would use a different workflow, ran a questionnaire the
floor had just forbidden, and invented answers to questions it had asked and not received.

The statement SHALL name no particular product, for the same reason the canonical one does not. It
SHALL be short: it competes for attention rather than explaining, and the explanation already exists
in the context.

Where the document is in the exploring phase it SHALL also direct the agent to interview in that
reply and stop, and SHALL forbid answering its own unanswered questions. A question asked in prose
does not block the turn the way a structured question does, so nothing but the instruction prevents
an agent proceeding on invented answers.

The prompt notice MUST NOT be merged into the operator's message as recorded. What the operator said
is a durable record, and it must not come to contain something they did not say.

A turn with no document open SHALL carry no such statement.

#### Scenario: The turn prompt names the governing procedure

- **WHEN** a run is triggered with a specification document open
- **THEN** the prompt delivered with the operator's message states that the Hub's procedure governs
  and that no other specification workflow applies

#### Scenario: The exploring phase is told to interview and stop

- **WHEN** a run is triggered with a document in the exploring phase
- **THEN** the prompt directs the agent to interview in that reply and stop for the operator's answer
- **AND** directs it not to answer its own unanswered questions

#### Scenario: The operator's recorded message is unchanged

- **WHEN** a turn carries the notice
- **THEN** the message stored for that turn is what the operator wrote, without it

#### Scenario: An ordinary turn carries nothing

- **WHEN** a run is triggered with no specification document open
- **THEN** the prompt carries no specification notice

#### Scenario: A later phase is not told to interview

- **WHEN** a run is triggered with an approved document open
- **THEN** the prompt names how to write the document but does not direct an interview
