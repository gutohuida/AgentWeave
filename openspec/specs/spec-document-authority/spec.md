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

The turn context SHALL further state that the Hub's procedure is the one that governs the open
document, and that no other specification workflow, skill, command, or tool applies to it —
including one installed on the machine the runner is running on, and including one the agent has
used before. Stating how to author a document does not settle which authority governs it, and a
procedure the agent already has, whose trigger matches the operator's own phrasing, is evaluated
against that phrasing before any standing context is weighed.

The Hub SHALL NOT detect, enumerate, or disable a competing procedure in order to satisfy this.
Doing so requires reading the private layout of other tools and cannot cover a runner that does not
exist yet. The context SHALL instead direct the agent to raise a competing workflow with the
operator rather than follow it silently: the tool belongs to the operator, and an agent told only
what not to do has nowhere to put what it found.

This statement SHALL be part of the code-owned floor rather than the charter, and SHALL appear only
where a document is open. A project with no charter bound is the case most exposed — mechanism
without judgement — so precedence carried by a charter would be absent exactly where it is needed
most.

#### Scenario: The context names the phase

- **WHEN** a run is triggered while a specification document is open
- **THEN** the turn context names the document, its phase, and the obligation that phase carries

#### Scenario: A blank charter still produces a valid document

- **WHEN** an agent with no charter bound authors a document
- **THEN** the document is subject to the same validation and the same phase conditions
- **AND** its validity does not depend on charter content

#### Scenario: The context states which procedure governs

- **WHEN** a run is triggered while a specification document is open
- **THEN** the turn context states that no specification workflow other than the Hub's applies to
  that document
- **AND** it does so without naming a particular product, so a workflow it has never heard of is
  covered by the same statement

#### Scenario: A competing workflow is raised rather than followed

- **WHEN** the agent has another specification workflow available to it
- **THEN** the turn context directs it to tell the operator what it found
- **AND** to author the document through the Hub regardless

#### Scenario: Precedence does not depend on a charter

- **WHEN** a run is triggered with a document open and no charter bound
- **THEN** the precedence statement is present

#### Scenario: A turn with no document open is unchanged

- **WHEN** a run is triggered with no specification document open
- **THEN** the turn context makes no statement about specification procedure

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
reply and stop, SHALL forbid answering its own unanswered questions, and SHALL direct it to rename
the document as soon as the interview establishes what the document is about. A question asked in
prose does not block the turn the way a structured question does, so nothing but the instruction
prevents an agent proceeding on invented answers. The rename is likewise an action taken on
information acquired during a particular turn, which is why it is stated with the turn rather than
only in standing context.

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

#### Scenario: The exploring phase is told to name the document

- **WHEN** a run is triggered with a document in the exploring phase
- **THEN** the prompt directs the agent to rename the document once it knows what it is about

#### Scenario: The operator's recorded message is unchanged

- **WHEN** a turn carries the notice
- **THEN** the message stored for that turn is what the operator wrote, without it

#### Scenario: An ordinary turn carries nothing

- **WHEN** a run is triggered with no specification document open
- **THEN** the prompt carries no specification notice

#### Scenario: A later phase is not told to interview

- **WHEN** a run is triggered with an approved document open
- **THEN** the prompt names how to write the document but does not direct an interview

### Requirement: A new document is given a name that means nothing

Where a document is created without an explicit path, the Hub SHALL mint one, and that path SHALL
carry no information about the document's subject.

A document enters the exploring phase precisely because its subject is not yet known. A path derived
from the operator's opening sentence records the guess that preceded the interview and then outlives
it, while looking — to every later reader — like a considered name. A name that is obviously
arbitrary cannot be misread as one that was chosen.

The minted name SHALL be a colour and a mythic animal joined by a hyphen, beneath the exploration
root, and SHALL be drawn at random for each document. It SHALL NOT be derived from the title, the
operator's message, the conversation, a counter, or anything else about the document, and it SHALL
NOT be reproducible from them.

The Hub SHALL NOT mint a path that is already taken by another document in the project or by an
existing file, and its search for a free name SHALL be bounded — a namespace that has filled up must
produce an answer or a refusal, never an unbounded search.

The minted path SHALL satisfy the specification path contract by construction rather than by
subsequent rejection.

