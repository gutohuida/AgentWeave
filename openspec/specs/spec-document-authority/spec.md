# spec-document-authority

## Purpose

Where a specification document lives, who may write it, how its requirements are identified, what
phase it is in, and who may move it between phases.

The document is the file in the project's working directory — there is no cached copy and nothing
to reconcile. An agent submits a structured payload and the Hub renders the markup, so the format is
a schema the agent cannot violate rather than a contract it is asked to honour. Phase is Hub-owned:
the status in the file is a copy for whoever reads it, and approval is a decision only the operator
can take.

## Requirements

### Requirement: A specification document is a file in the project working directory

Specification documents SHALL be stored as files beneath the project's working directory and read
from there. The Hub MUST resolve every document path through the project workspace, which refuses
absolute paths, traversal segments, control characters, and symlink escapes.

The Hub SHALL NOT maintain a second copy of a document's content. There MUST be no endpoint by which
a client pushes document content to the Hub, and no stored snapshot of another source's inventory.

#### Scenario: A document is read from the working directory

- **WHEN** the operator opens a specification document in a registered project
- **THEN** its content is read from the project's working directory at request time
- **AND** no cached copy is consulted

#### Scenario: A document path that escapes the project is refused

- **WHEN** any caller supplies a document path that is absolute, contains a traversal segment, or
  resolves outside the project workspace
- **THEN** the request is refused
- **AND** no file outside the workspace is read or written

#### Scenario: The container deployment confines documents to the mounted root

- **WHEN** the Hub runs with a configured workspace root and a project's directory lies beneath it
- **THEN** documents resolve normally within that root
- **AND** a path outside the root is refused rather than guessed at

### Requirement: The agent submits a structured payload and the Hub renders the document

An agent SHALL author a specification by submitting a structured payload through a tool. The Hub MUST
validate the payload and render the document itself.

An agent MUST NOT write specification markup directly, and the Hub MUST NOT accept agent-authored
markup as a document's content.

When a payload fails validation the Hub SHALL refuse it with an error naming the offending field, and
MUST NOT write a partial document.

#### Scenario: A valid payload becomes a rendered document

- **WHEN** an agent submits a payload that satisfies the schema
- **THEN** the Hub renders the document and writes it to the project working directory
- **AND** the rendered markup is produced by the Hub, not supplied by the agent

#### Scenario: An invalid payload is refused without a partial write

- **WHEN** an agent submits a payload that omits a required field or violates a declared constraint
- **THEN** the submission is refused with an error identifying the field
- **AND** the document on disk is unchanged

#### Scenario: Agent-authored markup is not a document

- **WHEN** an agent writes specification markup to the working directory by any other means
- **THEN** the Hub does not treat that content as an authored document
- **AND** the document's authority remains the last validated payload

### Requirement: The payload contract is versioned and forward compatible

Every payload SHALL declare a schema version. The Hub MUST preserve fields it does not recognise
across a read and re-write of the same document, and MUST re-emit them unchanged.

The contract MUST NOT be declared final while gate and traceability behaviour has not stated its
requirements on it.

#### Scenario: An unrecognised field survives a round trip

- **WHEN** a document containing fields the current schema version does not define is read and
  written again
- **THEN** those fields are present and unchanged in the result
- **AND** no validation error is raised on their account

#### Scenario: A payload without a schema version is refused

- **WHEN** a payload omits its schema version
- **THEN** the submission is refused
- **AND** the error names the missing version rather than a downstream field

### Requirement: The Hub mints requirement identifiers and they are stable

The Hub SHALL assign every requirement its identifier. An identifier supplied by an agent MUST NOT be
used.

A submission SHALL carry a **key** for each requirement: a handle, unique within the document, by
which the Hub correlates a requirement across submissions. A key MUST NOT be used as an identifier
and MUST NOT appear in any link.

