## ADDED Requirements

### Requirement: Approval reports what it created and what it could not

Every approval of a document SHALL record, with the document, a report of what the approval did: the
tasks it created, the tasks it did not create because existing work already served their
requirements, the declared dependencies it could not honour and why, whether creating the board failed
entirely and why, and whether a flow was created, naming it, or why not. For a document that is not a
change document, the report SHALL say that only a change document declares how it will be built. The report SHALL be returned
when the document is read and shown on the document. Where the document was approved more than once,
the report returned SHALL be the one recorded last, even when two were recorded at the same instant.
Where it reports that no flow was created, the
document SHALL point from the report to the document's one control for starting a flow, and SHALL do
so only while no unarchived flow declares the document. The report MUST NOT carry a second control
for the same action.

A failure to create the board SHALL NOT undo the approval, and SHALL be distinguishable in the report
from a document that declared no tasks. A failure part-way through SHALL leave none of the tasks that
attempt created, so the board never holds half a decomposition the report does not list.

#### Scenario: A total failure to create the board is reported, not hidden

- **GIVEN** a proposed document whose tasks cannot be created
- **WHEN** the operator approves it
- **THEN** the document is approved
- **AND** its report says the board could not be created and why, rather than that no tasks were declared
- **AND** none of the tasks created before the failure remain

#### Scenario: A dependency not honoured is named

- **GIVEN** an approved document one of whose tasks depends on a key no task carries
- **WHEN** the operator reads the document
- **THEN** its report names the task, the dependency and the reason it was not honoured

#### Scenario: A document with no flow offers to start one beside its report

- **GIVEN** an approved change document whose report says no flow was created, and no flow declares it
- **WHEN** the operator reads the document
- **THEN** the document offers to start a flow, once, beside the report
- **AND** the report points to that offer and carries no start control of its own

#### Scenario: The offer is withdrawn once a flow exists

- **GIVEN** an approved document whose report says no flow was created
- **WHEN** the operator starts a flow for it and reads the document again
- **THEN** the report still says no flow was created at approval
- **AND** the document no longer offers to start one, and the report no longer points to an offer

#### Scenario: The newest report is the one returned when two share a time

- **GIVEN** a document approved twice, both reports recorded at the same instant
- **WHEN** the operator reads the document
- **THEN** the report returned is the one recorded second
