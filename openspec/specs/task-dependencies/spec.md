# task-dependencies Specification

## Purpose
TBD - created by archiving change task-dependencies. Update Purpose after archive.
## Requirements
### Requirement: A document declares the order of its own tasks

A specification document's declared tasks SHALL be able to name other tasks in the same document that
must finish before they may begin, referenced by the task key the document already assigns.

A decomposition without order is a claim that every piece of work can start at once, which is almost
never true. Approving one produced a board of tasks all appearing ready, leaving the operator to hold
the real order in their head and the agents to discover it by collision.

Task keys are already stable handles unique within a document and are already kept across rewordings,
so a dependency SHALL be expressed with them rather than with a new identifier.

#### Scenario: A declared dependency becomes an edge on the board

- **WHEN** a document declaring a task that depends on a sibling task is approved
- **THEN** both tasks are created
- **AND** the dependency between them is recorded

#### Scenario: A dependency naming an unknown key is reported

- **WHEN** a submitted document declares a dependency on a key that no task in the document defines
- **THEN** the submission is accepted
- **AND** the unresolved key is reported as blocking a proposal

#### Scenario: A cycle within a document is reported

- **WHEN** a submitted document declares tasks whose dependencies form a cycle
- **THEN** the submission is accepted
- **AND** the cycle is reported as blocking a proposal

#### Scenario: A document declaring no dependencies behaves as before

- **WHEN** a document declaring tasks with no dependencies is approved
- **THEN** the tasks are created with no dependency recorded
- **AND** none of them is prevented from starting

### Requirement: An unmet dependency prevents starting and nothing else

A task SHALL NOT be moved to in-progress while any task it depends on is not yet approved. A task
with unmet dependencies SHALL still be assignable, and SHALL still be rejectable.

Being unable to start and having stopped are different states, and the task lifecycle already
distinguishes them: a task nobody has started is pending, and the status meaning "stopped" is
reachable only from in-progress and denotes work waiting on something a person must supply. A
dependency is a precondition on the act of starting, not a property the task carries.

Assignability is deliberate: it is what allows an entire wave of work to be assigned in advance, with
each task starting when its own prerequisites clear.

#### Scenario: Starting is refused while a prerequisite is unapproved

- **WHEN** a task whose prerequisite is not approved is moved to in-progress
- **THEN** the move is refused
- **AND** the refusal names the prerequisite that is not met

#### Scenario: Assignment is permitted while a prerequisite is unapproved

- **WHEN** a task whose prerequisite is not approved is assigned to an agent
- **THEN** the assignment succeeds

#### Scenario: Rejection is permitted while a prerequisite is unapproved

- **WHEN** the operator rejects a task whose prerequisite is not approved
- **THEN** the rejection succeeds

#### Scenario: Starting succeeds once every prerequisite is approved

- **WHEN** the last unapproved prerequisite of a task becomes approved
- **THEN** that task may be moved to in-progress

#### Scenario: Resuming is gated the same way as starting

- **WHEN** a task that had stopped is resumed, and a prerequisite is not approved
- **THEN** the resumption is refused

### Requirement: A dependency is met at approval, not at completion

A dependency SHALL count as met only when the task depended upon has reached approved.

Completion is the author's claim that work is done; approval is a second party's agreement that it
is. Advancing on completion would let each wave build on work that has not been reviewed and may be
sent back, and the product's review separation exists because that distinction is worth enforcing.

A consequence follows and is intended: because approval is also where a task's requirement coverage
is judged, a chain of dependent work cannot advance past work whose requirements are unverified.

A second consequence follows and must be accommodated rather than resisted: every wave passes through
review, and review requires a party other than the author.

#### Scenario: A completed but unreviewed prerequisite does not release its dependent

- **WHEN** a prerequisite reaches completed and has not been approved
- **THEN** its dependent still cannot be started

#### Scenario: An approved prerequisite releases its dependent

- **WHEN** a prerequisite reaches approved
- **THEN** its dependent may be started

### Requirement: A dependency that regresses after a dependent has started does not halt it

Where a task depended upon leaves approved after a dependent has already started, the dependent SHALL
continue, and the situation SHALL be surfaced.

The gate is a precondition evaluated when work starts, not an invariant maintained while it runs.
Halting a running task would take work away from an agent mid-turn on the strength of a change to a
different task, which is a larger intervention than the situation warrants and one nothing can undo
cleanly.

#### Scenario: A running dependent is not stopped

- **WHEN** an approved prerequisite is moved back to a state needing revision, and its dependent is
  already in progress
- **THEN** the dependent's status is unchanged

#### Scenario: The regression is visible

- **WHEN** a dependent is running on a prerequisite that has left approved
- **THEN** that situation is reported against the dependent

### Requirement: A dependency on rejected work is surfaced, never resolved

Where a task depends on a task that has been rejected, the Hub SHALL report that the dependent is
gated on rejected work and SHALL NOT release, reject, or otherwise resolve the dependent on the
operator's behalf.

A rejected task will never reach approved, so its dependents can never start, and the transition out
of rejected is the operator's alone. That is a decision — reopen the rejected work, or change the
document so the dependency no longer exists — and both answers are sometimes right.

Propagating rejection to dependents is refused: one rejection would cascade through a decomposition
without the operator seeing it happen. Treating rejected as met is refused: a task would become
startable because its prerequisite was abandoned.

#### Scenario: A dependent of rejected work cannot start

- **WHEN** a task whose prerequisite has been rejected is moved to in-progress
- **THEN** the move is refused

#### Scenario: The rejected prerequisite is named

- **WHEN** a task is gated on a rejected prerequisite
- **THEN** the report names the rejected task

#### Scenario: Rejection does not propagate

