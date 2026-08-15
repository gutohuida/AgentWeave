# runtime-diagnostics

## MODIFIED Requirements

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

Each of these facts SHALL be reported as a distinct fact and not only within a composed sentence. A
fact that exists solely inside a message can be read by a person and by nothing else, and where the
composed sentence is not the surface the operator is looking at, the fact does not arrive at all.

Where a run ends abnormally without raising — a turn that reports its own failure rather than one
whose start failed — the same facts SHALL be reported. The operator cannot see which internal path a
failure took, and reporting a runtime's death well in one case and not the other is
indistinguishable from reporting it unreliably.

The exit status a run reports for its turn SHALL be distinguishable from the exit status of the
runtime process. Where a transport has no process exit status for a turn, the system supplies one so
that success and failure read uniformly across transports; conflating that supplied value with a
process's own status gives one death two contradictory numbers and no way to tell which is which.

An exit status SHALL be rendered in a form a person can act on. A platform reporting a forced
termination as a large unsigned value states a fact that reads as corruption; what is displayed
SHALL convey the termination, while what is recorded remains what the platform reported.

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

#### Scenario: The facts are readable without parsing a sentence

- **WHEN** a run fails because its runtime process ended
- **THEN** the exit status, the operation in flight, and what was written to the error stream are
  each reported as separate facts

#### Scenario: A turn that fails reports the runtime's status too

- **WHEN** a turn ends in failure and the runtime process has exited
- **THEN** the failure reports that process's exit status
- **AND** it reports what the process wrote to its error stream

#### Scenario: The turn's status and the process's status are told apart

- **WHEN** a run on a transport with no per-turn process exit status fails
- **THEN** the status reported for the turn is distinct from the status reported for the runtime
  process
- **AND** neither is presented as the other

#### Scenario: A forced termination reads as one

- **WHEN** a runtime is terminated and the platform reports the termination as a large unsigned value
- **THEN** what is displayed conveys the termination rather than that value

#### Scenario: An ordinary exit status is untouched

- **WHEN** a runtime exits with an ordinary status
- **THEN** that status is displayed as it is

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

Where the report instructs the operator to rebuild, it SHALL name a way to do so that is available to
them. A warning naming a command the installation does not have is not actionable, and an
unactionable warning is ignored — including on the occasions when it is right.

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

#### Scenario: The instruction can be followed

- **WHEN** the system reports the artefact as stale
- **THEN** the instruction names a way to rebuild that does not depend on tooling the installation
  may not have
