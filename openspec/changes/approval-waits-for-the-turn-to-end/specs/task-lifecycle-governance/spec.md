## ADDED Requirements

### Requirement: Approval is refused while the work is still being produced

The system SHALL refuse the transition into `approved` while the task has a live turn, meaning a run bound to that task whose process is still alive.

A task's work is not knowable while its turn is live. An agent records `completed` during its turn; the commit that holds its edits is made when the turn ends. Between those two moments the task's branch points at the commit it was cut from, and every question of the form *"which commit is this task's work?"* is answered with a commit that contains none of it. Approving there records that the work is good, merges nothing, and reports the nothing as a fact no retry can alter — so the task reads `approved` while its work sits unmerged and no surface offers a remedy.

The refusal SHALL be carried in the same typed refusal that reports unverified requirements and unmergeable work, and SHALL name the agent whose turn is still running. An operator learning that approval was refused SHALL learn from the same response what it is waiting for.

The refusal SHALL clear itself. It states a fact about a moment, not a defect in the work, so it SHALL require no operator action beyond waiting for the turn to end.

Liveness SHALL be determined by testing the run's process, not by reading its recorded status alone. A run whose process died leaves its recorded status unchanged until the Hub next starts, so a refusal reading only that status would outlive the turn it describes and block approval indefinitely.

This refusal SHALL be independent of the rigor of any document the task's requirements belong to, for the same reason the unmergeable refusal is: rigor is a claim about how well work must be proven, and this is a claim about whether the work yet exists to be put anywhere.

#### Scenario: An approval inside the turn is refused

- **WHEN** a task is moved to `approved` while the agent that completed it still has a running turn bound to that task
- **THEN** the transition is refused
- **AND** the task's status is unchanged
- **AND** no integration is attempted or recorded

#### Scenario: The refusal names what it is waiting for

- **WHEN** approval is refused because the turn is still live
- **THEN** the refusal names the agent whose turn is running
- **AND** it is carried in the same typed refusal that reports unverified requirements

#### Scenario: The refusal clears when the turn ends

- **WHEN** the same task is approved after its turn has ended
- **THEN** the transition is permitted
- **AND** the commit that holds the turn's work is what integration merges

#### Scenario: A run whose process died does not block approval

- **WHEN** a task's most recent run is still recorded as running but its process is no longer alive
- **THEN** approval is not refused on account of that run

#### Scenario: A task with no run is unaffected

- **WHEN** a task with no run bound to it is approved
- **THEN** approval proceeds exactly as it did before this requirement

#### Scenario: Rigor does not exempt the refusal

- **WHEN** a task whose linked requirements belong to a `sketch`-rigor document is approved while its turn is live
- **THEN** the transition is refused on the same terms as it would be for a `gate`-rigor document
