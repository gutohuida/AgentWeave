# spec-document-authority

## ADDED Requirements

### Requirement: Evidence is footprinted against the work it describes

An implementation footprint SHALL be captured from the working tree that holds the work the evidence
is about, not from a fixed location.

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
