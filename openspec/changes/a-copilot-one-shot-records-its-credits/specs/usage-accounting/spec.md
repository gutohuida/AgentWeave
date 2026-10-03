## ADDED Requirements

### Requirement: A Copilot one-shot call records the credits its session reported
The system SHALL record, for every Copilot one-shot call (a checkpoint, its probe, or any other Hub-owned `copilot -p` call that writes an invocation record) whose process exited successfully and whose output carries a session usage checkpoint, the AI credits and premium requests of the last such checkpoint as that call's own charge.

A one-shot call is one process that opens one new session, so the session's final cumulative total
is the call's whole charge. The last checkpoint SHALL be taken, and checkpoints SHALL NOT be summed.
Each figure SHALL be read by the same rule as a Copilot run's session checkpoint: a negative,
non-numeric, boolean or non-finite figure, or a figure larger than 2^53 − 1 (the largest whole
number a floating-point or JavaScript number holds exactly), SHALL be ignored and that figure SHALL
be unknown, while the other figure is still recorded. A later checkpoint whose figure is ignored
SHALL make that figure unknown, not leave an earlier checkpoint's figure in its place. A call whose output carries no checkpoint SHALL record both
figures as unknown, never as zero, and no other part of the output SHALL be used in their place.
The credits SHALL be recorded whether the call produced a usable answer, reported an error, or
produced no answer. A call whose process exited unsuccessfully, timed out or failed to start SHALL
record both figures as unknown: its output is not read. Like a Copilot run's credits, they SHALL NOT be converted into a monetary
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

#### Scenario: A later checkpoint with an ignored figure makes that figure unknown
- **WHEN** a Copilot one-shot call's output carries a checkpoint with valid figures, then a later checkpoint whose credit figure is negative
- **THEN** the call's invocation record carries unknown credits and the later checkpoint's premium requests

#### Scenario: A call whose process did not exit successfully records unknown credits
- **WHEN** a Copilot one-shot call's process exits unsuccessfully, times out, or fails to start
- **THEN** the call's invocation record carries unknown credits and unknown premium requests

## MODIFIED Requirements
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
baseline. A negative credit or premium-request figure reported by Copilot SHALL be ignored, and so SHALL a
session total that is non-numeric, boolean, non-finite or larger than 2^53 − 1; an ignored session
total SHALL make that figure unknown and SHALL NOT make the run fail or lose its tokens. No run
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

#### Scenario: A malformed session total does not fail the run

- **WHEN** a Copilot run that completed reports a session credit total that is non-finite or larger
  than 2^53 − 1, and a valid premium-request total
- **THEN** the run is recorded as completed, with its tokens
- **AND** its session credit total is unknown and its premium-request total is recorded