An identifier SHALL remain attached to the requirement whose key it was minted for, regardless of
changes to that requirement's text, its position in the document, or the schema version the document
is rendered under. An identifier that has been used MUST NOT be reassigned to a different
requirement, including after the requirement it belonged to is removed.

Correlating by position would make inserting a requirement renumber every requirement after it, and
identifiers are what tasks and evidence point at — a renumber silently re-targets them.

#### Scenario: Rewording a requirement preserves its identifier

- **WHEN** an agent resubmits a document in which one requirement's text has changed and its key has
  not
- **THEN** that requirement keeps the identifier it already had

#### Scenario: Reordering requirements preserves their identifiers

- **WHEN** an agent resubmits a document with the same keys in a different order, or inserts a new
  requirement before an existing one
- **THEN** every previously known key keeps the identifier it already had
- **AND** only the new key receives a newly minted one

#### Scenario: An agent-supplied identifier is not honoured

- **WHEN** a submitted payload contains an identifier for a requirement
- **THEN** the Hub assigns its own identifier
- **AND** the submitted value does not appear as that requirement's identity

#### Scenario: A removed requirement's identifier is not recycled

- **WHEN** a requirement is removed and a new requirement is added in a later submission
- **THEN** the new requirement receives an identifier that has never been used in this document

### Requirement: A document has a phase and the Hub owns its transitions

Every specification document SHALL have a phase. The phases are `exploring`, `proposed`, and
`approved`.

A transition SHALL occur only when its entry conditions hold, and the Hub MUST evaluate those
conditions itself rather than accepting an assertion that they hold. A document created by the
operator's entry point SHALL start in `exploring`.

#### Scenario: A document is created in the exploring phase

- **WHEN** the operator creates a specification document
- **THEN** the document exists with phase `exploring`
- **AND** it is addressable before any requirement has been written

#### Scenario: A transition to proposed requires a valid document

- **WHEN** a transition to `proposed` is attempted for a document whose payload does not validate
- **THEN** the transition is refused
- **AND** the failing checks are reported

#### Scenario: A phase claimed in content does not move the document

- **WHEN** a submitted payload states a phase
- **THEN** the document's phase is unchanged by that statement
- **AND** the phase remains whatever the recorded transitions have made it

### Requirement: Approval is the operator's decision and no agent can express it

The transition to `approved` SHALL be recorded only from an operator action. There MUST be no tool
argument, payload field, or document content by which an agent can approve a document or cause it to
become approved.

#### Scenario: An agent cannot approve a document

- **WHEN** an agent attempts by any available means to move a document to `approved`
- **THEN** the document is not approved
- **AND** the attempt is refused

#### Scenario: An operator approval is recorded with its actor

- **WHEN** the operator approves a proposed document
- **THEN** the document's phase becomes `approved`
- **AND** the transition records that the operator made it, and when

### Requirement: Document validity is checked by the Hub, not asserted by its author

The Hub SHALL evaluate a document's structural and consistency checks itself. A check MUST NOT be
satisfied by the author reporting that it passed.

At minimum the Hub SHALL refuse a transition to `proposed` when: a requirement is referenced by no
acceptance criterion; a requirement is referenced by no task; a task references no requirement; a
requirement states no modal obligation; the non-goals are empty; or an unresolved clarification
marker remains.

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

### Requirement: Every change to a document is recorded as an attributed event

The Hub SHALL append an event for every change to a document's content or phase. Each event MUST
record the actor, whether the change originated from an operator control or an agent submission, the
run it belongs to where one exists, and what changed.

The event history SHALL be append-only. A recorded event MUST NOT be edited or removed.

#### Scenario: An agent submission is attributed to its run

- **WHEN** an agent submits a document payload during a run
- **THEN** an event records the agent as actor, the submission as origin, and that run's identifier

#### Scenario: An operator edit is attributed to the operator

- **WHEN** the operator changes a document through a Hub control
- **THEN** an event records the operator as actor and the control as origin

#### Scenario: History cannot be rewritten

