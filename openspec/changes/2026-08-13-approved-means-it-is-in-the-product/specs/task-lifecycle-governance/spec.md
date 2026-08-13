# task-lifecycle-governance

## ADDED Requirements

### Requirement: Approval integrates the approved work

The transition into `approved` SHALL merge the approved work into the project's configured main
branch, in the same operation that records the transition. Approval is what places work in the
product, and a lifecycle whose terminal state carries no such meaning cannot answer whether anything
it approved was ever shipped.

What is merged SHALL be the commit named by the task's accepted evidence footprints — the newest
such commit per distinct branch — and SHALL NOT be the agent's branch. Agent branches are per agent,
not per task, so merging a branch would integrate every other task's work that happens to sit beside
the approved one.

Evidence that is awaiting review or has been rejected SHALL NOT contribute a commit to integrate.

The merge SHALL be performed against the local repository only. The system SHALL NOT contact any
remote, SHALL NOT push, and SHALL NOT require any credential.

Integration SHALL occur regardless of the rigor of any document the task's requirements belong to.
Rigor governs who may bring a task to `approved`; integration is what reaching `approved` means. Were
the two coupled, lowering a document's rigor to get past a blocked task would also silently stop that
work being shipped.

#### Scenario: Approving a task puts its work on the main branch

- **WHEN** a task with accepted evidence naming a git commit is approved, and the project has a
  configured main branch
- **THEN** that commit is merged into the main branch
- **AND** coverage reports the served requirements as `integrated` rather than
  `verified, not integrated`

#### Scenario: Only the accepted evidence's commit is integrated

- **WHEN** a task is approved whose agent branch carries commits made after the commit its accepted
  evidence names
- **THEN** the later commits are not merged

#### Scenario: A sketch document's task still integrates

- **WHEN** a task whose linked requirements belong to a `sketch`-rigor document is approved
- **THEN** the work is integrated exactly as it would be for a `gate`-rigor document

#### Scenario: No remote is contacted

- **WHEN** any approval integrates work
- **THEN** no push occurs and no remote operation is attempted

### Requirement: Approval is refused when the work cannot be merged cleanly

Where the work to be integrated would conflict with the project's main branch, the system SHALL
refuse the transition into `approved`.

The conflict SHALL be detected before the transition is recorded, by a test merge that modifies
neither the working tree nor the index. A conflict discovered during the merge itself would leave a
task recorded as approved and a repository in a state the operator did not ask for.

The refusal SHALL be carried in the same typed refusal that reports unverified requirements, and
SHALL name the conflicting paths. An operator learning that approval failed SHALL learn why in the
same response, not by inspecting the repository.

This refusal SHALL apply regardless of rigor. It is not an assertion about whether the work is
verified; it is an assertion that the work cannot go where approval says it goes.

The check SHALL live inside the single transition service, and SHALL NOT introduce a second
enforcement point.

#### Scenario: A conflicting branch refuses approval

- **WHEN** approval is requested for a task whose evidence commit conflicts with the main branch
- **THEN** the transition is refused
- **AND** the refusal names the conflicting paths
- **AND** the task's status is unchanged
- **AND** no merge is attempted

#### Scenario: A conflict refuses approval even at sketch rigor

- **WHEN** approval is requested for a task with conflicting work whose documents are all `sketch`
- **THEN** the transition is refused

### Requirement: An integration that cannot proceed does not block approval

The transition into `approved` SHALL still succeed where integration cannot be attempted, and the
integration SHALL be recorded as skipped together with the reason. Integration cannot be attempted
when the project has no configured main branch, when the project is not a repository, when the
primary checkout has uncommitted changes, or when the primary checkout is not on the main branch.

Where integration is attempted and fails, the transition SHALL NOT be rolled back. The approval is a
judgement that the work is good; a repository failure SHALL NOT reverse it. Coverage SHALL then
report the requirement as `verified, not integrated`, which is a true statement of what happened.

A project that is not a repository SHALL be no less approvable than before this capability existed.

#### Scenario: An unconfigured main branch does not block approval

- **WHEN** a task is approved in a project with no configured main branch
- **THEN** the approval succeeds
- **AND** nothing is merged
- **AND** the skipped integration is recorded with its reason

#### Scenario: A dirty primary checkout skips rather than merges

- **WHEN** a task is approved while the primary checkout has uncommitted changes
- **THEN** the approval succeeds, no merge is attempted, and the reason is recorded

#### Scenario: A failed merge leaves the approval standing

- **WHEN** integration is attempted and the merge fails
- **THEN** the task remains `approved`
- **AND** coverage reports the served requirements as `verified, not integrated`

#### Scenario: A project without a repository approves unchanged

- **WHEN** a task is approved in a project whose evidence footprints record paths rather than commits
- **THEN** the approval succeeds and no integration is attempted

### Requirement: Every integration attempt is recorded

The system SHALL record each integration attempt: the task, the commit and branch integrated, the
target branch, the outcome (`merged`, `skipped` or `failed`), the reason where it did not merge, the
approving actor, and the time.

The record SHALL be append-only, with no update path and no delete path. An integration is a write to
the operator's repository performed by the system, and the account of what was written SHALL NOT be
editable by the thing that wrote it.

The record SHALL state how the integration was performed, so that a later mode which integrates by a
different mechanism is distinguishable in the history rather than conflated with this one.

#### Scenario: A merge is recorded with what it merged

- **WHEN** an approval integrates work
- **THEN** a record names the commit, the source branch, the target branch, the outcome and the
  approving actor

#### Scenario: Integration records cannot be altered

- **WHEN** any interface attempts to update or delete an integration record
- **THEN** no such path exists
