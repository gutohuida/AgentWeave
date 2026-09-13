## ADDED Requirements

### Requirement: An approver the harness has been seen not to start is not named

The Hub SHALL NOT name its own approver on a run's command line once an earlier run of the same agent was given the Hub's tool server, had its harness report its own start, and ended without that server reporting in, unless the operator has stated the run's access path or some run of that agent has seen the server report in.

An approver that the harness will not start answers nothing. Naming it anyway makes every
approval-needing call fail in a way the model has, on at least one harness, reported to the operator
as a broken machine. Once the Hub has watched one run go by without its server reporting in, it has
evidence, and it stops naming what that evidence says is absent.

A first run is not evidence. A fresh agent has no earlier run, and on a harness that honours the
server its first run is where the server first reports in. Withholding the approver there would
refuse the ordinary first turn of every new agent on every machine where the approver works.

A run counts as that evidence only if all of the following hold. The system recorded that it gave
that run its server. The harness reported its own start, which it does only after it has dealt
with its servers. The harness process exited. And the run completed or failed. A harness that exits
before reporting its start never reached its servers, so it says nothing about them. An unknown
option on the command line is one way to cause that, on a machine where the server would have
worked. The following are not evidence either: a run from before that record existed, a spawn that
never started a process, a stopped run, a run the system lost track of, and a run still in
progress.

This is how *"only where the mechanism answering them is present"* (*"Introducing an enforced
posture does not change existing runs"*) is judged for a run that is given the Hub's tool server.

Withholding the approver changes nothing else about the run. It keeps the permission mode it would
otherwise have had, and it is still given the tool server, so that a harness that later starts the
server earns the approver back without anyone acting. It is not moved to a mode that accepts
requests without asking. Such a run has every approval-needing call refused, and those refusals are
recorded (*"A refusal is recorded wherever it is decided"*). With an approver named and absent, the
same calls were not allowed either. That is the one case the default posture cannot serve, and
*"The default posture lets an agent work inside its own workspace"* states it.

#### Scenario: A first run is given the approver

- **WHEN** a non-yolo run of an agent with no earlier run is spawned under a posture whose
  approvals the Hub's approver answers
- **THEN** its command names the Hub's approver

#### Scenario: A run after a completed test without a report is not

- **WHEN** an earlier run of the agent was given the Hub's tool server, its harness reported its own
  start and exited, it completed or failed, and the server never reported in
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
  server, was not given the server, never started a harness process, had a harness that exited
  before reporting its start, was stopped, was lost track of, or is still running
- **THEN** the next run's command names the approver wherever its posture asks for one

#### Scenario: A harness that never reached its servers is not evidence

- **WHEN** an agent's only earlier run was given the Hub's tool server, and its harness exited
  before reporting its start because of an option it did not recognise
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

A Claude run's harness, if it reaches the end of its turn, reports every refusal of that run in its
own end-of-turn result. That includes refusals it decided alone and refusals the approver decided.
A harness process that dies before the end of its turn writes no such report. Each refusal in that report is
recorded, unless the run has already recorded a refusal of the same tool call, whoever decided it.
The approver's own record can be missing even when an approver was named. An approver the harness
never started answers nothing, and a report that fails is swallowed so that it cannot change the
decision. The harness's report is the one account of those refusals.

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
  naming the tool
- **AND** the record of each names the path or command it was refused

#### Scenario: A refusal the approver recorded is not recorded twice

- **WHEN** a Claude run's approver refuses a tool call and records that refusal
- **AND** the run's harness reports the same tool call as refused
- **THEN** exactly one refusal of that tool call is recorded

#### Scenario: A refusal the approver did not record is recorded from the harness's report

- **WHEN** a Claude run's command names the approver, and the harness refuses a tool call that
  the approver left unrecorded, because nothing answered or the report was lost
- **AND** the run's harness reports that tool call as refused
- **THEN** one refusal of that tool call is recorded

### Requirement: The default posture lets an agent work inside its own workspace

The permission posture the Hub imposes by default SHALL permit an agent to do work within its own
workspace without further configuration.

The Hub MUST NOT impose by default a posture whose decisions can only be resolved by an operator
prompt, unless a surface exists through which an operator can actually answer that prompt. A posture
that defers every decision to an absent answerer denies everything and is indistinguishable from a
broken run.

Isolation SHALL continue to be carried by the agent's workspace boundary, not by withholding
permission inside it.

One case is excepted, by the operator's decision rather than by oversight. On a harness that does
not start the Hub's tool server, the default posture has no answerer, and no posture gives that run
both a workspace check and the ability to work. The Hub does not substitute a posture that accepts
requests without asking, because that would remove the check rather than supply an answer. Such a
run has its approval-needing calls refused, including writes inside its own workspace, and those
refusals are recorded. The operator can instead state the agent's access path. That choice, and
what it trades, is theirs to make.

#### Scenario: A newly created agent can edit files in its own workspace

- **WHEN** the Hub spawns a non-yolo agent that has been given no permission configuration
- **AND** that agent's harness starts the Hub's tool server
- **AND** that agent writes a file inside its own workspace
- **THEN** the write succeeds
- **AND** no approval was required from an operator

#### Scenario: A posture requiring an answer is not imposed by default

- **WHEN** no operator-facing approval surface exists for a provider
- **THEN** the Hub does not default that provider's runs to a posture that asks for approval

#### Scenario: The workspace boundary is unchanged

- **WHEN** an agent acts under the default posture
- **THEN** its ability to affect anything outside its own workspace is unchanged by that posture

#### Scenario: A harness that refuses the Hub's server gets no posture that asks nothing

- **WHEN** the Hub spawns a non-yolo agent that has been given no permission configuration
- **AND** an earlier run showed that agent's harness does not start the Hub's tool server
- **THEN** the run's command does not carry a posture that accepts file or shell requests without
  asking
- **AND** a write inside its own workspace is refused and the refusal is recorded
