## MODIFIED Requirements

### Requirement: Approval integrates the approved work

The transition into `approved` SHALL merge the approved work into the project's configured main branch, in the same operation that records the transition. Approval is what places work in the product, and a lifecycle whose terminal state carries no such meaning cannot answer whether anything it approved was ever shipped.

What is merged SHALL be the commits named by the task's accepted evidence footprints — per line of work, the commit that contains the others (the most recently recorded where neither contains the other), and among footprints that name no line of work, every commit no other of them contains — and SHALL NOT be the agent's branch. The rule is stated in full by spec-document-authority's *Within one line of work the later commit is the one merged*. Choosing the most recently recorded commit per branch let a later footprint of an older commit displace newer work, and treated footprints naming no line of work as one branch, dropping unrelated accepted work.

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
