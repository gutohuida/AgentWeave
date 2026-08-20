## ADDED Requirements

### Requirement: A firing does not claim a task whose dependencies are unmet

A firing SHALL NOT claim a task the dependency gate would refuse to start. Claimability and
startability must agree, or the loop claims work it cannot begin.

The check SHALL use the same determination of *"are this task's dependencies met"* that the
transition gate uses, so that the queue and the gate cannot disagree.

A firing SHALL claim the queue's oldest startable task, skipping unstartable ones in order rather
than stopping at the first.

#### Scenario: An unstartable task is skipped in favour of a startable one

- **WHEN** a loop's queue holds an older task with an unapproved prerequisite and a newer task with
  none
- **THEN** the firing claims the newer task
- **AND** the older task keeps its status and gains no assignee

#### Scenario: A queue of only unstartable tasks claims nothing

- **WHEN** every non-terminal task in a loop's queue has an unmet dependency
- **THEN** the firing claims nothing

#### Scenario: A task becomes claimable when its prerequisite is approved

- **WHEN** a task's only prerequisite moves to `approved` and the loop fires
- **THEN** the firing claims that task

#### Scenario: The claim and the gate agree

- **WHEN** a firing claims a task
- **THEN** that task's move to `in_progress` is not refused by the dependency gate

### Requirement: A queue gated on unapproved work is stalled, never stopped

A loop whose queue holds only tasks with unmet dependencies SHALL be treated as stalled, and its job
SHALL remain enabled and remain scheduled.

The recorded stall reason SHALL distinguish a queue waiting on work that can still be approved from
one gated on a prerequisite that has been `rejected`, because the two mean different things to an
operator and have different remedies.

A queue gated on a rejected prerequisite SHALL NOT stop the loop. `rejected` is reversible by the
operator, and stopping would set the job disabled and remove it from the scheduler, so the operator
reversing the rejection afterwards could not revive it.

#### Scenario: A dependency-gated queue does not disable the loop

- **WHEN** a loop fires and every task in its queue has an unapproved prerequisite
- **THEN** the job remains enabled and the loop records no stop reason

#### Scenario: The stall reason names which kind of gating it is

- **WHEN** a loop's queue is gated on a prerequisite that is `rejected`
- **THEN** the recorded reason identifies the gating as permanent-until-reversed, distinctly from a
  prerequisite merely not yet approved

#### Scenario: Reversing a rejection revives the loop with no further action

- **WHEN** the operator moves a rejected prerequisite back to `pending`, it is subsequently approved,
  and the loop fires again
- **THEN** the firing claims the task that was gated on it
