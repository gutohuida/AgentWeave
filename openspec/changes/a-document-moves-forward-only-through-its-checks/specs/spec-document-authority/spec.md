## MODIFIED Requirements

### Requirement: Document validity is checked by the Hub, not asserted by its author

The Hub SHALL evaluate a document's structural and consistency checks itself. A check MUST NOT be
satisfied by the author reporting that it passed.

At minimum the Hub SHALL refuse a transition to `proposed` when: a requirement is referenced by no
acceptance criterion; a requirement is referenced by no task; a task references no requirement; a
requirement states no modal obligation; the non-goals are empty; or an unresolved clarification
marker remains.

The Hub SHALL apply the same checks to a transition to `approved`. A proposed document can still be
written, and a document can be adopted at `proposed` without having been checked, so having been
proposed does not establish that a document is complete when it is approved. The one exception is
an import naming a document that is no longer approved: at approval it SHALL be preserved and
reported by materialisation, as task-dependencies requires, rather than refuse the approval.

The checks SHALL apply on every operation that moves a document to `proposed` or `approved`, and
SHALL be enforced at the point the Hub actually changes a document's phase, not at whichever surface
a caller reaches it through. A second operation that moves the document without them is a way around
them, whichever surface offers it, and a check made per surface only survives until another surface
is added.

An operation that reports what blocks a document from `proposed` SHALL report every blocker in one
answer, including that exploration has not been closed. A caller told of some blockers and then
refused on another makes a round trip the answer could have spared it.

A move the phase map forbids, or one the caller may not make, SHALL be refused as such and not
reported as incompleteness.

#### Scenario: An orphan requirement blocks the transition

- **WHEN** a document contains a requirement that no acceptance criterion references
- **THEN** the transition to `proposed` is refused
- **AND** the offending requirement is named

#### Scenario: An orphan task blocks the transition

- **WHEN** a document contains a task that references no requirement
- **THEN** the transition to `proposed` is refused
- **AND** the offending task is named

#### Scenario: An unresolved clarification blocks the transition

- **WHEN** a document still carries a clarification marker that has not been resolved
- **THEN** the transition to `proposed` is refused

#### Scenario: The phase operation cannot propose an incomplete document

- **WHEN** the operator moves an incomplete document to `proposed` through the phase operation rather than the propose operation
- **THEN** the move is refused with every finding named
- **AND** the document stays in `exploring`

#### Scenario: An incomplete proposed document cannot be approved

- **WHEN** a proposed document is edited so that a requirement has no task, and the operator approves it
- **THEN** approval is refused with the finding named
- **AND** no task is created from the document

#### Scenario: The checks hold regardless of caller

- **WHEN** any code path calls the Hub's phase transition operation to move an incomplete document to `proposed` or `approved`
- **THEN** the move is refused with every finding named, because the checks are made there and not duplicated per caller

#### Scenario: Proposing lists an open exploration with the other blockers

- **WHEN** the operator proposes an incomplete document whose exploration has not been closed
- **THEN** the answer names the open exploration and every completeness finding together
- **AND** the document stays in `exploring`

#### Scenario: An illegal move is not reported as incompleteness

- **WHEN** a transition the phase map does not allow is attempted on an incomplete document
- **THEN** it is refused as an illegal transition

#### Scenario: An import reopened after the proposal does not block approval

- **WHEN** a complete document is proposed while the document it imports from is approved, that document is then reopened, and the operator approves the first
- **THEN** approval succeeds
- **AND** the import is preserved and reported as naming a document that is not approved
