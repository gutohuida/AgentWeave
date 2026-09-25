## ADDED Requirements

### Requirement: Approval reports what it created and what it could not

Every approval of a change document SHALL record, with the document, a report of what the approval
did: the tasks it created, the tasks it did not create because existing work already served their
requirements, the declared dependencies it could not honour and why, whether creating the board failed
entirely and why, and whether a flow was created, naming it, or why not. The report SHALL be returned
when the document is read and shown on the document.

A failure to create the board SHALL NOT undo the approval, and SHALL be distinguishable in the report
from a document that declared no tasks.

#### Scenario: A total failure to create the board is reported, not hidden

- **GIVEN** a proposed document whose tasks cannot be created
- **WHEN** the operator approves it
- **THEN** the document is approved
- **AND** its report says the board could not be created and why, rather than that no tasks were declared

#### Scenario: A dependency not honoured is named

- **GIVEN** an approved document one of whose tasks depends on a key no task carries
- **WHEN** the operator reads the document
- **THEN** its report names the task, the dependency and the reason it was not honoured

#### Scenario: A document with no flow offers to start one from its report

- **GIVEN** an approved document whose report says no flow was created
- **WHEN** the operator reads the document
- **THEN** the report offers to start a flow for it
