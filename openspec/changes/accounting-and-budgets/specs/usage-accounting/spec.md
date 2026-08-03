## ADDED Requirements

### Requirement: Every Hub-owned turn has a durable accounting outcome

The system SHALL persist exactly one accounting outcome for every Hub-owned run after that run
ends. When the runner reports usable token telemetry, the outcome SHALL record normalized input,
output, total, cache, and reasoning dimensions when available. When it does not, the outcome SHALL
be explicitly unavailable and MUST NOT represent missing values as zero.

#### Scenario: Reported usage is recorded once per turn

- **WHEN** a runner completes a turn and reports token usage
- **THEN** exactly one measured accounting record is associated with that run
- **AND** its normalized total is available for aggregation

#### Scenario: Missing usage is unavailable

- **WHEN** a runner completes a turn without usable token telemetry
- **THEN** exactly one unavailable accounting record is associated with that run
- **AND** the interface does not display zero tokens for that turn

### Requirement: Supported runner telemetry normalizes to one accounting shape

The system SHALL normalize Claude Code result usage and model usage, Codex completed-turn and
token-count telemetry, and OpenCode completed-step telemetry without changing the separate
context-window meter semantics. Malformed telemetry SHALL degrade to an unavailable accounting
outcome rather than failing the run.

#### Scenario: Claude final result is authoritative

- **WHEN** a Claude stream contains partial assistant usage followed by final result usage
- **THEN** the final result usage is the turn's accounting outcome
- **AND** partial samples are not added as additional turns

#### Scenario: Codex and OpenCode dimensions normalize

- **WHEN** Codex or OpenCode reports input, output, cache, or reasoning dimensions
- **THEN** the dimensions are retained in the normalized accounting record
- **AND** cache or reasoning subsets are not double-counted in the total

### Requirement: Usage aggregates by agent and project

The accounting API SHALL aggregate measured token totals per agent and project and SHALL separately
report measured-turn and unavailable-turn counts. Historical or missing telemetry MUST NOT be
invented.

#### Scenario: Agent totals contribute to the project total

- **WHEN** measured turns exist for more than one agent in a project
- **THEN** each agent summary contains only that agent's usage
- **AND** the project total contains the sum of their measured totals

#### Scenario: Unavailable turns remain visible

- **WHEN** a project contains both measured and unavailable turn outcomes
- **THEN** the aggregate reports both counts
- **AND** the unavailable turn contributes no fabricated token value

### Requirement: Allowance and currency presentation cannot imply billing

When a runner reports remaining rate-limit allowance, the accounting presentation SHALL prefer it
to a monetary figure. Otherwise, any runner-reported monetary figure SHALL be labelled
“API-equivalent estimate” and MUST NOT be described as an amount charged. The system MUST NOT
invent a monetary figure from a model price catalog.

#### Scenario: Allowance takes display precedence

- **WHEN** the latest accounting telemetry includes both rate-limit allowance and monetary data
- **THEN** the preferred display is the allowance

#### Scenario: Monetary telemetry is explicitly derived

- **WHEN** runner-reported monetary telemetry is displayed without allowance
- **THEN** it is labelled “API-equivalent estimate”
- **AND** it is not labelled spend, bill, or amount charged

### Requirement: A project token budget pauses autonomy but not the operator

The system SHALL allow an operator to configure a positive token budget per project or disable it. When measured project
usage is greater than or equal to the configured budget, autonomous turns SHALL remain queued and
SHALL NOT start. Operator-initiated turns SHALL remain available and SHALL still be accounted.

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

### Requirement: The operator can see accounting and exhaustion state

The interface SHALL show the project's measured token total and budget state, SHALL distinguish
unavailable usage from zero, and SHALL state when exhausted budget has paused autonomous work while
operator input remains available.

#### Scenario: Exhausted state explains retained control

- **WHEN** project usage meets or exceeds its configured budget
- **THEN** the interface states that autonomous turns are paused
- **AND** it states that operator messages can still run