The creating caller SHALL receive the minted path in the response.

#### Scenario: A document created with no path is named

- **WHEN** a document is created without a path
- **THEN** the Hub mints a path of the form `spec/changes/<colour>-<animal>/spec.html`
- **AND** returns that path to the caller

#### Scenario: The name says nothing about the subject

- **WHEN** two documents are created without a path, with different titles and different opening
  messages
- **THEN** neither minted path contains any word from its title or its opening message

#### Scenario: A minted name does not collide

- **WHEN** a document is created without a path and the first candidate name is already in use in
  that project
- **THEN** the Hub mints a different one and the created document occupies it

#### Scenario: An explicit path is still honoured

- **WHEN** a document is created with a path
- **THEN** that path is used and nothing is minted

### Requirement: A document is renamed once its subject is established

The Hub SHALL provide a rename operation that takes a *subject* in prose and derives the document's
new path from it, and the agent exploring a document SHALL be directed to use it as soon as the
interview establishes what the document is about.

The caller SHALL NOT supply a path. Path validation is the single control preventing a document
being written to an arbitrary location beneath the specification root; a rename accepting a target
path would expose that control to the least trusted caller in the system as its only guard. Deriving
the slug from a subject makes a traversal, a hidden segment or a different filename unexpressible
rather than merely rejected.

A rename SHALL move the document's file, update the document's recorded path, and update every
inbound queue entry that names the old path and has not yet been delivered. A delivered entry SHALL
NOT be rewritten: it records what was open when its turn ran.

A rename SHALL NOT change the document's identity, its requirement identifiers, its content, its
digests, or its recorded events. Identity is the document's identifier and never was its path.

A rename SHALL be recorded as an event naming both the old and the new path.

The Hub SHALL refuse a rename where the document is approved, where the subject yields no usable
slug, or where the resulting path is already occupied by another document or an existing file. Every
such refusal SHALL occur before anything is moved, and SHALL state which condition applied.

The Hub SHALL NOT rewrite the document index in response to a rename. The index is a file the
operator owns and the Hub has only ever read; an entry naming a moved document becomes a missing
entry, which existing diagnostics report truthfully.

#### Scenario: A subject becomes a path

- **WHEN** a document at a minted placeholder path is renamed with the subject
  `Personal houseplant watering tracker`
- **THEN** the document's path becomes `spec/changes/personal-houseplant-watering-tracker/spec.html`
- **AND** the file exists at the new path and no longer exists at the old one

#### Scenario: Content and identity survive the move

- **WHEN** a document with minted requirement identifiers is renamed
- **THEN** its identifier, its rendered content, its requirement identifiers and its recorded events
  are unchanged

#### Scenario: A pending turn follows the document

- **WHEN** an inbound queue entry naming the old path has not been delivered and the document is
  renamed
- **THEN** that entry names the new path

#### Scenario: A delivered turn keeps its record

- **WHEN** an inbound queue entry naming the old path has already been delivered and the document is
  renamed
- **THEN** that entry still names the old path

#### Scenario: An approved document is not renamed

- **WHEN** a rename is attempted on an approved document
- **THEN** it is refused, and the refusal says the document is approved

#### Scenario: A subject that is not a name is refused

- **WHEN** a rename is attempted with a subject that yields an empty slug
- **THEN** it is refused, and no placeholder is minted in its place

#### Scenario: An occupied path is refused

- **WHEN** a rename would move a document onto a path another document already occupies
- **THEN** it is refused and neither document is changed

### Requirement: A rendered document is ordered and complete for a reader

The rendered document SHALL present acceptance criteria grouped in the order of the requirements
they belong to, and SHALL state explicitly when there are no outstanding open questions.

Both defects were found by reading the first agent-authored document rather than by any check.
Criteria were rendered in submission order, so a reader scanning the table by requirement met
`FR-8, FR-8, FR-7` and lost their place. An empty open-questions list rendered as no section at all,
leaving a reader unable to distinguish questions asked and resolved from questions never asked —
which is the difference between a document that has been through an interview and one that has not.

Ordering SHALL be stable: criteria belonging to the same requirement keep the order in which they
were submitted, because that order is the author's and carries their emphasis.

#### Scenario: Criteria are grouped by requirement

