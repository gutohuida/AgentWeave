## ADDED Requirements

### Requirement: Evidence is decided only after the run that recorded it has ended

The Hub SHALL refuse to accept or reject a piece of evidence while the run that recorded it is still executing, and the refusal SHALL say that it clears when that run ends.

An agent records evidence while its work is uncommitted, and the Hub re-points the evidence at the
commit holding the work when the run ends. A decision taken before then judges a commit the Hub is
about to replace, and the decision's reason then disagrees with the row it is recorded on.

The refusal SHALL apply to the operator and to a granted agent alike. It SHALL NOT be answered as a
lack of permission: it is a conflict that clears on its own. Where the Hub cannot tell that the run
is executing — including a run left marked running by a Hub that stopped — the decision SHALL be
allowed.

A view of a piece of evidence SHALL say whether the run that recorded it is still executing, so a
screen can hold its decision instead of offering one the Hub will refuse.

Where the same run records the same demonstration again — same requirement, task, actor and commit —
while its earlier piece is still undecided, the Hub SHALL revise that piece rather than refuse the
second. The revision SHALL keep the piece's identity and SHALL say it was a revision. A piece
recorded against an earlier wording of the requirement SHALL NOT be revised onto the current one.

A refusal of a duplicate recorded by an agent SHALL NOT tell the agent to commit its work, because
the agent is told the Hub commits it. Where the agent's checkout is one the Hub commits when the run ends and holds uncommitted changes, a piece
matching an earlier run's piece at the same commit SHALL be recorded rather than refused, because the
Hub re-points it at the commit holding those changes when the run ends.

#### Scenario: A decision during the recording run is refused

- **WHEN** the operator or a granted agent decides a piece of evidence whose recording run is still executing
- **THEN** the decision is refused as a conflict that names the run
- **AND** no review is recorded and the piece stays awaiting

#### Scenario: The same decision after the run ends is recorded

- **WHEN** the recording run has ended and its evidence has been re-pointed
- **THEN** the same decision is accepted and recorded against the re-pointed commit

#### Scenario: A run the Hub is not executing does not hold a decision

- **WHEN** the recording run is marked running but the Hub is not executing it
- **THEN** the decision is accepted

#### Scenario: The view says the run is still going

- **WHEN** a piece of evidence is read while its recording run is executing
- **THEN** the view says so

#### Scenario: A re-record in the same run revises the undecided piece

- **WHEN** a run records evidence for a requirement and task, then records it again in the same run before anything is committed
- **THEN** the first piece is revised with the second's summary and locator
- **AND** no second piece exists and nothing is refused

#### Scenario: An agent's duplicate refusal does not ask for a commit

- **WHEN** an agent's evidence is refused as a duplicate of a piece an earlier run recorded
- **THEN** the refusal does not tell the agent to commit its work

#### Scenario: A changed checkout re-records across runs

- **WHEN** an agent's new run records evidence matching a piece its earlier run recorded at the same commit, in a task or agent checkout the Hub commits at the end of the run, and that checkout holds uncommitted changes
- **THEN** the new piece is recorded and not refused
