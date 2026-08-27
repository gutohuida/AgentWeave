## ADDED Requirements

### Requirement: A task's checkout carries the work it depends on

A task's isolated checkout SHALL contain the work of every prerequisite the task was permitted to start on, whether or not that work reached the project's main branch.

A dependency is met at `approved`, and approval attempts integration — but integration is best-effort and never blocks an approval, so a prerequisite can be `approved` with its work not on the main branch: the project may have no main branch named, the accepted evidence may name no commit at all, the operator's own checkout may be mid-edit or parked elsewhere, or the merge may have failed outright. Isolating work per task removes the accident that used to cover this, which was that a dependent held by the same agent inherited the prerequisite's commits because it was literally the same branch.

The checkout SHALL be created from the branch approved work is integrated into, and each direct prerequisite's accepted evidence commit that is not already contained SHALL then be brought in. A prerequisite whose accepted evidence names no commit contributes nothing, because there is no commit to bring; that is a supported project shape, not a failure.

Where a prerequisite's work cannot be brought in without conflict, the turn SHALL NOT start, and the refusal SHALL name the prerequisite. Starting an agent on a checkout that silently lacks what it was told to build on produces work against the wrong base and evidence that describes a tree nobody reviewed.

#### Scenario: A prerequisite that was approved but not integrated

- **WHEN** a task starts whose prerequisite is approved and whose work did not reach the main branch
- **THEN** the task's checkout contains that prerequisite's work

#### Scenario: A prerequisite whose work is already in the main line

- **WHEN** a task starts whose prerequisite's work was integrated into the main branch
- **THEN** the task's checkout contains that work once, not twice

#### Scenario: A prerequisite that demonstrated no commit

- **WHEN** a task starts whose prerequisite's accepted evidence names paths rather than a commit
- **THEN** the checkout is created without refusing the turn

#### Scenario: A prerequisite that cannot be brought in

- **WHEN** bringing a prerequisite's work into a new task checkout conflicts
- **THEN** the turn does not start
- **AND** the reason names the prerequisite whose work could not be brought in
