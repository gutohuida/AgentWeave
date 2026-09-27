## MODIFIED Requirements

### Requirement: Supported runner telemetry normalizes to one accounting shape

The system SHALL normalize Claude Code result usage and model usage, Codex completed-turn and
token-count telemetry, OpenCode completed-step telemetry, and GitHub Copilot per-call and
per-prompt telemetry without changing the separate context-window meter semantics. Malformed
telemetry SHALL degrade to an unavailable accounting outcome rather than failing the run.

A Copilot run's tokens SHALL be the sum of its per-call usage events, each call counted once,
including calls made by subagents and the model call of a compaction. Copilot's per-prompt usage is
cumulative for its session within a process, so it SHALL be used only as the difference from the
previous prompt result in that process, and only as a cross-check or a replacement for per-call
events that were lost. The two figures SHALL NOT be added together. Copilot reports input tokens
inclusive of cache reads, so cache reads SHALL NOT be added to its input or total again.

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

#### Scenario: A Copilot run's cumulative usage is differenced

- **WHEN** a second prompt in the same Copilot process reports cumulative usage that includes the
  first prompt
- **THEN** the second run is charged only the difference from the first prompt's result

#### Scenario: Lost Copilot call events do not under-count the run

- **WHEN** a Copilot run's per-call events sum to less than the difference of its cumulative prompt
  usage
- **THEN** the run records the cumulative difference
- **AND** does not add the per-call sum to it

#### Scenario: Copilot cache reads are not counted twice

- **WHEN** a Copilot call reports input tokens that include cache-read tokens
- **THEN** the recorded total is input plus output
- **AND** the cache-read tokens are retained as a breakdown only

## ADDED Requirements

### Requirement: A Copilot turn's AI credits and premium requests are recorded and shown, and are not budgeted

The system SHALL record, for every Copilot run that reports them, the AI credits and premium requests that run consumed, and SHALL show them as information beside the tokens, while the token total remains the only quantity counted against a project's budget.

Copilot reports its credit total as a session-wide running total that survives the session being
resumed. A run's credits SHALL be that total at the run's end minus the total the previous run of
the same provider session ended at, or minus zero when the run created the session. The run SHALL
record the total it ended at, so that the next run can take its own difference. When no difference
can be taken, the run's credits SHALL be the sum of its per-call credit costs where Copilot
reported them, and SHALL otherwise be unknown. A negative difference SHALL be recorded as unknown,
never as negative spend.

Credits SHALL be stored in the unit Copilot reports them in, and SHALL be presented as AI credits.
They SHALL NOT be converted into a monetary figure, SHALL NOT be added to any token total, and SHALL
NOT count toward a project's token budget or its exhaustion. A surface that shows no credits for a
project, agent, conversation or turn that reported none SHALL look as it did before credits existed.

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
- **THEN** the run's credits are recorded as unknown
- **AND** the total it ended at becomes the next run's baseline

#### Scenario: A project with no Copilot runs is unchanged

- **WHEN** a project's runs are all Claude or Codex runs
- **THEN** no surface shows a credits figure
