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

### Requirement: Evidence is footprinted against the work it describes

An implementation footprint SHALL be captured from the working tree that holds the work the evidence is about, not from a fixed location, and SHALL name the commit that contains that work.

Evidence recorded by an agent SHALL be footprinted from that agent's own checkout where the system
has provisioned one. Evidence recorded by the operator SHALL be footprinted from the project's own
checkout. Agents are given isolated checkouts on their own branches, so a footprint taken from the
project directory names whatever the operator's checkout is on and never names the agent's work.

Determining whether an agent has a checkout SHALL be answered by the version control system, not by
the presence of a directory. A version control command run inside a directory the system does not
track answers about the enclosing repository instead, so an abandoned or partially created directory
would otherwise produce the project's own commit while appearing to have been checked.

Establishing the footprint SHALL NOT create a checkout that does not already exist.

Where no checkout for the agent exists, or the project is not under version control, the footprint
SHALL fall back to the project's own directory rather than failing.

Where the system commits an agent's work after the turn that produced it, the footprints that turn
recorded SHALL be re-pointed at the resulting commit. Evidence is recorded while the work is still
uncommitted, so the commit named at that moment is necessarily the one the turn started from — it
does not contain the work, and on a new project it is frequently already on the main line, so the
evidence reads as already integrated. Correcting the record after the commit exists is the only
point at which the right answer is knowable.

Re-pointing SHALL apply to every piece of evidence the turn recorded, whatever decision has since
been taken on it. The stored commit is a fact about where the work is, not a judgement about the
work; leaving a decided piece of evidence pointing at a commit that does not contain the work would
make what gets merged depend on how quickly it was reviewed.

Re-pointing SHALL re-answer whether the work has reached the main line, and SHALL be free to answer
that it has not. It concerns a different commit from the one first recorded, so an answer carried
over from the old commit would be an assertion about work that was never examined.

Re-pointing SHALL establish a footprint for evidence that has none.

#### Scenario: An agent's evidence names the agent's own commit

- **WHEN** an agent records evidence while its checkout holds work not present in the project's
  checkout
- **THEN** the footprint names the agent's branch and the commit in that checkout
- **AND** the footprint does not name the project checkout's commit

#### Scenario: The operator's evidence names the project's checkout

- **WHEN** the operator records evidence
- **THEN** the footprint names the project checkout's branch and commit

#### Scenario: A directory that is not a tracked checkout is not treated as one

- **WHEN** an agent records evidence and a directory exists at the agent's checkout location that
  version control does not track as that agent's checkout
- **THEN** the footprint falls back to the project's own directory
- **AND** no error is raised

#### Scenario: Recording evidence creates no checkout

- **WHEN** an agent with no provisioned checkout records evidence
- **THEN** the footprint falls back to the project's own directory
- **AND** no checkout is created

#### Scenario: Evidence recorded mid-turn names the commit the turn produced

- **WHEN** an agent records evidence for work it has not yet committed
- **AND** the system commits that work when the turn ends
- **THEN** the evidence names the commit the system made
- **AND** it does not name the commit the turn started from

#### Scenario: Evidence already decided is corrected too

- **WHEN** a turn's evidence has been accepted before the turn's work was committed
- **THEN** the accepted evidence names the commit containing the work
- **AND** the decision recorded against it is unchanged

#### Scenario: Correcting the commit re-answers integration

- **WHEN** a turn's evidence is re-pointed at a commit that has not reached the main line
- **THEN** the evidence reports that the work has not reached the main line
- **AND** an earlier answer of reached is not carried over

### Requirement: Whether work has reached the main line is re-answered

The recorded answer to whether a footprint has reached the project's main line SHALL be re-evaluated
after work is integrated, and SHALL NOT remain fixed at the value observed when the evidence was
recorded.

Work is demonstrated before it is integrated, so an answer captured at that moment is necessarily
"not yet" for every piece of agent evidence. Left unrevised, a requirement would report as
unintegrated permanently, including immediately after its work was merged.

Re-evaluation SHALL consider the project's configured main branch where one is set, in preference to
any inferred name.

Re-evaluation SHALL be bounded, and SHALL revise only those answers that changed.

#### Scenario: Integration updates the recorded answer

- **WHEN** a requirement's work is integrated into the project's main branch
- **THEN** coverage reports that requirement as integrated
- **AND** it did not report so before the integration

#### Scenario: Other work on the same branch is re-answered too

- **WHEN** integrating one requirement's commit also brings an earlier commit on the same branch into
  the main line
- **THEN** the earlier work's recorded answer is revised as well

### Requirement: Drift is assessed against the line of work a footprint names

Drift SHALL be assessed by comparing a footprint against the line of work it names, and SHALL NOT be
assessed by comparing every footprint against a single location.

Comparing an agent's footprint against the project's main line would report every file that agent
added as a change, making every demonstrated requirement a drift candidate. That the work is not on
the main line is already reported as an integration answer; raising it again as drift asks the
operator one question in two vocabularies.

A footprint that names no line of work, or names one that no longer exists, SHALL raise nothing.
Being unable to tell is not evidence of drift.

Footprints of different kinds SHALL be compared against their own kind of observation.

#### Scenario: Movement on the main line is not drift for work on a branch

- **WHEN** the main branch changes and an agent's demonstrated work is unchanged
- **THEN** no drift candidate is raised for that work

#### Scenario: Movement on the branch is drift

- **WHEN** the branch a footprint names changes after the evidence was accepted
- **THEN** a drift candidate is raised

#### Scenario: A vanished branch raises nothing

- **WHEN** the branch a footprint names no longer exists
- **THEN** no drift candidate is raised
- **AND** no error is reported

### Requirement: A renamed document carries its new subject

Where a document is renamed to reflect its subject, that subject SHALL become the document's title.

A document is renamed precisely because its subject became clear. Leaving the previous title in place
means every surface that lists documents shows a name contradicting the document's own location until
some later save happens to correct it.

#### Scenario: Renaming updates the title

- **WHEN** a document is renamed to a new subject
- **THEN** its title is that subject
- **AND** its path reflects that subject

### Requirement: A declared task can state the name the board shows

A document declaring a task SHALL be able to state that task's title, and the system SHALL use it when the task is created.

A declared task carries a description of the work — a sentence of intent, written to be read in the
document. A board shows names. Deriving one from the other produces a title that is the whole
sentence, which is not a name, and a board of them cannot be scanned.

Where no title is declared, the system SHALL derive one, and SHALL keep it short enough to read as a
name. A derived title SHALL NOT end mid-word: a truncation that splits a word reads as a defect in
the board rather than as an abbreviation.

A description short enough to serve as a name SHALL be used unchanged. Shortening what is already
short would be a change with no reader.

#### Scenario: A declared title is used

- **WHEN** a document declares a task with a title
- **AND** the document is approved
- **THEN** the created task carries that title

#### Scenario: A title is derived when none is declared

- **WHEN** a declared task states only its description
- **THEN** the created task carries a title derived from it
- **AND** that title is short enough to read as a name

#### Scenario: A derived title does not split a word

- **WHEN** a description is too long to serve as a title
- **THEN** the derived title ends on a word boundary

#### Scenario: A short description is kept as-is

- **WHEN** a declared task's description is already short enough to be a name
- **THEN** the created task's title is that description

