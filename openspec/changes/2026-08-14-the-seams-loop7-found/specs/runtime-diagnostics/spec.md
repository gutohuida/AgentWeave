# runtime-diagnostics

## ADDED Requirements

### Requirement: A runtime that dies reports what it was doing

A run that fails because its runtime process ended SHALL report the process's exit status, the operation in flight when it ended, and what the process last wrote to its error stream.

"The process ended" is true of every such failure and distinguishes none of them. A crash, a
non-existent binary, a rejected credential and an unresumable session all produce the same sentence,
so diagnosing one means inferring the cause from which other agents still work.

The error stream of a runtime the system starts SHALL be read. A stream that is captured and never
consumed can fill, at which point the process it belongs to blocks on writing to it — so leaving it
unread is not merely a lost diagnostic but a way to hang the very process being diagnosed. What is
retained SHALL be bounded.

These facts SHALL be carried by the failure itself, so that every existing reader of the failure
reports them without being changed.

#### Scenario: A runtime that exits reports its status

- **WHEN** a run fails because its runtime process ended
- **THEN** the failure names the process's exit status
- **AND** it names the operation that was in flight

#### Scenario: What the runtime complained about is retained

- **WHEN** a runtime writes to its error stream and then exits
- **THEN** the failure includes what it wrote
- **AND** the amount retained is bounded

#### Scenario: A talkative runtime is not blocked by its own diagnostics

- **WHEN** a runtime writes more to its error stream than the stream can hold
- **THEN** the runtime is not blocked

### Requirement: The built interface artefact can be asserted current

The system SHALL treat the built interface artefact as current where a recorded assertion says it was built from the interface source as it now stands.

Staleness is reported today by comparing when the source was last changed against when the artefact
was last changed. A source change that cannot alter the built output — a change to types, comments,
or anything else erased before the output is produced — leaves the artefact byte for byte identical,
so rebuilding produces nothing to record, the artefact's timestamp never moves, and the warning
stands permanently. A warning that cannot be cleared by doing the thing it asks for teaches the
operator to ignore it, which costs the cases where it is right.

The assertion SHALL identify the state of the source it was made against, including changes not yet
committed, so that it distinguishes an artefact built from what is present from one built from
something else.

Where no assertion has been recorded, staleness SHALL be reported as it was before. An installation
carrying no assertion is not thereby declared current.

A recorded assertion SHALL take effect without restarting the system.

This requirement establishes an assertion, not a proof. Only building the artefact can establish
that it matches its source; what is recorded is a dated and attributable claim that someone did so.

#### Scenario: An assertion matching the source clears the warning

- **WHEN** the artefact carries an assertion naming the interface source as it now stands
- **THEN** the system does not report the artefact as stale

#### Scenario: A source change that cannot alter the output clears after rebuilding

- **WHEN** the interface source changes in a way that leaves the built artefact identical
- **AND** the artefact is rebuilt and the assertion recorded
- **THEN** the system does not report the artefact as stale

#### Scenario: An assertion naming other source still warns

- **WHEN** the artefact carries an assertion naming source that differs from what is present
- **THEN** the system reports the artefact as stale

#### Scenario: No assertion behaves as before

- **WHEN** the artefact carries no assertion
- **THEN** staleness is reported by comparing when source and artefact last changed

#### Scenario: The warning clears without a restart

- **WHEN** an assertion is recorded while the system is running
- **THEN** the system stops reporting the artefact as stale without being restarted
