## ADDED Requirements

### Requirement: Evidence is decided only after the run that recorded it has ended

The Hub SHALL refuse to accept or reject a piece of evidence while the run that recorded it is still executing, and the refusal SHALL say that it clears when that run ends and that stopping that run ends it.

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
second. The revision SHALL keep the piece's identity, SHALL say it was a revision, and SHALL take the
time of the revision as the time the piece was recorded, because it is the most recent recording of
that demonstration and whatever picks the most recent piece must pick it. A piece
recorded against an earlier wording of the requirement SHALL NOT be revised onto the current one.

A refusal of a duplicate recorded by an agent SHALL NOT tell the agent to commit its work, because
the agent is told the Hub commits it. Where the agent's checkout is one the Hub commits when the run ends and holds uncommitted changes, a piece
matching an earlier run's piece at the same commit SHALL be recorded rather than refused, because the
Hub re-points it at the commit holding those changes when the run ends.

#### Scenario: A decision during the recording run is refused

- **WHEN** the operator or a granted agent decides a piece of evidence whose recording run is still executing
- **THEN** the decision is refused as a conflict that names the run
- **AND** the refusal says that stopping the run ends it
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
- **AND** its recorded time is the time of the revision
- **AND** no second piece exists and nothing is refused

#### Scenario: An agent's duplicate refusal does not ask for a commit

- **WHEN** an agent's evidence is refused as a duplicate of a piece an earlier run recorded
- **THEN** the refusal does not tell the agent to commit its work

#### Scenario: A changed checkout re-records across runs

- **WHEN** an agent's new run records evidence matching a piece its earlier run recorded at the same commit, in a task or agent checkout the Hub commits at the end of the run, and that checkout holds uncommitted changes
- **THEN** the new piece is recorded and not refused

#### Scenario: A second record in a new turn revises that turn's own piece

- **WHEN** an agent's new run, with uncommitted changes, records a piece matching its earlier run's piece at the same commit and then records the same demonstration again in the same run
- **THEN** the new run's piece is revised
- **AND** exactly two pieces exist, one per run

### Requirement: An agent held from a decision is told when it can decide

The Hub SHALL tell an agent whose decision was refused because the recording run was still executing, once that run has ended, that the pieces it tried to decide can now be decided.

A refused agent's turn ends on the refusal, and nothing else would bring it back: an agent is often
woken to review work while the author's run is still going, and without this the refusal turns a
premature decision into a missing one. The note SHALL be queued to that agent like any other input,
in the conversation the refusal happened in, SHALL name each piece and the commit it names after the
run ended, and SHALL be sent once per ended run. The note SHALL come from the Hub, not from the
operator or an agent. It SHALL NOT be sent before the Hub has stopped counting the run as executing,
so a decision the note prompts is not refused again. A piece decided by someone else in the meantime
SHALL be left out of the note, and where none is left no note SHALL be sent.

Where the Hub restarted while the agent waited, the Hub SHALL NOT be required to send the note: after
a restart the run is no longer executing and the decision is already open.

#### Scenario: A refused reviewer is told when the run ends

- **WHEN** an agent's decision is refused because the recording run is executing, and that run then ends
- **THEN** the agent has one queued input from the Hub, in the conversation it was refused in, naming the piece and the commit it now names
- **AND** deciding the piece in the turn that input starts is recorded

#### Scenario: A piece decided in the meantime is not re-announced

- **WHEN** an agent's decision is refused while the run is executing, and the operator decides the piece after the run ends and before the agent's note is queued
- **THEN** no note naming that piece is queued

#### Scenario: The operator is not queued a note

- **WHEN** the operator's decision is refused because the recording run is executing, and that run then ends
- **THEN** nothing is queued for any agent on the operator's account

### Requirement: A decision is answered as recorded even when the merge it triggers fails

The Hub SHALL answer an accepted or rejected decision with the decision it recorded, even when integrating the work that was waiting for that decision fails.

Accepting evidence may merge an approved task's waiting work, and a repository failure there is
recorded as a skip rather than undoing the decision. The response SHALL NOT turn that failure into
a server error, because the decision stands and a client told otherwise would show a failure for a
decision that was made.

#### Scenario: An integration failure after accepting still answers the decision

- **WHEN** the operator or a granted agent accepts a piece of evidence that an approved task was waiting for, and integrating that task fails
- **THEN** the response reports the piece as accepted
- **AND** the stored piece reads accepted
