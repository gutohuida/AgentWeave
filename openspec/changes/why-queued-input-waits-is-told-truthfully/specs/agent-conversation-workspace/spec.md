## ADDED Requirements

### Requirement: An agent's queue status presents a remembered refusal as a record of the last attempt

Where the queue status of an agent answers why its input is waiting with the refusal of an earlier delivery attempt, it SHALL present that refusal as what the last attempt was refused with, and SHALL NOT present it as the present reason.

The status first asks what it can check now: whether the agent is running, whether the hop budget
or the token budget is spent, whether the agent's queue is held, whether the agent can be launched,
and whether the project's workspace resolves. Only where none of those answers does it fall back to
the words the last refused attempt was given, because without them an agent with input waiting
showed no reason at all. That fallback is a memory. A condition it names may have ended since, and
nothing re-evaluated it.

A refusal naming another agent's turn as holding the task's checkout SHALL be checked now rather
than remembered. Whether another agent is running a turn on that task is something the status can
read, and a remembered claim that one is, read beside a live answer that the named agent is running
nothing, tells the operator two contradicting things with no way to tell which is stale.

Where the check finds the holder still running a turn on that task, the status SHALL name that
agent and that task as the present reason. Where it finds nothing holding the task, the remembered
refusal SHALL be presented as the last attempt's.

#### Scenario: A checkout held now is reported as the present reason

- **WHEN** an agent's input names a task, and another agent is running a turn on that task
- **THEN** the queue status names that other agent and that task as why the input waits

#### Scenario: A checkout no longer held is not reported as held

- **WHEN** an agent's input was refused because another agent held the task's checkout, and that other agent's turn has since ended, and no attempt has been made since
- **THEN** the queue status does not state that the other agent is running a turn on that task
- **AND** it presents the refusal as what the last attempt was refused with

#### Scenario: A remembered refusal is marked as remembered

- **WHEN** none of the conditions the queue status can check holds, and the last delivery attempt was refused
- **THEN** the status presents that refusal's own words as the last attempt's refusal

#### Scenario: A reason checked now is reported as before

- **WHEN** an agent's input waits because the agent is running a turn
- **THEN** the queue status reports that reason exactly as before
