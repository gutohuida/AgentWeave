## ADDED Requirements

### Requirement: A file tool writing outside the run's workspace is recorded, in every posture

The Hub SHALL record, against the run, every call to a file-writing tool whose target resolves outside that run's own workspace, in every permission posture, including postures that perform no check and postures in which the operator approved the call.

Detection SHALL be made where the run's tool calls are already observed to build its transcript, not
where they are approved. Approval runs in some postures and not others, and under the posture in
which the operator answers, the call being recorded is one they deliberately allowed. Observation
runs in all of them, because it is how the run is rendered at all.

The boundary compared against SHALL be the run's own recorded workspace — the same value the run was
started in and the same value any enforcing posture checks. A second boundary computed from the
agent's identity would be able to disagree with the first, and nothing could then say which is real.

The record SHALL name **which workspace was written into**, as a kind and a name, and not merely that
the write left the run's own. The destinations are distinguishable and they do not mean the same
thing. A write into another agent's or task's workspace is committed onto that workspace's branch by
the Hub's own snapshot, under a subject naming its owner's turn, and thereafter flows through review,
evidence and integration attributed to the wrong actor. A write into the project's tracked tree lands
where its owner's `git status` will show it.

**The Hub's own working directory under the project root SHALL be a destination kind of its own, and
SHALL NOT be reported as the project's directory.** The Hub seeds the repository's ignore rules with
its own subtree on every turn, so a write there is the one part of the project root that is
deliberately invisible to `git status` — the opposite of the tracked case above — and part of it is
the Hub's own record-keeping about the very run doing the writing. Naming it "the project" would
attach the mildest reading to the least visible destination.

The record SHALL be bounded, and repeated writes to the same destination within one run SHALL notify
the operator once rather than once per call.

Where the run's workspace cannot be established or resolved, nothing SHALL be recorded, and the
absence SHALL NOT be reported as a write outside the workspace. This differs deliberately from the
enforcing posture, which refuses when it cannot establish a boundary: refusing is correct for a gate,
whereas writing "it wrote outside" when the truth is "nobody could tell" would attribute to an agent
something it may not have done.

A run for which no observation was made SHALL be distinguishable from a run observed and found to
have written nothing outside its workspace.

The record SHALL NOT be a refusal and SHALL NOT be presented as one. The action it describes was
allowed — by an operator who answered for it, or by a posture that checked nothing — and a record
that reads as a refusal would tell the operator the write did not land when it did.

**A run whose workspace is the project's own directory is outside this requirement's reach, and the
absence of a record for it SHALL NOT be read as confinement.** Where the run's workspace and the
project directory are the same — a read-only agent, a project that is not a repository, a machine
with no git — every path inside the project is inside that run's workspace, including another
agent's checkout. Such a run is correctly recorded as having written nothing outside its workspace,
because its workspace is everything; it is also the least confined run the product has. The two
readings are only compatible while the recorded directory is read as *where the run started*, which
is what the companion requirement in `workspace-isolation` establishes.

**Scope is part of the requirement, not a limitation of it.** What is recorded is that a file tool
wrote outside the workspace. It SHALL NOT be described, labelled or surfaced as a complete account of
writes leaving the workspace, because two vectors are not reachable from a check on a tool call's
declared path and are out of scope:

- a shell command, which carries a command string rather than a path argument, so a redirect to an
  absolute path names no path this check can see;
- a symbolic link inside the workspace pointing outside it, whose reported path is legitimately
  inside.

A detector that misses the case it is named for is worse than none, because it reads as coverage.
Named for exactly what it catches, it is coverage.

#### Scenario: A write outside the workspace under the default posture

- **WHEN** a run's file-writing tool call names a path outside the run's workspace
- **THEN** the call is recorded against the run
- **AND** the record names the tool, the path, and the workspace the path belongs to

#### Scenario: An operator-approved write outside the workspace is still recorded

- **WHEN** a run under the posture in which the operator answers makes a file-writing call outside its
  workspace and the operator allows it
- **THEN** the write is recorded against the run
- **AND** the record does not depend on how the call was decided

#### Scenario: A posture that checks nothing is still observed

- **WHEN** a run under a posture that performs no permission check writes outside its workspace
- **THEN** the write is recorded against the run

