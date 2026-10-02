## Purpose

Define durable per-turn token accounting, runner-neutral usage aggregation, honest allowance and
API-equivalent presentation, and project budgets that pause autonomous work without preventing
operator control.

## Requirements

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
token-count telemetry, OpenCode completed-step telemetry, and GitHub Copilot per-call and
per-prompt telemetry without changing the separate context-window meter semantics. Malformed
telemetry SHALL degrade to an unavailable accounting outcome rather than failing the run.

A Copilot run's tokens SHALL be measured two ways. One is the sum of its per-call usage events,
each call counted once, including calls made by subagents and the model call of a compaction. The
other is the per-prompt usage its own process reported. Copilot's per-prompt usage is cumulative
within a process, so a later prompt result SHALL replace an earlier one from the same process, and
usage a process reported for an earlier run SHALL NOT be charged to this one. Each figure is a
lower bound, so the run SHALL record the one with the larger total. The two SHALL NOT be added
together. Copilot reports input tokens inclusive of cache reads, so cache reads SHALL NOT be added
to its input or total again.

#### Scenario: Claude final result is authoritative

- **WHEN** a Claude stream contains partial assistant usage followed by final result usage
- **THEN** the final result usage is the turn's accounting outcome
- **AND** partial samples are not added as additional turns

#### Scenario: Codex and OpenCode dimensions normalize

- **WHEN** Codex or OpenCode reports input, output, cache, or reasoning dimensions
- **THEN** the dimensions are retained in the normalized accounting record
- **AND** cache or reasoning subsets are not double-counted in the total

#### Scenario: A Copilot run sums its calls once

- **WHEN** a Copilot run reports three model calls and a prompt result whose cumulative usage equals
  their sum
- **THEN** the run's recorded tokens equal the sum of the three calls
- **AND** the prompt result's usage is not added to them

#### Scenario: A later cumulative result replaces an earlier one

- **WHEN** one Copilot process reports two prompt results, the later of which includes the earlier
- **THEN** the run records the later result
- **AND** does not add the two together

#### Scenario: Lost Copilot call events do not under-count the run

- **WHEN** a Copilot run's per-call events sum to less than its process's cumulative prompt usage
- **THEN** the run records the cumulative usage
- **AND** does not add the per-call sum to it

#### Scenario: Copilot cache reads are not counted twice

- **WHEN** a Copilot call reports input tokens that include cache-read tokens
- **THEN** the recorded total is input plus output
- **AND** the cache-read tokens are retained as a breakdown only

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
"API-equivalent estimate" and MUST NOT be described as an amount charged. The system MUST NOT
invent a monetary figure from a model price catalog.

A monetary figure summed over turns SHALL state how many of those turns reported no cost and are
therefore not in it. A figure that leaves out any turn MUST NOT be presented as though it covered
them all.

#### Scenario: Allowance takes display precedence

- **WHEN** the latest accounting telemetry includes both rate-limit allowance and monetary data
- **THEN** the preferred display is the allowance

#### Scenario: Monetary telemetry is explicitly derived

- **WHEN** runner-reported monetary telemetry is displayed without allowance
- **THEN** it is labelled "API-equivalent estimate"
- **AND** it is not labelled spend, bill, or amount charged

#### Scenario: An estimate that leaves out turns says how many

- **WHEN** a project's turns include some that reported a cost and some that did not
- **THEN** the monetary figure is the sum of the reported costs
- **AND** the presentation states how many turns reported no cost and are not included

#### Scenario: A turn with no reported cost is not priced from its tokens

- **WHEN** a runner reports token usage for a turn but no cost
- **THEN** no monetary value is computed for that turn
- **AND** the turn is counted among those the monetary figure does not include

### Requirement: A project token budget pauses autonomy but not the operator

The system SHALL allow an operator to configure a positive token budget per project or disable it.
When measured project usage is greater than or equal to the configured budget, autonomous turns
SHALL remain queued and SHALL NOT start. Operator-initiated turns SHALL remain available and SHALL
still be accounted.

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

### Requirement: A Copilot turn's AI credits and premium requests are recorded and shown, and are not budgeted

