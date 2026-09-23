## ADDED Requirements

### Requirement: An exploration started with a conversation exists only if that conversation's first input was accepted
The Hub SHALL create the specification document that an operator's first message starts, in the same request that accepts that message, and SHALL leave no document, row or file behind when that request is refused.

The operator arms an exploration before the first message of a new conversation. The document has
to exist before that message's turn, because the turn's context is what tells the agent it is
exploring. If the document is created by a separate earlier request, every refused send leaves one
empty placeholder in the repository and in the specification list, for a turn that never ran. A
retrying operator collects one per attempt.

The composer SHALL ask for the exploration in the request that sends the message, and SHALL NOT
create the document itself. The Hub SHALL create the document only after every refusal it can
answer before queueing the message. It SHALL create it together with the conversation and the
queued message. Where the message is then refused before any turn runs, the Hub SHALL remove the
document it created for that request.

The removal SHALL apply only to a document the refused request itself created, which is still
exploring, carries no change after its creation, and no task or loop names. It SHALL NOT be
reachable as a way to delete any other document.

Where the document cannot be created, the Hub SHALL refuse the message and say why. It SHALL NOT
start the conversation without it, because an exploration's first turn without its document is the
failure the control exists to prevent. The composer SHALL keep the operator's text when the send is
refused.

Input that is accepted and queued, and later given up after repeated delivery failures, is outside
this requirement. The operator was told it was accepted, and the document is retired through its
phase like any other.

#### Scenario: A send refused before anything is queued
- **WHEN** the operator arms an exploration and sends a first message to an archived agent
- **THEN** the request SHALL be refused with the reason
- **AND** no specification document row SHALL exist for it
- **AND** no file SHALL have been written under `spec/`

#### Scenario: A send refused by the dispatch
- **WHEN** the operator arms an exploration and the first message is queued and then refused by its dispatch before any turn runs
- **THEN** the request SHALL be answered with the refusal
- **AND** the document created for that request SHALL no longer exist, as a row or as a file
- **AND** subscribers SHALL be told the specification list changed

#### Scenario: A send that is accepted
- **WHEN** the operator arms an exploration and the first message starts a turn or is queued behind other input
- **THEN** the response SHALL name the document created for it
- **AND** that turn's context SHALL carry that document

#### Scenario: Retrying after a refusal
- **WHEN** the operator's armed send is refused three times and then accepted
- **THEN** exactly one specification document SHALL exist for those four sends

#### Scenario: The document cannot be created
- **WHEN** the operator arms an exploration and the Hub cannot mint a path for the document
- **THEN** the send SHALL be refused, naming why
- **AND** no conversation SHALL be started
- **AND** the composer SHALL still hold the operator's text

#### Scenario: A document someone has changed is not removed
- **WHEN** a document created for a send has been written to after its creation, or has left `exploring`, by the time that send's dispatch refusal is handled
- **THEN** the Hub SHALL leave the document in place
