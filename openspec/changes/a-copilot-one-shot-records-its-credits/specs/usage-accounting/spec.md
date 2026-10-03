## ADDED Requirements

### Requirement: A Copilot one-shot call records the credits its session reported
The system SHALL record, for every Copilot one-shot call (a checkpoint, its probe, or any other Hub-owned `copilot -p` call that writes an invocation record) whose output carries a session usage checkpoint, the AI credits and premium requests of the last such checkpoint as that call's own charge.

A one-shot call is one process that opens one new session, so the session's final cumulative total
is the call's whole charge. The last checkpoint SHALL be taken, and checkpoints SHALL NOT be summed.
Each figure SHALL be read by the same rule as a Copilot run's session checkpoint: a negative,
non-numeric, boolean or non-finite figure, or a figure too large for the invocation record to
hold, SHALL be ignored and that figure SHALL be unknown, while the other figure is still recorded. A call whose output carries no checkpoint SHALL record both
figures as unknown, never as zero, and no other part of the output SHALL be used in their place.
The credits SHALL be recorded whether the call produced a usable answer, reported an error, or
produced no answer. Like a Copilot run's credits, they SHALL NOT be converted into a monetary
figure, SHALL NOT be added to any token total, and SHALL NOT count toward a project's token budget.
Reading a malformed figure SHALL NOT make the call fail, and SHALL NOT prevent the call's invocation
record from being written.

#### Scenario: A checkpoint's credits reach its invocation record
- **WHEN** a Copilot one-shot call's output carries a session usage checkpoint
- **THEN** the call's invocation record carries that checkpoint's credits and premium requests

#### Scenario: The last checkpoint is the call's charge
- **WHEN** a Copilot one-shot call's output carries two session usage checkpoints
- **THEN** the call's invocation record carries the second checkpoint's figures, not their sum

#### Scenario: A call that failed still records what it was charged
- **WHEN** a Copilot one-shot call's output carries a session error, or no answer, and a session usage checkpoint
- **THEN** the call is recorded as having failed
- **AND** its invocation record carries the checkpoint's credits and premium requests

#### Scenario: No checkpoint records unknown, not zero
- **WHEN** a Copilot one-shot call's output carries no session usage checkpoint
- **THEN** the call's invocation record carries unknown credits and unknown premium requests

#### Scenario: A malformed figure is unknown and does not fail the call
- **WHEN** a Copilot one-shot call's checkpoint carries a negative, non-finite or too-large credit figure and a valid premium-request figure
- **THEN** the call's invocation record is written, carrying unknown credits and the premium-request figure
- **AND** the call's outcome is decided by its answer as if the checkpoint were absent
