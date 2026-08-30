## MODIFIED Requirements

### Requirement: A task is recorded as waiting because the system observed it

The system SHALL move a task into the waiting status when it observes that a run bound to that task has asked a blocking question that is not yet answered, attributed to that run and recorded as system-caused.

The move SHALL happen when the question is asked, not when the asking run ends. The whole purpose of
a blocking ask is the interval between those two moments, and a status that only becomes true at the
end of it describes the wait after it has stopped mattering. During that interval the board otherwise
states that work is under way about work that has stopped and is waiting on a person.

The system SHALL still make the same move at the end of a run bound to a task that is not already
waiting and that has an unanswered blocking question outstanding. That covers a question asked in an
earlier turn of the same thread, and a task that was not in the in-progress status at the moment the
question was asked and so could not be moved then.

The system SHALL move it back out when that question is answered.

A task SHALL NOT enter or leave the waiting status because an agent asserted that it should. An
agent that could declare itself blocked could claim to be waiting on a person it never asked, which
is the one claim a completion gate would most reward. A report by the system's own tooling that a
wait has begun or ended is not such an assertion: it describes what the tool did, and the system
accepts it only about the reporting run's own questions.

#### Scenario: Asking a blocking question leaves the task waiting immediately

- **WHEN** a run bound to a task whose work is under way asks a blocking question
- **THEN** the task is recorded as waiting before the run ends
- **AND** the transition names the run and is recorded as system-caused

#### Scenario: A run that ends with a question outstanding leaves its task waiting

- **WHEN** a run bound to a task ends
- **AND** a blocking question it asked has not been answered
- **THEN** the task is recorded as waiting
- **AND** the transition names the run and is recorded as system-caused

#### Scenario: A task that cannot be moved when the question is asked is still moved at the end

- **GIVEN** a run bound to a task that is not in the in-progress status
- **WHEN** that run asks a blocking question and the task later reaches the in-progress status
- **AND** the run ends with the question still unanswered
- **THEN** the task is recorded as waiting

#### Scenario: Answering releases the task

- **WHEN** the question that caused a task to be recorded as waiting is answered
- **THEN** the task returns to the in-progress status
- **AND** the transition is recorded

#### Scenario: An agent cannot declare itself waiting

- **WHEN** an agent requests the waiting status for its own task
- **THEN** the request is refused

#### Scenario: The operator may block and release directly

- **WHEN** the operator moves a task into or out of the waiting status
- **THEN** the transition is accepted and recorded as an operator action

### Requirement: Only an unanswered blocking question makes a task wait

The system SHALL record a task as waiting only on account of a question that is unanswered, not declined, marked as blocking, whose wait has not already ended, and that was asked by the run whose ask or whose end is being evaluated.

A question that does not block is the agent leaving a note and continuing; a task parked on one would
make the status mean that an agent mentioned something. A question left open by a different run is
not evidence that this run stopped for it.

A question whose wait has ended is no longer being waited on by anybody. Parking a task on one would
record a wait that has already finished, and — where the run then ended without moving its task —
would suppress a divergence that is real, describing an agent that proceeded and dropped the work as
one that was waiting for an answer.

#### Scenario: A non-blocking question does not make a task wait

- **WHEN** a run ends having asked a non-blocking question and without moving its task
- **THEN** the task is not recorded as waiting
- **AND** the run is divergent as normal

#### Scenario: An answered question does not make a task wait

- **WHEN** a run ends having asked a question that was answered, without moving its task
- **THEN** the task is not recorded as waiting

#### Scenario: Another run's open question does not make this task wait

- **WHEN** a run ends without moving its task
- **AND** the only unanswered blocking question was asked by a different run
- **THEN** the task is not recorded as waiting

#### Scenario: A question whose wait has ended does not make a task wait

- **WHEN** a run ends without moving its task
- **AND** the only outstanding blocking question it asked is one whose wait already ended
- **THEN** the task is not recorded as waiting
- **AND** the run is divergent as normal

#### Scenario: A question whose wait has ended is not reported as an open wait

- **WHEN** a task is listed and the only blocking question against it is one whose wait ended
- **THEN** the task does not state that it is waiting for an answer

### Requirement: Starting work is gated on its prerequisites, and the gate lives with the other gates

The transition to in-progress SHALL be guarded by the task's dependencies where it starts work, and that guard SHALL be applied in the same place as the machine's existing guards — inside the transition service, before the history row is written.

Placement is the requirement, not an implementation note. The existing gates are positioned there
precisely so that no caller can reach a status write another way, which is what gives every surface —
the operator's route, the agent capability plane, the tool surface, scheduled jobs — the same
enforcement without any of them knowing it exists. A dependency check applied at a route, or in the
board, would be a rule that holds for the callers somebody remembered.

The transition out of the waiting status back to in-progress SHALL NOT be gated. That edge resumes
work rather than starting it: the waiting status is reachable only from in-progress, so a task on
that edge has already passed the gate once and has already begun. Gating it would let a prerequisite
that regressed while the task waited strand the work — the answer arrives and releases nothing, or
the agent that waited out its question is refused the completion of work it has finished, with no
action available to it either way.

