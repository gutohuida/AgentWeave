# agent-charter Specification

## Purpose

Define project-scoped, operator-authored behavior charters, their one-time migration seed from the
legacy role guides, and the single explicit charter binding used to build each agent's context.

## Requirements

### Requirement: Charters are project-scoped, authored Hub records

The Hub SHALL persist charters as project-scoped database rows, each with a name and markdown
behavior content. A charter SHALL NOT be represented as a file on disk or as a fixed, hardcoded
list of personas.

#### Scenario: Charter is created

- **WHEN** an operator creates a charter with a name and content
- **THEN** the Hub persists it as a project-scoped record with a stable identifier

#### Scenario: Charter content is edited

- **WHEN** an operator edits an existing charter's content and saves
- **THEN** subsequent context lookups for agents bound to that charter return the updated content

### Requirement: Existing role guides seed initial charters once

A project with zero charter records SHALL be seeded, on first Hub start, with the bundled starter
charter set. This seeding SHALL run at most once per project.

The starter set SHALL be curated against the accountability test defined below, not derived
one-for-one from the legacy role guides. A charter SHALL be included only if it names something an
agent can be held answerable for.

Seeding SHALL NOT modify, replace, or reconcile the charters of a project that already has them. A
project seeded from an earlier starter set keeps that set, including any charter the operator has
since edited.

#### Scenario: First boot seeds the curated starter set

- **WHEN** a project has no charter records and the Hub starts
- **THEN** the Hub creates one charter per entry in the bundled starter set, with matching name and
  content

#### Scenario: Seeding does not repeat

- **WHEN** the Hub restarts after charters already exist for a project
- **THEN** no additional seed charters are created

#### Scenario: An existing project is not reconciled to a changed starter set

- **WHEN** the bundled starter set changes and the Hub starts on a project that was seeded earlier
- **THEN** that project's charters are left exactly as they are, and none is added, removed, or
  rewritten

### Requirement: An agent is bound to at most one charter

Each Hub `Agent` record SHALL reference at most one charter record. An agent with no bound charter
SHALL remain usable — its context response SHALL state plainly that no charter is assigned rather
than erroring or fabricating behavior content.

#### Scenario: Agent context resolves its bound charter

- **WHEN** an agent with a bound charter begins a turn
- **THEN** the supplied context includes that charter's content

#### Scenario: Agent has no bound charter

- **WHEN** an agent with no bound charter requests its context
- **THEN** the response includes project instructions and a clear no-charter notice, and does not
  error

### Requirement: Charter management is available through the Hub UI

The Hub UI SHALL provide a screen to list, read, create, edit, and delete charters, and to bind an
agent to a charter from the agent's detail view. This screen replaces any prior role-assignment
command or interface.

Reading a charter's full content SHALL be possible without opening any surface that can modify it. A
charter's content is the text injected into an agent's turn, so an operator choosing which charter to
bind SHALL be able to see all of it.

The screen SHALL allow more than one charter to be open for reading at the same time, so that two can
be compared without closing either.

#### Scenario: Operator reads a charter without opening the editor

- **WHEN** an operator expands a charter on the charter screen
- **THEN** its full content is shown, and no editable field, save action, or discard action is
  presented

#### Scenario: Two charters are compared

- **WHEN** an operator opens one charter for reading and then opens a second
- **THEN** both remain open, and the first is not closed by the second

#### Scenario: The list is legible when nothing is expanded

- **WHEN** the charter screen is first opened
- **THEN** every charter is collapsed to a short summary, and the list of charter names is readable
  without scrolling past full documents

#### Scenario: Operator authors a new charter

- **WHEN** an operator opens the charter screen and creates a charter with custom content
- **THEN** the charter is available to bind to any agent in the project

#### Scenario: Operator reassigns an agent's charter

- **WHEN** an operator selects a different charter for an agent in the Hub UI
- **THEN** the agent's charter binding updates and its next context response reflects the new
  charter

