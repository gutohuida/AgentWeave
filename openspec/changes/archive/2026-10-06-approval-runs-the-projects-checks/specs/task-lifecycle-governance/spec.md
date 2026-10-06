## ADDED Requirements

### Requirement: Approval is refused unless the project's checks passed on the work it would merge
In a project with checks, the system SHALL refuse a move to `approved` unless the latest check run for that task passed on the current main tip and the current merge targets.

The refusal is a `checks` category of the gate refusal, beside `unmergeable` and `unaccepted`. Its message SHALL:
- for a `failed` run, name each failing check and end with the last lines of its output;
- for a `running` run, or one this request started because the result was missing, stale or
  `interrupted`, say the checks are running and that approval can be retried when they finish;
- for an `error` run (the scratch checkout could not be built), name the error.

The message SHALL end with the reviewer's move: a reviewer sends a failing task back to its author with `revision_needed`. The gate SHALL NOT run a check itself. Only the approval transition and the land route may start a run. Every other caller of the gate (`approval_held_for_operator`, the scheduler, run divergence, the integration preview) reads the recorded result only.

#### Scenario: A failing check refuses approval
- **WHEN** a task's latest run failed and a reviewer requests `approved`
- **THEN** the request is refused with the failing check's name, its output tail and `revision_needed` as the reviewer's move
- **AND** nothing merges

#### Scenario: A passing check lets approval through
- **WHEN** a task's latest run passed on the current main tip and merge targets
- **THEN** approval proceeds and merges as it did before this change

#### Scenario: Asking for approval does not wait for a run
- **WHEN** approval is requested and the result is missing
- **THEN** a run starts, the request is refused as "checks still running", and it answers in under two seconds

#### Scenario: The review briefing does not start a run
- **WHEN** a review turn is briefed for a task with no check result
- **THEN** no run starts

### Requirement: The operator may approve over failing checks with a recorded reason
The operator SHALL be able to approve a task whose checks failed or errored by giving a non-empty reason. The reason SHALL be kept on the approval transition. An agent's request SHALL NOT be able to override checks: any override field it sends is refused. A `running` result is not overridable; the override covers a recorded failure, not an unknown.

#### Scenario: Operator overrides with a reason
- **WHEN** the operator approves a task whose checks failed, giving the reason "flaky on this machine only"
- **THEN** the task is approved and merged, and its transition history shows the reason

#### Scenario: An agent cannot override
- **WHEN** a reviewer agent requests `approved` with an override reason on a task whose checks failed
- **THEN** the request is refused and the task stays in its pre-request status

#### Scenario: No reason, no override
- **WHEN** the operator approves a task whose checks failed without a reason
- **THEN** the request is refused with the failing checks named
