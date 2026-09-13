## ADDED Requirements

### Requirement: An approver the harness has been seen not to start is not named

The Hub SHALL NOT name its own approver on a run's command line once an earlier run of the same agent was given the Hub's tool server, reached its harness, and ended without that server reporting in, unless the operator has stated the run's access path or some run of that agent has seen the server report in.

An approver that the harness will not start answers nothing. Naming it anyway makes every
approval-needing call fail in a way the model has, on at least one harness, reported to the operator
as a broken machine. Once the Hub has watched one run go by without its server reporting in, it has
evidence, and it stops naming what that evidence says is absent.

A first run is not evidence. A fresh agent has no earlier run, and on a harness that honours the
server its first run is where the server first reports in. Withholding the approver there would
refuse the ordinary first turn of every new agent on every machine where the approver works.

A run counts as that evidence only if the system recorded that it gave that run its server, the
harness process was started and exited, and the run completed or failed. A run from before that
record existed, a spawn that never started a process, a stopped run and a run still in progress
are not evidence.

Withholding the approver changes nothing else about the run. It keeps the permission mode it would
otherwise have had, and it is still given the tool server, so that a harness that later starts the
server earns the approver back without anyone acting. It is not moved to a mode that accepts
requests without asking. Such a run has every approval-needing call refused, exactly as it had
with an approver named and absent, and those refusals are recorded (*"A refusal is recorded wherever
it is decided"*).

#### Scenario: A first run is given the approver

- **WHEN** a non-yolo run of an agent with no earlier run is spawned under a posture whose
  approvals the Hub's approver answers
- **THEN** its command names the Hub's approver

#### Scenario: A run after a completed test without a report is not

- **WHEN** an earlier run of the agent was given the Hub's tool server, its harness process started
  and exited, it completed or failed, and the server never reported in
- **AND** no run of the agent has seen the server report in, and the operator has not stated the
  access path
- **THEN** the next run's command does not name the Hub's approver
- **AND** it still carries the Hub's tool server
- **AND** it carries the permission mode it would have carried with the approver named

#### Scenario: The operator's posture choice does not bring an absent approver back

- **WHEN** the operator selects a posture whose approvals the Hub's approver answers, for an agent
  in the state described above
- **THEN** the run's command carries that posture's permission mode
- **AND** it does not name the Hub's approver

#### Scenario: A report outranks the absence of one

- **WHEN** any run of the agent has seen the Hub's tool server report in
- **THEN** the next run's command names the approver wherever its posture asks for one, however
  many runs have ended without a report

#### Scenario: The operator's statement is honoured

- **WHEN** the operator has stated that the agent's runs use the tool-protocol access path
- **THEN** the approver is named wherever the posture asks for one

#### Scenario: What is not a test is not evidence

- **WHEN** every earlier run of the agent either predates the record of whether it was given the
  server, was not given the server, never started a harness process, was stopped, or is still
  running
- **THEN** the next run's command names the approver wherever its posture asks for one

#### Scenario: Nothing is widened

- **WHEN** a run's command does not name the approver for the reason above
- **THEN** its permission mode is not one that accepts file or shell requests without asking

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

A Claude run whose command names no approver has its refusals decided by the harness alone, and the
harness reports them only in its own end-of-turn result. Those refusals are recorded from that
report. A run whose command does name the approver already has each refusal recorded where the
approver decided it, and is not recorded a second time from the harness's report.

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

#### Scenario: A Claude run with no approver has its harness's refusals recorded

- **WHEN** a Claude run whose command names no approver ends with its harness reporting refused
  tool calls
- **THEN** each refused call appears in the project's activity as a refusal decided by the runtime,
  naming the tool and the path or command it was refused

#### Scenario: A run with the approver is not recorded twice

- **WHEN** a Claude run whose command names the approver ends with its harness reporting refused
  tool calls
- **THEN** no refusal is recorded from the harness's report
