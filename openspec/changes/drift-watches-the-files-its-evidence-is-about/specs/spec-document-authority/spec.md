## MODIFIED Requirements

### Requirement: Drift is assessed against the line of work a footprint names

Drift SHALL be assessed by comparing a footprint against the line of work it names until that work is reachable from the project's main line, and against the main line from then on, and SHALL NOT be assessed by comparing every footprint against a single location regardless of where its work is.

Comparing an agent's footprint against the project's main line before its work is there would report
every file that agent changed as a change, making every demonstrated requirement a drift candidate.
That the work is not on the main line is already reported as an integration answer; raising it again
as drift asks the operator one question in two vocabularies.

Once the work is on the main line, the line of work it was recorded on is no longer where the
product is. Nothing commits to it again, so comparing against it would stop watching the evidence
at exactly the moment the work ships — and an agent's evidence is always recorded on such a line,
so the loss would fall entirely on the agent plane. Whether the work has reached the main line only
ever changes from no to yes, so a footprint changes basis at most once.

A footprint whose work is not yet on the main line, and that names no line of work or names one
that no longer exists, SHALL raise nothing. Being unable to tell is not evidence of drift. A
footprint whose work is on the main line is compared against the main line whatever line of work it
names.

Footprints of different kinds SHALL be compared against their own kind of observation.

#### Scenario: Movement on the main line is not drift for work not yet on it

- **WHEN** the main branch changes and an agent's demonstrated work, not yet reachable from the main
  line, is unchanged
- **THEN** no drift candidate is raised for that work

#### Scenario: Movement on the branch is drift

- **WHEN** the branch a footprint names changes a watched file after the evidence was accepted, and
  the work is not yet reachable from the main line
- **THEN** a drift candidate is raised

#### Scenario: Movement on the main line is drift for work already on it

- **WHEN** an agent's demonstrated work has reached the main line
- **AND** a later commit on the main line changes a file its footprint watches
- **THEN** a drift candidate is raised for that evidence

#### Scenario: Reaching the main line does not re-raise a resolved change

- **WHEN** a candidate was resolved while the work was on its branch
- **AND** the work then reaches the main line with the same content for the watched files
- **THEN** no new candidate is raised

#### Scenario: Work on the main line is watched even when no branch was named

- **WHEN** a footprint names no line of work, because it was taken on a detached checkout
- **AND** its commit is reachable from the main line
- **AND** a later commit on the main line changes a file it watches
- **THEN** a drift candidate is raised for that evidence

#### Scenario: A vanished branch raises nothing

- **WHEN** the branch a footprint names no longer exists and its work is not on the main line
- **THEN** no drift candidate is raised
- **AND** no error is reported