The system SHALL record, for every Copilot run that reports them, the AI credits and premium requests that run consumed, and SHALL show them as information beside the tokens, while the token total remains the only quantity counted against a project's budget.

Copilot reports its credit total as a session-wide running total, and each model call's own credit
cost. A run's credits SHALL be the larger of two lower bounds. One is the session total at the run's
end minus the total the previous run of the same provider session recorded, or minus zero when the
run created the session. The other is the sum of the run's own per-call credit costs. When the
difference cannot be taken, is negative, or is smaller than that sum, the run SHALL be charged the
sum, and its premium requests SHALL be unknown. When Copilot reported neither, the run's credits
SHALL be unknown. The run SHALL record the session total it ended at, so that the next run can take
its own difference. A run charged its per-call sum from a known starting total, with no session
total reported, SHALL record the total it thereby reached, so that the next run does not charge the
same credits again. The previous run SHALL be the one whose record was written last, not the one
with the latest clock time, so that a clock that steps backwards cannot make an older total the
baseline. A negative credit or premium-request figure reported by Copilot SHALL be ignored. No run
SHALL be charged negative credits, and no credit SHALL be charged to two runs.

Credits SHALL be stored in the unit Copilot reports them in, and SHALL be presented as AI credits.
They are the provider's own report of what the run consumed, not a monetary figure, and so are not
the runner-reported monetary figure that allowance and currency presentation governs. They SHALL NOT
be converted into a monetary figure, SHALL NOT be added to any token total, and SHALL NOT count
toward a project's token budget or its exhaustion, including the budget check that gates the
scheduling of a turn. A screen that shows no credits for a project, agent, conversation or turn that
reported none SHALL look as it did before credits existed. The accounting responses SHALL carry the
credit and premium-request fields for every project, empty when none were reported, so a project
with no Copilot runs gains those empty fields and is otherwise unchanged.

#### Scenario: A Copilot turn shows its credits beside its tokens

- **WHEN** a Copilot run reports its usage and its session's credit total
- **THEN** the run's accounting record carries its tokens and its credits
- **AND** the turn, its conversation, its agent and the project each show the credits beside their
  tokens

#### Scenario: A resumed session is charged only its own difference

- **WHEN** a Copilot run resumes a session whose previous run ended at one credit total
- **AND** it ends at a higher total
- **THEN** it is charged the difference between the two totals

#### Scenario: Credits do not count against the budget

- **WHEN** a project has a token budget and a Copilot run reports credits
- **THEN** the budget's used amount includes the run's tokens
- **AND** does not include its credits

#### Scenario: A reset session total is not negative spend

- **WHEN** a Copilot run ends at a session credit total lower than its baseline
- **THEN** the run is charged the sum of its own per-call credit costs, and its premium requests are
  unknown
- **AND** the total it ended at becomes the next run's baseline

#### Scenario: A session total that restarted does not under-charge the run

- **WHEN** a Copilot run resumes a session and ends at a session credit total above its baseline
- **AND** the difference is smaller than the sum of the run's own per-call credit costs
- **THEN** the run is charged the per-call sum, not the difference

#### Scenario: Credits charged without a session total are not charged again

- **WHEN** a Copilot run that created its session reports per-call credit costs but no session
  credit total
- **AND** the next run of that session ends at a session credit total
- **THEN** the first run is charged the sum of its per-call costs
- **AND** the next run is charged only the session total minus that sum

#### Scenario: A project with no Copilot runs is unchanged

- **WHEN** a project's runs are all Claude or Codex runs
- **THEN** no screen shows a credits figure
- **AND** the accounting responses report the project's credits and premium requests as empty

#### Scenario: A clock that steps backwards does not double-charge

- **WHEN** a Copilot session's runs are recorded in order, and the clock stepped backwards between
  two of them
- **THEN** each run's baseline is the total recorded by the run written just before it
- **AND** no credit is charged to two runs

#### Scenario: Credits do not gate the scheduling of a turn

- **WHEN** a project's token budget is not yet spent by its tokens
- **AND** its Copilot runs reported credits whose count exceeds that budget
- **THEN** the project's budget is not exhausted and its turns are still scheduled
