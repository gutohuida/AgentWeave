## MODIFIED Requirements

### Requirement: Approval integrates the approved work

The transition into `approved` SHALL merge the approved work into the project's configured main branch, in the same operation that records the transition. Approval is what places work in the product, and a lifecycle whose terminal state carries no such meaning cannot answer whether anything it approved was ever shipped.

What is merged SHALL be the commit named by the task's accepted evidence footprints — the newest such commit per distinct branch — and SHALL NOT be the agent's branch.

**What actually lands SHALL be the approved task's work and nothing else.** Merging a commit brings that commit's whole ancestry, so naming a commit rather than a branch narrows the tip and nothing more. It is therefore not sufficient for the system to name a commit: the commit's ancestry SHALL correspond to the task, which is what per-task isolation of the work provides. Where a task's work was produced before that isolation existed and sits on a branch shared with other tasks, the system SHALL record which commits landed alongside it rather than claiming none did.

Evidence that is awaiting review or has been rejected SHALL NOT contribute a commit to integrate.

The merge SHALL be performed against the local repository only. The system SHALL NOT contact any remote, SHALL NOT push, and SHALL NOT require any credential.

Integration SHALL occur regardless of the rigor of any document the task's requirements belong to. Rigor governs who may bring a task to `approved`; integration is what reaching `approved` means. Were the two coupled, lowering a document's rigor to get past a blocked task would also silently stop that work being shipped.

#### Scenario: Approving a task puts its work on the main branch

- **WHEN** a task with accepted evidence naming a git commit is approved, and the project has a
  configured main branch
- **THEN** that commit is merged into the main branch
- **AND** coverage reports the served requirements as `integrated` rather than
  `verified, not integrated`

#### Scenario: Only the accepted evidence's commit is integrated

- **WHEN** a task is approved whose branch carries commits made after the commit its accepted
  evidence names
- **THEN** the later commits are not merged

#### Scenario: Another task's work does not land

- **WHEN** a task is approved while a different task, held by the same agent, has unreviewed commits
- **THEN** none of that other task's commits are on the main branch
- **AND** the integration record names no commits as having ridden along

#### Scenario: The approved task's own earlier work does land

- **WHEN** a task is approved whose work is several commits, the newest of which its accepted
  evidence names
- **THEN** every one of those commits is on the main branch

#### Scenario: A sketch document's task still integrates

- **WHEN** a task whose linked requirements belong to a `sketch`-rigor document is approved
- **THEN** the work is integrated exactly as it would be for a `gate`-rigor document

#### Scenario: No remote is contacted

- **WHEN** any approval integrates work
- **THEN** no push occurs and no remote operation is attempted

## ADDED Requirements

### Requirement: A finished task's checkout is released, and its branch is not

A task's isolated checkout SHALL be released when the task reaches a terminal status, and its branch SHALL NOT be removed.

Releasing the checkout is what bounds how much of a repository the system occupies. Agents are bounded by the roster; tasks are bounded by nothing, so a checkout per task that is never released grows without limit, and the first symptom would be a git failure in an unrelated turn.

Release SHALL follow the same discipline as releasing any working checkout: any uncommitted change SHALL be committed onto the task's branch first, the branch SHALL be kept, and commits the branch carries beyond the main line SHALL be reported rather than discarded. Nothing an agent produced is destroyed by a release.

Release SHALL happen after the transition's own integration has run, so that what integration merges is never affected by what release commits.

Release SHALL NOT be able to fail a transition. A checkout that cannot be removed is a condition to report, not a reason to reverse a judgement about whether work was good — the same rule integration already follows.

Because a terminal status can be left again, a task whose work resumes SHALL have its checkout re-provisioned with its previous work present. That is what keeping the branch is for.

A task's terminal status SHALL be the only thing that releases its checkout. Removing from the roster the agent that was working a task SHALL release that agent's own checkout and SHALL NOT release the task's. A task outlives whoever held it: its status is unchanged by a roster edit, another agent may be assigned to continue it, and releasing its checkout would take the working tree away from a task for a reason that says nothing about the task. The work would survive on the branch either way — this is about not making a roster edit act on the task lifecycle.

#### Scenario: Removing an agent leaves the checkouts of its tasks alone

- **WHEN** an agent holding a task with its own checkout is removed from the roster
- **THEN** the agent's own checkout is released
- **AND** the task's checkout still exists, and the task's status is unchanged

#### Scenario: An approved task's checkout is released

- **WHEN** a task is approved
- **THEN** its checkout directory no longer exists
- **AND** its branch still exists, at the same commit

#### Scenario: A rejected task's work survives its release

- **WHEN** a task is rejected
- **THEN** its checkout directory no longer exists
- **AND** every commit made on its branch is still reachable

#### Scenario: Integration is unaffected by release

- **WHEN** a task with accepted evidence naming a commit is approved
- **THEN** the commit merged into the main branch is the one the evidence names, not one created
  while releasing the checkout

#### Scenario: A reopened task gets its work back

- **WHEN** an approved task is moved to `revision_needed` and worked again
- **THEN** its checkout is provisioned again, containing the work it had before it was released

#### Scenario: A release that fails does not undo the transition

- **WHEN** releasing a task's checkout fails
- **THEN** the task is still in its terminal status
- **AND** the failure is recorded