- **WHEN** a document is rendered whose acceptance criteria were submitted out of requirement order
- **THEN** the rendered table lists every criterion for a requirement before any criterion for a
  later requirement

#### Scenario: Criteria for one requirement keep their order

- **WHEN** a requirement has several acceptance criteria
- **THEN** they appear in the order they were submitted

#### Scenario: No outstanding questions is said, not implied

- **WHEN** a written document has an empty open-questions list
- **THEN** the rendered document states that none are outstanding

### Requirement: A document declares how strictly it is enforced

A specification document SHALL carry a rigor level of `sketch`, `contract` or `gate`, stated in the
document itself, defaulting to `sketch`.

Rigor says what happens to work that ignores the document. `sketch` reports its state and blocks
nothing. `contract` reports its state, including drift, and blocks nothing. `gate` refuses the
approval of work serving its requirements while any of them is unverified.

**Rigor is not phase.** Phase asks whether the operator has agreed to the document; rigor asks what
follows for work that does not satisfy it. A document may be approved and remain a sketch, or be a
gate while still exploring. Making approval imply enforcement would turn every agreed document into
a barrier.

The Hub SHALL own rigor transitions. A change SHALL be written against the document's current
content digest, so a rigor change cannot land on a document that was edited underneath it, and each
change SHALL be recorded append-only with the actor, the reason, and the digest current at that
moment.

#### Scenario: A document with no stated rigor is a sketch

- **WHEN** a document is created
- **THEN** its rigor is `sketch`
- **AND** it blocks no work

#### Scenario: Rigor is visible in the document

- **WHEN** a document's rigor is set
- **THEN** the rendered document states it

#### Scenario: A rigor change is recorded

- **WHEN** rigor moves from one level to another
- **THEN** the previous level, the new level, the actor and the reason are recorded and never
  overwritten

#### Scenario: A rigor change cannot land on a document that moved

- **WHEN** a rigor change is submitted against a digest that is no longer current
- **THEN** it is refused rather than applied

### Requirement: Only the operator changes rigor

An agent SHALL NOT promote or demote a document's rigor. There SHALL be no argument, tool or route
by which it can express either.

A gate an agent can lower is not a gate. The blocked party would remove the obstacle, and the
enforcement would exist only for agents that did not think to try. Promotion is refused for a
related reason: raising rigor blocks other work, which is a decision about how the project is run.

This is the same construction as approval, and for the same reason: enforced by the absence of a
route rather than by instructing agents not to attempt it. The mechanism it replaces was a charter
instructing an agent to enforce a gate on itself, which is honour-system by construction.

The operator MAY lower rigor, and doing so SHALL be recorded and attributed. An operator who needs
to get past a gate has an explicit, visible way through; what there SHALL NOT be is an unrecorded
override, which is the same act without the evidence that it happened.

#### Scenario: An agent cannot raise rigor

- **WHEN** an agent attempts to promote a document's rigor
- **THEN** it is refused

#### Scenario: An agent cannot lower rigor

- **WHEN** an agent blocked by a gate attempts to demote the document
- **THEN** it is refused
- **AND** the document's rigor is unchanged

#### Scenario: The operator can lower rigor, and it shows

- **WHEN** the operator demotes a document
- **THEN** the demotion is applied and recorded with their attribution

### Requirement: Rigor is only raised on a document that can be enforced

Promotion to `contract` or `gate` SHALL be refused while the document has unresolved requirement
identifiers, duplicate references, or content that does not parse.

Rigor is a claim about enforceability. A document that cannot be read cannot be enforced, and
promoting one would produce a gate whose refusals are parse diagnostics rather than judgements about
the work.

Demotion SHALL NOT be subject to that condition, and SHALL change enforcement only: links,
revisions, evidence and reviews all survive it. A demotion that destroyed the record would be a way
to launder unverified work rather than a way to unblock it.

#### Scenario: A broken document cannot become a gate

- **WHEN** promotion is attempted on a document with an unresolved identifier
- **THEN** it is refused, naming what is unresolved

#### Scenario: Demotion keeps what was established

- **WHEN** a `gate` document is demoted to `sketch`
- **THEN** its requirement links, evidence and reviews are unchanged

#### Scenario: Demotion is always available to the operator

- **WHEN** the operator demotes a document that does not currently parse
- **THEN** the demotion succeeds

