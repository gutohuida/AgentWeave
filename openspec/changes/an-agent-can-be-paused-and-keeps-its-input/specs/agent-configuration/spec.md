## ADDED Requirements

### Requirement: The operator can pause an agent, and its input waits

The operator SHALL be able to pause an agent so that no new turn of it starts until the operator resumes it, and input addressed to a paused agent SHALL be kept, in order, and delivered when it is resumed.

Stopping a run stops one turn, and a peer's message started the next one moments later; archiving is
refused while any input is queued. Without a pause, an agent that other agents keep addressing cannot
be brought to rest.

A pause SHALL NOT withdraw, refuse or count a delivery attempt against any input, whoever sent it,
including the operator. Every surface that reports why an agent's input is waiting SHALL say the agent
is paused. While paused, the agent SHALL NOT be selected by a flow to take work or to review, and a
loop whose agent is paused SHALL NOT queue further briefings for it.

Pausing SHALL NOT change the agent's lifecycle: a paused agent remains on the roster with its
conversations. Pausing MAY stop the agent's running turn in the same action, and where it does, the
pause SHALL take effect before the turn is stopped. The agent plane SHALL NOT offer pausing or
resuming.

#### Scenario: A peer's message does not restart a paused agent

- **GIVEN** an agent is paused while another agent messages it
- **WHEN** the message is accepted
- **THEN** it is queued and no turn of the paused agent starts
- **AND** the waiting reason says the agent is paused

#### Scenario: Resuming delivers what waited

- **GIVEN** a paused agent with three queued entries
- **WHEN** the operator resumes it
- **THEN** its queue is delivered in order
- **AND** no entry records a delivery attempt from the time it was paused

#### Scenario: Pause and stop in one action

- **GIVEN** an agent running a turn with a peer message queued behind it
- **WHEN** the operator pauses it and asks for the running turn to stop
- **THEN** the turn stops and no further turn starts

#### Scenario: A flow does not staff a paused agent

- **GIVEN** a flow whose only free agent is paused
- **WHEN** the flow fires
- **THEN** it does not select the paused agent
