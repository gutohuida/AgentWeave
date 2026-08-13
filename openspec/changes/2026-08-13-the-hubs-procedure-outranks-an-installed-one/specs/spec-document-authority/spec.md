# spec-document-authority

## MODIFIED Requirements

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
