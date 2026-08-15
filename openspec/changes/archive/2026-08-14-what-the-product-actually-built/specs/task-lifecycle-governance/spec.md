# task-lifecycle-governance

## ADDED Requirements

### Requirement: Work already in the main line is not reported as merged

Where the work to integrate is already reachable from the target branch, the system SHALL record the
integration as skipped, naming that as the reason, and SHALL NOT record it as merged.

Merging a commit that is already an ancestor of the target succeeds, reports success, and changes
nothing. Recording that as a merge makes a no-op indistinguishable from work reaching the product,
which is the one thing integration reporting exists to distinguish.

This SHALL be determined before any precondition concerning the state of the working tree. Whether a
commit is already present is a fact about the commit and the target alone, and an operator whose
checkout is mid-edit is better told the true reason than told to tidy up for a merge that would
change nothing.

#### Scenario: An already-integrated commit is skipped

- **WHEN** a task is approved whose accepted evidence names a commit already reachable from the
  target branch
- **THEN** the integration is recorded as skipped
- **AND** the reason states the work is already in the target branch
- **AND** the target branch is unchanged

#### Scenario: The true reason wins over a working-tree complaint

- **WHEN** the commit is already in the target branch and the project's checkout also has
  uncommitted changes
- **THEN** the reason given is that the work is already integrated

### Requirement: Approval creates the work its document declares

A document's approval SHALL create the tasks that document declares, each linked to the requirements
it declares that it serves.

A document that declares its own decomposition and produces nothing leaves the operator to
re-describe by hand work the document already contains, and leaves no relationship between the two.

Tasks SHALL be created unassigned and in the lifecycle's entry status. The document states that the
work exists; who performs it is not a decision a specification makes.

Creation SHALL be idempotent per document and declared task, so that re-approving a document after
revision creates only what is new.

A task that already exists for a declared task SHALL NOT be modified, reassigned or reverted by a
later approval. The document declares that work exists, not what has happened to it since.

A document declaring no tasks SHALL create none, and this SHALL NOT be an error.

Where a declared task names a requirement the document does not resolve, the task SHALL still be
created and the unresolved reference SHALL be preserved rather than discarded.

#### Scenario: Approving a document creates its declared tasks

- **WHEN** a document declaring tasks is approved
- **THEN** a task is created for each declared task
- **AND** each is linked to the requirements it declared it serves
- **AND** each is unassigned

#### Scenario: Re-approving creates no duplicates

- **WHEN** a document is revised and approved again
- **THEN** tasks already created for its declared tasks are not duplicated
- **AND** tasks declared for the first time are created

#### Scenario: Work already under way is left alone

- **WHEN** a document is approved again after a task it declared has been moved out of its entry
  status
- **THEN** that task's status and assignee are unchanged

#### Scenario: A document declaring no tasks creates none

- **WHEN** a document declaring no tasks is approved
- **THEN** no tasks are created
- **AND** the approval succeeds
