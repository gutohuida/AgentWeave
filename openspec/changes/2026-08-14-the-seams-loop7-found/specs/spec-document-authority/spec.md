# spec-document-authority

## MODIFIED Requirements

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