### Requirement: Seeded charters describe only what the runtime provides

Seeded charters SHALL describe only mechanisms the runtime actually offers. A charter's content is
injected into an agent's context verbatim, so a charter is instruction, not documentation.

A seeded charter MUST NOT instruct an agent to read a file the system does not create, run a command
that does not exist, or address a participant the roster does not contain.

A roster is whatever agents the operator has created. No charter may therefore assume that any
particular other charter, title, or specialism is present in the project. Where a seeded charter
needs to escalate, hand off, or resolve an ambiguity, it SHALL direct the agent to the operator,
which is the one participant always reachable.

A seeded charter MUST NOT restate a rule that the system enforces in code. A gate the agent is
subject to is not a gate the agent administers, and a prose copy of it can disagree with the
enforced version while carrying no authority.

Where a charter would once have told an agent to gather its orientation, it SHALL instead rely on the
context it is given: the roster, the project instructions, and the charter itself all arrive with the
turn, and nothing needs to be read before starting.

#### Scenario: A seeded charter cites no absent file

- **WHEN** a seeded charter's content is examined
- **THEN** it instructs the agent to read no file the system does not create

#### Scenario: A seeded charter cites no absent command

- **WHEN** a seeded charter's content is examined
- **THEN** it names no command the shipped runtime does not provide

#### Scenario: A seeded charter directs no agent at another roster title

- **WHEN** a seeded charter's content is examined for escalation, hand-off, or consultation
  instructions
- **THEN** none of them names another charter's title as the party to address

#### Scenario: Escalation resolves to the operator

- **WHEN** a seeded charter describes what to do about an ambiguity or a dispute it cannot settle
- **THEN** it directs the agent to ask the operator

#### Scenario: A seeded charter does not re-enforce a coded gate

- **WHEN** a seeded charter's content is examined against rules the system enforces
- **THEN** it does not instruct the agent to enforce a status transition or approval gate that the
  transition service owns

#### Scenario: Orientation comes from the turn, not from retrieval

- **WHEN** a seeded charter describes how an agent should begin
- **THEN** it relies on the roster, instructions, and charter already supplied with the turn

### Requirement: A charter names an accountability, not an activity

A seeded charter SHALL describe what its holder is answerable for. It SHALL NOT be defined by the
activity its holder performs, by the technology its holder works in, or by the phase of work it
occurs in.

Two candidate charters that are answerable for the same thing and differ only in subject matter SHALL
be one charter carrying an explicit scope, rather than two charters.

Coordination that the system performs in code SHALL NOT also be expressed as a charter. A charter
asking a model to guarantee in prose what a service guarantees in code creates an unenforced second
authority.

#### Scenario: Specialisms of one accountability are one charter

- **WHEN** the starter set is examined for charters answerable for the same outcome
- **THEN** they appear as a single charter with a scope the operator fills in, not as several
  near-duplicate charters distinguished by technology

#### Scenario: Coded coordination is not also a charter

- **WHEN** the starter set is examined
- **THEN** it contains no charter whose responsibility is to route work, assign tasks, select models,
  or track progress

#### Scenario: An activity has no charter of its own

- **WHEN** the starter set is examined
- **THEN** no charter's identity is the stage of work its holder is in

### Requirement: The starter set demonstrates a non-software separation of duties

The bundled starter set SHALL include at least one pair of charters from a non-software domain whose
separation from each other is a control rather than a convenience — where one holder may not perform
the other's step.

This exists because the software case cannot demonstrate it. One capable model can perform every
activity in a development workflow, which makes charters look like topic labels; a genuine separation
of duties is what shows a charter carrying a guarantee.

#### Scenario: The starter set is not exclusively about software

- **WHEN** an operator views the charters seeded into a fresh project
- **THEN** at least one pair describes accountabilities from a domain other than software development

#### Scenario: The pair states its own separation

- **WHEN** either charter of the non-software pair is read
- **THEN** it states which step belongs to the other holder and that it may not perform that step
  itself
