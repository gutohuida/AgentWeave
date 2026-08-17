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

**The exploring phase's stated duty SHALL be to interview in the agent's own reply** — open
questions, alternatives with what each makes easier and harder, and what reading the code
established — with the blocking question tool reserved for a decision that has genuine alternatives
and that the agent cannot proceed past. A structured question tool can only collect answers to
questions already thought of; the operator volunteering what nobody asked about is what an
exploration is for, and that only happens in a conversation. Directing the agent to route every
scope question through the tool turns the interview into a form, whatever a charter says about
questionnaires.

The floor SHALL also state that a sketch of a workflow, a boundary, or a before-and-after is welcome
where it makes something easier to see than prose. This belongs with the obligation rather than with
the craft: a charter is optional by decision, and a project with no charter bound should still get a
diagram rather than a wall of text.

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

#### Scenario: Exploring directs the agent to ask in its reply

- **WHEN** the turn context states the exploring phase's duty
- **THEN** it directs the agent to put its questions, alternatives and findings in its own reply
- **AND** it does not direct the agent to route every question that affects scope through the
  blocking question tool

#### Scenario: The blocking tool is scoped to decisions

- **WHEN** the turn context states the exploring phase's duty
- **THEN** it reserves the blocking question tool for a decision with real alternatives that the
  agent cannot proceed past

#### Scenario: Sketching survives an unbound charter

- **WHEN** a run is triggered with a document open in the exploring phase and no charter bound
- **THEN** the turn context still invites a sketch where one makes something easier to see
