## ADDED Requirements

### Requirement: Every question that parks a task SHALL record which task it parked

A blocking question asked about a task that is already waiting SHALL record that task, so that
answering that question releases the block. Recording which task a question is about SHALL NOT depend
on that question being the one that moved the task into waiting.

Today the recording happens only as a side effect of the transition into the waiting status, and a
task already waiting has no such transition to make — the status is not a target of itself. So a
second question about the same task records nothing, and answering it releases nothing. The operator
answers the question in front of them and the task stays waiting; only answering the older question
works, and nothing tells them that.

This SHALL NOT change which transitions are legal. Recording what a question is about and moving a
task are different facts, and only one of them needs an edge in the transition map.

#### Scenario: A second question about a waiting task records it

- **GIVEN** a task already waiting on a person
- **WHEN** a run asks a further blocking question about that same task
- **THEN** that question records the task it is waiting on

#### Scenario: Answering the second question releases the task

- **GIVEN** a waiting task with more than one blocking question recorded against it
- **WHEN** the most recent of those questions is answered
- **THEN** the task is released

#### Scenario: The transition map is unchanged

- **WHEN** a question is asked about a task that is already waiting
- **THEN** the task's status is not transitioned
- **AND** no transition into the waiting status from itself is permitted

#### Scenario: A question about an unrelated task releases nothing

- **GIVEN** a waiting task and a blocking question about a different task
- **WHEN** that question is answered
- **THEN** the waiting task is not released
