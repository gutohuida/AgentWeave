## MODIFIED Requirements

### Requirement: Usage aggregates by agent and project

The accounting API SHALL aggregate measured token totals per agent and project and SHALL separately
report measured-turn and unavailable-turn counts. Historical or missing telemetry MUST NOT be
invented.

The accounting API SHALL also aggregate the Hub's own out-of-band model calls (a checkpoint, its
probe, a conversation title) per kind, beside the agents. The project total SHALL be the sum of the
agents' measured totals and those calls' measured totals. A call that never started SHALL
contribute nothing, and a call that started but reported no usage SHALL be counted as such rather
than as zero.

#### Scenario: Agent totals contribute to the project total

- **WHEN** measured turns exist for more than one agent in a project
- **THEN** each agent summary contains only that agent's usage
- **AND** the project total contains the sum of their measured totals

#### Scenario: Unavailable turns remain visible

- **WHEN** a project contains both measured and unavailable turn outcomes
- **THEN** the aggregate reports both counts
- **AND** the unavailable turn contributes no fabricated token value

#### Scenario: Out-of-band calls are their own lines and part of the total

- **WHEN** a project has measured turns and a measured checkpoint call
- **THEN** the aggregate reports the checkpoint call's tokens on a line of its own kind
- **AND** the project total is the turns' total plus the call's total

#### Scenario: A call's tokens are normalised as a turn's are

- **WHEN** a call's provider reports cached input separately from fresh input
- **THEN** the call's total counts the cached input as a turn's total from that provider would

### Requirement: A project token budget pauses autonomy but not the operator

The system SHALL allow an operator to configure a positive token budget per project or disable it.
When measured project usage is greater than or equal to the configured budget, autonomous turns
SHALL remain queued and SHALL NOT start. Operator-initiated turns SHALL remain available and SHALL
still be accounted.

Measured project usage SHALL include the Hub's own out-of-band model calls. When the budget is
exhausted, an out-of-band call the operator did not request SHALL NOT start, and SHALL be recorded
as not started because the budget is exhausted. A call the operator requested SHALL still start and
SHALL be accounted. Where the budget cannot be read, a call the operator did not request SHALL NOT
start.

#### Scenario: Agent-to-agent work pauses at exhaustion

- **WHEN** an agent-origin queue batch is ready and the project budget is exhausted
- **THEN** no run starts
- **AND** every entry remains queued
- **AND** the waiting reason states that the token budget is exhausted

#### Scenario: Scheduled work is autonomous

- **WHEN** a scheduled job queues work while the project budget is exhausted
- **THEN** that work does not start autonomously
- **AND** it is not misclassified as an operator turn

#### Scenario: Operator input still runs

- **WHEN** operator input is queued while the project budget is exhausted
- **THEN** its turn can start
- **AND** the resulting run is classified as operator-initiated

#### Scenario: Out-of-band spend can exhaust the budget

- **WHEN** measured turns alone are below the budget and measured turns plus out-of-band calls meet it
- **THEN** the budget is exhausted
- **AND** autonomous turns remain queued

#### Scenario: An automatic checkpoint at exhaustion is not taken, and is reported due

- **WHEN** a conversation crosses its automatic checkpoint threshold while the budget is exhausted
- **THEN** no model is invoked
- **AND** no checkpoint is created, so no later checkpoint anchors on one without a body
- **AND** the operator is told a checkpoint is due, as when checkpoints are not automatic

#### Scenario: A handover at exhaustion keeps the author's notes

- **WHEN** a flow handover with notes for the reviewer completes while the budget is exhausted
- **THEN** no model is invoked and no checkpoint is created
- **AND** the notes remain pending for the next handover

#### Scenario: A title is not generated at exhaustion

- **WHEN** a turn completes in a project that generates conversation titles and the budget is exhausted
- **THEN** no model is invoked for the title
- **AND** the conversation keeps its truncated title

#### Scenario: An operator's checkpoint still runs at exhaustion

- **WHEN** the operator requests a checkpoint while the budget is exhausted
- **THEN** the checkpoint call starts
- **AND** its tokens are added to the project's usage

## ADDED Requirements

### Requirement: Every model call the Hub makes for a project is recorded

Every model invocation the Hub starts on a project's behalf outside an agent turn SHALL be recorded with its purpose, runner, model, outcome and reported usage, including a call that ended before a model was invoked.

A call that leaves no record cannot be totalled, budgeted or explained. The conversation titler is
such a call, and it SHALL be recorded like every other out-of-band call.

#### Scenario: A generated title is recorded

- **WHEN** the Hub generates a conversation title with a model
- **THEN** a record of that call exists with its runner, model, outcome and reported usage

#### Scenario: A call that did not start is recorded with its reason

- **WHEN** an out-of-band call does not start because its provider, its model or the budget refused it
- **THEN** a record of that call exists stating why it did not start
