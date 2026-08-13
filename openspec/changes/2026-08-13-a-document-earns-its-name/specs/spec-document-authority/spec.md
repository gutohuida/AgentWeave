# spec-document-authority

## ADDED Requirements

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

## MODIFIED Requirements

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