#### Scenario: A write into another workspace names that workspace

- **WHEN** a run writes into a workspace belonging to another agent or to a task
- **THEN** the record names that workspace's kind and name
- **AND** does not merely state that the write was outside the writing run's own

#### Scenario: Work inside the workspace is not recorded

- **WHEN** a run's file-writing calls all resolve inside its own workspace
- **THEN** no such record is made
- **AND** the run is still distinguishable from one that was never observed

#### Scenario: A relative path that traverses outside is caught

- **WHEN** a file-writing call names a relative path that resolves outside the workspace only after
  traversal
- **THEN** it is recorded as a write outside the workspace

#### Scenario: The record is not a refusal

- **WHEN** a write outside the run's workspace is recorded
- **THEN** the record is not a refusal
- **AND** it does not claim the action was refused or prevented

#### Scenario: A run whose workspace is the project directory records nothing

- **WHEN** a run's workspace is the project's own directory and it writes anywhere inside the project
- **THEN** no write outside the workspace is recorded
- **AND** the empty record is not a statement that the run was confined

#### Scenario: Reads are not recorded

- **WHEN** a run reads a file outside its workspace
- **THEN** nothing is recorded

#### Scenario: An unestablished workspace records nothing

- **WHEN** a run's workspace cannot be established or resolved
- **THEN** no write is recorded for that run
- **AND** the run is not reported as having written outside its workspace

#### Scenario: Repeated writes to one destination notify once

- **WHEN** a run makes several file-writing calls into the same destination workspace
- **THEN** every call is present in the run's record
- **AND** the operator is notified once for that destination rather than once per call

### Requirement: The product states which postures confine a run and which do not

The Hub's documentation SHALL state, per permission posture, whether a run's file writes are checked against its workspace, and SHALL NOT state it per execution mode.

Saying it by mode would be false in both directions. In native mode the posture in which the Hub
answers each call *does* refuse a path outside the run's workspace, so telling an operator running the
default that nothing is checking is wrong; and the postures that check nothing exist in native mode
too, so telling an operator running one of those that native mode's story applies to them is equally
wrong. Docker mode confines at the mount, by construction, whatever posture is selected.

The statement SHALL say that a workspace is a working directory rather than a wall, that the operator
is the boundary where no posture is checking, and that a write that leaves the workspace is recorded
rather than prevented.

#### Scenario: The postures are documented by what they check

- **WHEN** the permission postures are documented
- **THEN** each states whether a file write is checked against the run's workspace

#### Scenario: Containment is not claimed for a mode

- **WHEN** the documentation describes native execution
- **THEN** it does not claim that native mode confines a run's writes
- **AND** it does not claim that native mode leaves them entirely unchecked

## MODIFIED Requirements

### Requirement: A refusal is recorded wherever it is decided

The system SHALL record a durable event when it refuses an agent's action, regardless of which runtime decided the refusal.

An operator reading the activity of a run needs to know an agent was blocked. A refusal that exists
only in the agent's own prose account is one the operator will not find, and the agent's summary of
its own failure is a claim rather than a record.

Recording SHALL cover refusals a runtime decides on its own, not only those the operator was asked
about. The refusals an operator never saw are precisely the ones they cannot otherwise learn of.

A refusal SHALL be recorded once. A decision the operator already answered is already recorded, and
recording it again tells them it happened twice.

Only refusals SHALL be recorded **as refusals**. An allowed action is the ordinary case, and a
refusal record with an entry per allowed action buries the refusals among them. This constrains
what the refusal record may contain; it is not a rule about every durable event the system keeps.

The recorded event SHALL name the refused action in terms the operator can read.

#### Scenario: A runtime refuses an action on its own

- **WHEN** a runtime refuses an agent's action without asking the operator
- **THEN** the refusal appears in the project's activity

#### Scenario: An operator-answered refusal is recorded once

- **WHEN** the operator is asked about an action and refuses it
- **THEN** exactly one refusal is recorded

#### Scenario: Allowed actions are not recorded as refusals

- **WHEN** a runtime allows an agent's action
- **THEN** no refusal is recorded

#### Scenario: The refused action is readable

- **WHEN** a refusal is recorded
- **THEN** the action it names is readable rather than an internal method name
