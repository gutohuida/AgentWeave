## ADDED Requirements

### Requirement: A loop declares at creation whether its work needs evidence

A loop SHALL be creatable with a declaration of whether the work it produces needs evidence before that work can reach the project's main branch, and the system SHALL apply the product's current default where a loop was created without one.

A loop is documentless by definition — declaring a specification document is what makes it a flow —
so a loop's project mints no requirements for it, its tasks can record no evidence against them, and
the chain that carries approved work to the main branch begins at a requirement link. Before this
requirement, every loop task that was ever approved recorded that nothing was merged, and no
configuration, no permission and no operator action could change that. A loop could not land work at
all, structurally, and the product never said so.

A loop that declares its work **does** need evidence SHALL behave exactly as loops behave today: its
tasks reach the main branch through the requirements they are individually linked to and the evidence
accepted against them, and where nothing is accepted, nothing is merged. This is a coherent
declaration rather than a promise the product cannot keep, because a loop's tasks may be linked to
requirements individually even though the loop declares no document.

A loop that declares its work does **not** need evidence SHALL have its tasks' work integrated on
approval without any requirement link or accepted evidence, from the source stated in
`task-lifecycle-governance`.

The declaration SHALL be recorded as made or not made, and SHALL NOT be stored as a copy of whatever
the default is at the moment of creation. A loop created before this capability existed, and a loop
created without stating a preference, are the same case and SHALL be answered by resolving the
default at the moment the question is asked. A row that stores today's default would keep asserting
it after the default moved.

The declaration SHALL be accepted at creation only. An attempt to change it afterwards SHALL be
refused, naming why. The declaration decides what approving a task writes into the operator's
repository; a queue that is part-way through being approved would otherwise have two different
answers applied to two halves of the same work, and the mechanism that defers a loop's edits to its
next firing cannot help, because this is not read by a firing at all.

Supplying the declaration SHALL NOT, by itself, opt a job into being a loop. The fields that opt a
job in are unchanged. Where the declaration is supplied for a job that is not becoming a loop, the
request SHALL be refused, naming what to supply instead, and SHALL NOT be accepted with the
declaration silently discarded. A declaration that decides what an approval writes into the
operator's repository is not visible in its absence: unlike a loop's other fields, nothing on any
screen shows that it was dropped, and the first evidence of the loss is a merge that did or did not
happen long afterwards.

#### Scenario: A loop created without stating a preference gets the default

- **WHEN** a loop is created without saying whether its work needs evidence
- **THEN** the loop is created
- **AND** no declaration is recorded against it
- **AND** the question is answered by the product's current default wherever it is asked

#### Scenario: A loop that declares its work needs no evidence can land work

- **WHEN** a loop declaring that its work needs no evidence has a task approved, in a project with a
  configured main branch
- **THEN** the task's work is integrated
- **AND** no requirement link and no accepted evidence were needed for it

#### Scenario: A loop that declares its work needs evidence is unchanged

- **WHEN** a loop declaring that its work needs evidence has a task approved with no accepted
  evidence naming a commit
- **THEN** the approval succeeds
- **AND** nothing is merged
- **AND** the skipped integration is recorded with its reason

#### Scenario: The declaration cannot be changed after the loop exists

- **WHEN** an update supplies a different declaration for an existing loop
- **THEN** the request is refused, naming why the declaration is fixed at creation
- **AND** the loop's recorded declaration is unchanged

#### Scenario: The declaration alone does not create a loop

- **WHEN** a job is created supplying only the declaration, and none of purpose, a stop time, or a
  queue-emptiness stop condition
- **THEN** the request is refused, naming what else must be supplied for the job to be a loop
- **AND** no job and no loop state are created
