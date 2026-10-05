## ADDED Requirements

### Requirement: A roadmap carries ordered slices and no requirements or tasks

A roadmap document SHALL carry an ordered list of slices, each with a key, a title, an intent, a done criterion, and the keys of the slices it builds after. It SHALL carry no requirements and no tasks.

A roadmap is the plan for a request too large for one change document. It says what the slices
are and in what order they are built. Each slice's requirements live in the change document that
specifies it, which is written when that slice is next. Slices are accepted only on a roadmap.
Completeness for a roadmap asks for at least one slice, not for requirements. Approving a roadmap
creates no tasks.

#### Scenario: A roadmap with slices is proposable

- **WHEN** a roadmap is moved to proposed, and its payload has non-goals and two slices, each with
  a key, title, intent and done criterion
- **THEN** the move succeeds, and no finding names missing requirements

#### Scenario: A roadmap without slices is incomplete

- **WHEN** a roadmap with no slices is moved to proposed
- **THEN** it is refused, and the finding names the missing slices

#### Scenario: A roadmap that carries tasks or requirements is refused

- **WHEN** a roadmap payload carrying a requirement or a task is submitted
- **THEN** it is refused, and the refusal says those belong in the slice's change document

#### Scenario: Slices are refused on any other kind

- **WHEN** a change-spec payload carrying slices is submitted
- **THEN** it is refused

#### Scenario: A slice builds after a slice that exists

- **WHEN** a slice names in builds-after a key that is not a slice of the same roadmap, or names
  itself
- **THEN** the submission is refused, naming the key

#### Scenario: Approving a roadmap creates no tasks

- **WHEN** the operator approves a roadmap
- **THEN** no task is created

#### Scenario: The roadmap's slices are rendered and readable

- **WHEN** a roadmap is rendered, or read by an agent through the document read tool
- **THEN** each slice's key, title, intent, done criterion and builds-after appear, in roadmap order

### Requirement: A change document may name the roadmap slice it specifies

A change document SHALL be able to name the roadmap and the slice key it specifies, and moving it to proposed or approved SHALL be refused unless that roadmap exists, is approved, and holds that slice.

The link is held in the slice's own payload, not in the corpus index. Only the operator may set a
document's place in the index, and a rename does not update it. A roadmap is approved before its
first slice is proposed, and an approved document cannot be renamed. So a path that resolves at
proposal still resolves later.

#### Scenario: A slice of an approved roadmap is proposable

- **WHEN** a change document naming an approved roadmap and one of its slice keys is moved to
  proposed
- **THEN** no roadmap finding blocks it

#### Scenario: A slice of an unapproved roadmap is not proposable

- **WHEN** a change document names a roadmap that is still exploring
- **THEN** the move to proposed is refused, and the finding names the roadmap and its phase

#### Scenario: A slice key the roadmap does not hold

- **WHEN** a change document names a slice key that the roadmap does not hold
- **THEN** the move to proposed is refused, and the finding names the key and the roadmap

#### Scenario: The slice says whose slice it is

- **WHEN** a change document naming a roadmap slice is rendered
- **THEN** it shows the slice's key and title and the roadmap's title

### Requirement: Approving a slice can start the drafting of the next one

Approving a change document that names a roadmap slice SHALL, when the approval request asks for it, queue one turn as the operator to the agent that created that document, in the conversation where it created it, asking it to draft the slice that follows in the roadmap's order; the approval response SHALL say whether a turn was queued and, if not, why.

The operator approves each slice. The agent drafts the next one with what the last one taught it.
The turn is the operator's because the operator asked for it in the approval request, so no new kind
of queue origin is introduced. "The next slice" is the one after the approved slice in the roadmap's
list. Builds-after constrains that order but does not choose it.

#### Scenario: The next slice is drafted by the slice's author

- **WHEN** the operator approves, asking for the next slice, slice S1 of a roadmap whose slices are
  S1 and S2, and the slice document was created by agent planner
- **THEN** one turn is queued from the operator to planner, in the conversation that created the
  document, naming the roadmap and slice S2 with its title
- **AND** the approval response reports it as queued, naming S2 and planner

#### Scenario: The drafting turn is a specification turn on the roadmap

- **WHEN** the turn queued to draft the next slice starts
- **THEN** it has the roadmap open as its specification document, so it has no file-write tool
- **AND** it is told that the roadmap's slices are specified as change documents, not implemented
  from the roadmap

#### Scenario: The last slice queues nothing

- **WHEN** the approved document specifies the roadmap's last slice
- **THEN** no turn is queued, and the response says the roadmap has no further slice

#### Scenario: A document the operator created has no author to ask

- **WHEN** the approved slice document was created by the operator
- **THEN** no turn is queued, and the response says no agent created the document

#### Scenario: Not asking queues nothing

- **WHEN** the operator approves a slice document without asking for the next slice
- **THEN** no turn is queued

#### Scenario: A document that is not a slice is unaffected

- **WHEN** the operator approves, asking for the next slice, a change document that names no roadmap
- **THEN** no turn is queued, and the approval is otherwise unchanged

### Requirement: Authoring guidance prefers a roadmap and a small slice

The guidance an agent receives for creating and submitting a specification SHALL tell it to write a request larger than one slice as a roadmap plus the first slice's change document, to keep a slice to about a dozen requirements or fewer as a few tasks, and to record later slices in the roadmap instead of specifying them.

The guidance is in the creation and submission tool descriptions and in the specification-turn
duties, so every authoring agent receives it whether or not a charter is bound. It is not enforced.
The size is measured on real runs instead.

#### Scenario: The tools say it

- **WHEN** the creation and submission tool descriptions are read
- **THEN** both name the roadmap-plus-slice shape and the size of a slice

#### Scenario: A specification turn is told it

- **WHEN** an agent's turn context carries the specification duties
- **THEN** they name the roadmap-plus-slice shape and the size of a slice

#### Scenario: An approved roadmap is not implemented

- **WHEN** an agent's turn has an approved roadmap open
- **THEN** its duties say that slices are specified one at a time as change documents naming the
  roadmap, and that the roadmap itself is not implemented
