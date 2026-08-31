## MODIFIED Requirements

### Requirement: A task's checkout carries the work it depends on

A task's isolated checkout SHALL contain the work of every prerequisite the task was permitted to start on, whether or not that work reached the project's main branch.

A dependency is met at `approved`, and approval attempts integration — but integration is best-effort
and never blocks an approval, so a prerequisite can be `approved` with its work not on the main
branch: the project may have no main branch named, the accepted evidence may name no commit at all,
the operator's own checkout may be mid-edit or parked elsewhere, or the merge may have failed
outright. Isolating work per task removes the accident that used to cover this, which was that a
dependent held by the same agent inherited the prerequisite's commits because it was literally the
same branch.

The checkout SHALL be created from the branch approved work is integrated into, and each direct
prerequisite's commit **that the system would integrate for that prerequisite** SHALL then be brought
in where it is not already contained. A prerequisite for which no commit would be integrated
contributes nothing, because there is no commit to bring; that is a supported project shape, not a
failure.

**This sentence named a prerequisite's accepted evidence commit until now, because evidence was the
only thing that could name what a task integrates.** It no longer is: a task whose loop declared that
its work needs no evidence integrates its own branch, and for such a prerequisite there is no
accepted evidence commit to bring, so the unamended sentence would carry nothing while the
requirement's own opening sentence says the successor's checkout must contain that work. The two are
reconciled by naming the answer rather than one of its sources — the same answer approval would
merge, asked one place earlier.

**Only a prerequisite that is `approved` SHALL contribute.** A dependency is met at `approved` and
nothing earlier, so this is what the gate already guarantees for every prerequisite a task was
*permitted* to start on — but it SHALL be enforced here rather than assumed, because a task's branch
can be created before the gate has fired, and bringing an unapproved prerequisite's work into a
checkout an agent is about to write in would place work nobody has judged under the successor's
authorship. Where a prerequisite's work is integrated from evidence, this changes nothing: evidence
that has not been accepted names no commit anyway.

Where a prerequisite's work cannot be brought in without conflict, the turn SHALL NOT start, and the refusal SHALL name the prerequisite. Starting an agent on a checkout that silently lacks what it was told to build on produces work against the wrong base and evidence that describes a tree nobody reviewed.

#### Scenario: A prerequisite that was approved but not integrated

- **WHEN** a task starts whose prerequisite is approved and whose work did not reach the main branch
- **THEN** the task's checkout contains that prerequisite's work

#### Scenario: A prerequisite whose work needs no evidence

- **WHEN** a task starts whose prerequisite belongs to a loop that declared its work needs no
  evidence, and that prerequisite's approval did not reach the main branch
- **THEN** the task's checkout contains that prerequisite's work
- **AND** it was not required to have recorded any evidence for that to happen

#### Scenario: A prerequisite that is not yet approved contributes nothing

- **WHEN** a task's checkout is created while a prerequisite of it is not yet approved
- **THEN** that prerequisite's work is not brought in
- **AND** the turn is not refused on account of it

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
