## MODIFIED Requirements

### Requirement: A firing is refused while its queue is stalled

The Hub SHALL refuse a firing whose queue is stalled, before queueing any input, and SHALL record a reason naming what the queue is waiting on. A queue is stalled when it holds tasks that are not terminal and none of them is claimable.

Where nothing is claimable and no dependency gate is involved, that reason SHALL name how many tasks
are open and in which statuses. Where instead a dependency gate refuses every candidate, the reason
is governed by "A queue gated on unapproved work is stalled, never stopped", which requires it to
distinguish an unmet prerequisite from a rejected one. That reason names counts and causes rather
than statuses, and this requirement SHALL NOT be read to demand both of it: the operator's remedy
there is the prerequisite, not the queue's own status breakdown.

**Where the firing's own walk attributed the stall to a specific task and named what the operator can
do about it, that SHALL be the recorded reason in place of the status breakdown.** The breakdown is
the reason of last resort — it is what the queue can say about itself when nothing more specific was
established — and the same argument the gated case makes applies here unchanged: the operator's
remedy is the named task, not a count. A firing that established a specific cause and then reported a
histogram has discarded the only part of what it knows that can be acted on.

The loop's job SHALL remain enabled and remain scheduled. A stalled queue is not a finished one, and
the operator resolving the stall SHALL be sufficient for a later firing to proceed with no further
action.

#### Scenario: A stalled queue refuses the firing and states why

- **WHEN** a loop's job fires and every non-terminal task in its queue is unclaimable, with no
  dependency gate involved and no specific cause established
- **THEN** the firing is refused
- **AND** the recorded reason names the count and statuses of the open tasks

#### Scenario: A gated stall states its gate rather than its statuses

- **WHEN** a loop's job fires and every candidate in its queue is refused by the dependency gate
- **THEN** the firing is refused
- **AND** the recorded reason names the gating rather than the queue's status breakdown

#### Scenario: An attributed stall names its task rather than the queue

- **WHEN** a loop's job fires, nothing is claimable, and the walk recorded a staffing outcome naming
  a task and a remedy
- **THEN** the firing is refused
- **AND** the recorded reason is that outcome rather than the queue's status breakdown

#### Scenario: A stalled loop is not disabled

- **WHEN** a loop's job fires with a stalled queue
- **THEN** the job remains enabled and the loop records no stop reason

#### Scenario: A resolved stall resumes on the next firing

- **WHEN** a stalled loop's queue gains a claimable task and the job fires again
- **THEN** the firing claims that task