#### Scenario: Every surface is gated identically

- **WHEN** a task with an unmet prerequisite is moved to in-progress through any surface
- **THEN** the move is refused

#### Scenario: The refusal is distinguishable from an illegal transition

- **WHEN** a start is refused for an unmet prerequisite
- **THEN** the refusal identifies the cause as a dependency rather than as an illegal edge

#### Scenario: Resuming a waiting task is not refused for a prerequisite

- **GIVEN** a waiting task whose prerequisite no longer clears the gate
- **WHEN** the wait ends by any route
- **THEN** the task returns to the in-progress status
- **AND** the return is not refused as a dependency failure

## ADDED Requirements

### Requirement: A wait that ends without an answer returns the task to its work

Where a bounded wait for an operator's answer ends without one and the asking run continues, the system SHALL return the waiting task to the in-progress status and SHALL record durably that the wait ended unanswered.

A task is waiting because somebody is waiting. When the wait ends and the agent goes on to decide
for itself, nobody is waiting any longer, and a task still recorded as waiting would ask the
operator for something no one needs. It would also be unfinishable: the waiting status has no edge
to a finished one, deliberately, so an agent that completed the work would be refused.

The system SHALL accept this only as a report about a wait it has already recorded: about questions
asked by the reporting run, whose recorded wait has expired, and that are neither answered nor
declined. A report that does not describe a wait the system recorded SHALL be refused, so that the
end of a wait remains an observation rather than a lever.

Where no such report arrives — the tool did not survive to send it, or the run was killed — the task
SHALL remain waiting. Nobody proceeded, so nothing has changed about what the task is waiting for.

A wait ended by the operator answering or declining SHALL NOT be recorded as ended unanswered.
Declining is a decision the operator made and handed back; silence is not.

#### Scenario: An expired wait releases the task

- **GIVEN** a task recorded as waiting on a blocking question
- **WHEN** the asking run reports that its wait for that question expired
- **THEN** the task returns to the in-progress status
- **AND** it no longer states what it was waiting for

#### Scenario: The expired wait is recorded on the question

- **WHEN** a run reports that its wait for a question expired
- **THEN** the question durably records that its wait ended unanswered
- **AND** the question is still neither answered nor declined

#### Scenario: A report before the wait could have expired is refused

- **WHEN** a run reports an expired wait for a question whose recorded wait has not yet elapsed
- **THEN** the report is refused
- **AND** the task is unchanged

#### Scenario: A run cannot report another run's wait

- **WHEN** a run reports an expired wait for a question asked by a different run
- **THEN** the report is refused
- **AND** the task is unchanged

#### Scenario: An unreported wait leaves the task waiting

- **GIVEN** a task recorded as waiting on a blocking question
- **WHEN** the asking run ends without reporting anything about its wait
- **THEN** the task is still waiting

#### Scenario: A declined question is not recorded as an unanswered wait

- **WHEN** the operator declines a question and the asking run stops waiting
- **THEN** the question is not recorded as having ended unanswered

### Requirement: Work that proceeded without an answer says so, for good

Where a task's wait for an operator's answer ended without one, the system SHALL state that on the task, and SHALL continue to state it for every later status the task reaches.

The measured failure this exists to end: an agent asked which comparison semantics to ship, waited
out its timeout, chose one itself, edited the code and completed the task in the same turn. The task
read completed with nothing on it — not its status, not what it was waiting for, not any field the
task surface exposes — indicating that a substantive judgment call had been made unilaterally
because nobody answered in time. An operator scanning the board for problems would not find that
one.

The statement SHALL identify the question that went unanswered, so that the operator can read what
was decided without them rather than only that something was.

The statement SHALL NOT be cleared by the question later being answered. A question answered after
the work has shipped records a choice that may contradict what was built; clearing the statement then
would remove the only evidence of the unilateral call at the moment it becomes most misleading —
leaving a question that reads answered, a task that reads clean, and work that carries a decision
neither of them names.

The statement SHALL be derived from the durable record of the wait rather than stored a second time
on the task, so that the two cannot disagree.

#### Scenario: A completed task that shipped on an unanswered question says so

- **GIVEN** a task whose wait for an answer ended unanswered
- **WHEN** the agent completes that task
- **THEN** the task states that the work proceeded without the operator's answer
- **AND** the statement identifies the question

#### Scenario: The statement survives review and approval

- **WHEN** a task that proceeded without an answer is moved to review and then approved
- **THEN** it still states that the work proceeded without the operator's answer

#### Scenario: Answering afterwards does not erase the statement

- **GIVEN** a task that proceeded without the operator's answer
- **WHEN** the operator answers that question afterwards
- **THEN** the task still states that the work proceeded without their answer

#### Scenario: A task whose question was answered in time says nothing

- **WHEN** a task's blocking question is answered before its wait ends
- **THEN** the task states nothing about having proceeded without an answer

#### Scenario: A declined question does not mark the task

- **WHEN** the operator declines a blocking question and the agent decides for itself
- **THEN** the task states nothing about having proceeded without an answer