- **WHEN** any caller attempts to modify or delete a recorded event
- **THEN** the attempt is refused
- **AND** the existing history is unchanged

### Requirement: A document's digest is stored on write and divergence is reported

The Hub SHALL store a content digest for every document it writes, and a digest for each
requirement's text.

When a document on disk differs from the digest recorded for it, the Hub SHALL report the divergence
and MUST NOT resolve it. It MUST NOT overwrite the file, merge the versions, or select one on the
operator's behalf.

#### Scenario: An externally edited document is reported, not overwritten

- **WHEN** a document's content on disk no longer matches its stored digest
- **THEN** the divergence is reported to the operator
- **AND** the file is left as it is found

#### Scenario: A requirement's text digest changes when its meaning is edited

- **WHEN** a requirement's text is changed
- **THEN** the digest recorded for that requirement changes
- **AND** the digest for an unmodified requirement does not

### Requirement: The turn context states the phase and holds without a charter

The canonical turn context SHALL state which document is open, what phase it is in, and what the
agent's obligation is in that phase.

This statement MUST NOT depend on a charter. A project whose agent has no charter bound SHALL still
be able to produce a valid document.

#### Scenario: The context names the phase

- **WHEN** a run is triggered while a specification document is open
- **THEN** the turn context names the document, its phase, and the obligation that phase carries

#### Scenario: A blank charter still produces a valid document

- **WHEN** an agent with no charter bound authors a document
- **THEN** the document is subject to the same validation and the same phase conditions
- **AND** its validity does not depend on charter content

### Requirement: Document discovery covers every safe document

The Hub SHALL discover every document beneath the project's specification directory whose path is
safe, not only those in a single expected location. Nested archives, roadmaps, and system maps are
documents.

A document whose path is unsafe MUST be excluded and reported rather than silently skipped.

#### Scenario: A nested document is discovered

- **WHEN** the specification tree contains documents in nested directories
- **THEN** all of them are listed

#### Scenario: An unsafe path is excluded and reported

- **WHEN** a discovered path fails path validation
- **THEN** it is not listed as a document
- **AND** the exclusion is reported rather than passed over silently

### Requirement: Home-document selection is explicit and resilient

The document tree SHALL have an explicit home document. The Hub MUST NOT change an existing home
selection without being asked.

When no home is recorded and exactly one candidate exists, the Hub MAY record it. When there are none
or several, the Hub SHALL ask rather than choose.

#### Scenario: An existing home selection is preserved

- **WHEN** the index records a home document that still exists
- **THEN** it remains the home document

#### Scenario: An ambiguous home is asked about, not guessed

- **WHEN** no home is recorded and several candidates exist
- **THEN** the operator is asked which is home
- **AND** none is selected in the meantime

### Requirement: An unreadable or absent index degrades visibly

When the document index is absent, unreadable, or invalid, the Hub SHALL continue to list the
documents it discovered and SHALL report the index's state.

It MUST NOT present a degraded tree as a healthy one, and MUST NOT discard an index entry it cannot
explain.

#### Scenario: An invalid index still lists documents

- **WHEN** the index cannot be parsed
- **THEN** discovered documents are still listed
- **AND** the index's state is reported as invalid

#### Scenario: An unexplained entry is retained

- **WHEN** the index names a document with no file on disk and no evidence of deliberate deletion
- **THEN** the entry is retained and reported as unresolved
- **AND** it is not silently discarded

### Requirement: Document state changes refresh subscribers

A change to a document's content, phase, or index state SHALL be broadcast to the project's
subscribers, so an open surface reflects it without a manual refresh.

#### Scenario: A submitted document reaches an open surface

- **WHEN** an agent's submission is accepted
- **THEN** subscribers to that project receive an event identifying the document

#### Scenario: A phase transition reaches an open surface

- **WHEN** a document's phase changes
- **THEN** subscribers receive an event carrying the document and its new phase