- **WHEN** a task with dependents is rejected
- **THEN** the status of its dependents is unchanged

### Requirement: A dependency may name a task in another document, by importing it

A document SHALL be able to declare a task belonging to another document as an entry of its own,
marked as imported, so that its local tasks may depend on it using a local key.

Work crosses documents. Expressing that with a qualified reference inside the dependency field would
give one field two grammars; declaring the foreign task as an entry keeps dependencies a list of
local keys, makes the dependency visible to a reader of the document rather than only to a screen,
and keeps a per-document view able to lay itself out without consulting another document.

An imported entry SHALL resolve to the existing task and SHALL NOT create one. An import whose
referenced task cannot be found SHALL be preserved and reported rather than dropped.

#### Scenario: A local task depends on an imported one

- **WHEN** a document declaring an imported entry and a local task depending on it is approved
- **THEN** the local task is created
- **AND** its dependency is recorded against the existing foreign task

#### Scenario: An import creates no task

- **WHEN** a document declaring an imported entry is approved
- **THEN** no new task is created for that entry

#### Scenario: An unresolvable import is preserved and reported

- **WHEN** an imported entry names a task that cannot be found
- **THEN** the reference is preserved
- **AND** it is reported

### Requirement: An import may name only an approved document

An imported entry SHALL name a document that has been approved. An import naming a document in any
other phase SHALL be reported as blocking a proposal.

Two things follow from the restriction, and both are the reason for it. An approved document's path
is permanent, so the reference cannot be broken by a rename. And an approved document has already
produced its tasks, so the task being imported is guaranteed to exist.

The check SHALL be reported at submission rather than refused, consistent with the standing rule that
a document under discussion is incomplete by definition and that it is the transition to proposed
that cares. An author must be able to write down a dependency on work that is still being explored.

#### Scenario: Importing from an unapproved document is reported, not refused

- **WHEN** a document is submitted with an import naming a document that is still exploring
- **THEN** the submission is accepted
- **AND** the import is reported as blocking a proposal

#### Scenario: The document cannot be proposed while the import is unapproved

- **WHEN** that document is proposed
- **THEN** the proposal is refused

#### Scenario: The same document proposes once its import is approved

- **WHEN** the imported document reaches approved and the importing document is proposed again
- **THEN** the import no longer blocks

### Requirement: A task belonging to no document cannot be given a dependency

Where a task has no owning specification document, the Hub SHALL refuse to record a dependency for it
and SHALL state why.

A dependency is declared by a document, and a task created by hand belongs to none — so there is
nothing that could declare its edges and no place the edge could be written down. The refusal exists
so that this reads as a rule rather than as a feature quietly not working.

#### Scenario: A hand-made task refuses a dependency with a reason

- **WHEN** a dependency is recorded for a task with no owning document
- **THEN** it is refused
- **AND** the refusal states that dependencies are declared by a document

### Requirement: A task may name the reviewer it needs, as a portable hint

A document's task MAY name a reviewer, and the Hub SHALL treat that name as a hint to be resolved
rather than as an agent identity. A task naming no reviewer SHALL validate and materialise exactly as
one authored before this field existed.

A named reviewer that resolves to nothing on this machine SHALL be preserved and reported, and SHALL
NOT cause the document to be refused. A document is committed and is expected to reproduce on a
machine whose agent roster differs from its author's, so an unresolvable name is an ordinary
condition rather than an error.

#### Scenario: A task naming a reviewer round-trips unchanged

- **WHEN** a payload whose task names a reviewer is rendered and read back
- **THEN** the recovered payload names the same reviewer

#### Scenario: A task naming no reviewer is unaffected

- **WHEN** a payload whose tasks name no reviewer is submitted
- **THEN** it validates and materialises exactly as it did before this field existed

#### Scenario: An unresolvable reviewer is reported, not refused

- **WHEN** a document names a reviewer matching no charter and no agent in this project
- **THEN** the submission succeeds
- **AND** the unresolvable name is reported among the document's blocking items
- **AND** the name is preserved on the task rather than discarded

#### Scenario: The name is not stored as an agent identity

- **WHEN** a document naming a reviewer is materialised
- **THEN** no task is assigned to an agent as a result of the name alone

### Requirement: The operator can declare a dependency between existing tasks

An operator SHALL be able to declare that one task depends on another, for tasks they created,
without authoring a specification document.

Today dependency rows are written in exactly one place, reached only when an approved document
carries ordering keys. The task-update surface refuses the field and no dependency route exists. So
an operator cannot say "B needs A" about two tasks they made, and the whole subsystem — the gate,
the board tab, two tables, and the prerequisite and dependent fields on every task — is reachable
only if an agent happens to author the right keys into a document that is then approved. In the
sweep the agent authored no ordering at all, so the graph came out empty and the gate was never
exercisable.

Both paths SHALL write dependencies through one shared writer, so the graph cannot be built two
different ways.

#### Scenario: An operator declares a dependency
- **WHEN** the operator declares that task B depends on task A
- **THEN** the dependency SHALL be recorded
- **AND** the existing gate SHALL apply to B unchanged

#### Scenario: The dependency would form a cycle
- **WHEN** a declared dependency would create a cycle
- **THEN** it SHALL be refused, naming the cycle

#### Scenario: A named task does not exist
- **WHEN** a declared dependency names a task that does not exist
- **THEN** it SHALL be refused, naming which one

#### Scenario: The document path is unchanged
- **WHEN** an approved document declares ordering between its own tasks
- **THEN** the dependencies SHALL be recorded exactly as before

#### Scenario: An operator removes a dependency
- **WHEN** the operator removes a declared dependency
- **THEN** it SHALL no longer gate the dependent task

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
