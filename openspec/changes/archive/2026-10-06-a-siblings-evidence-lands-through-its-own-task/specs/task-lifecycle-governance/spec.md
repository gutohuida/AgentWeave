## ADDED Requirements

### Requirement: Another task's evidence lands through that task's own approval
Accepted evidence recorded by a different task SHALL count toward a task's merge targets, and toward its refusal for evidence awaiting a decision, only once that recording task is `approved`; evidence recorded by the task itself, or recorded with no task, SHALL count as before.

Accepting a piece of evidence SHALL NOT merge it through an approved task other than the one that recorded it while the recording task is not `approved`. The recording task's own approval, with its review and its checks, is what lands it.

#### Scenario: Accepting a sibling's evidence does not land it
- **WHEN** two tasks serve the same requirement, the first is approved and merged, and the operator accepts evidence the second recorded while the second is `under_review`
- **THEN** the second task's commit is not on the main branch
- **AND** no integration of the first task names that commit

#### Scenario: The sibling's own approval lands it
- **WHEN** that second task is then approved
- **THEN** its commit is merged into the main branch, recorded under the second task
