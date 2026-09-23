## MODIFIED Requirements

### Requirement: Pressing Run on a loop that declines names why it declined

The Hub SHALL answer an operator's manual firing of a loop that the loop's busy guard refused with a conflict that names the reason the guard gave, and SHALL NOT answer it as a failure to fire.

The busy guard refuses a firing when the job's agent is running a turn or its queue is held, and
**either the loop declares no specification document, or no other agent in the project is free, or
the loop's queue holds no task in a non-terminal status.** It records nothing, deliberately, so
there is no firing record to read a reason from, and the most recent record is some earlier
firing's.

The answer SHALL name the condition that held, and SHALL NOT state a condition that did not hold or
that was not the reason. Where more than one holds, the answer SHALL name the empty queue.

Where the loop's queue holds no task in a non-terminal status, the answer SHALL say so, and SHALL
NOT state that no other agent is free. Stating that no other agent is free when one is free tells
the operator to free an agent, which would change nothing; what the loop lacks is work. Where the
loop declares no specification document, the answer SHALL NOT describe the empty queue as work for
another agent to take, because that loop gives its work to no other agent.

Where the loop declares no specification document and its queue holds an open task, the answer SHALL
say that the loop gives its work only to the agent its job names, and SHALL NOT state that no other
agent is free. That loop is refused whether or not another agent is free, so the roster is not its
reason, even where the roster is in fact empty.

Where the loop declares a specification document and its queue holds an open task, the guard refused
because no other agent is free, and the answer SHALL say so.

The route SHALL answer from a firing record only when the manual firing wrote that record or counted
itself into it. A continuing stall counts each firing into the record it already holds rather than
writing another, so that record is this firing's answer. Where the firing did neither, the route
SHALL ask the guard again before anything else, because the guard is the first question the firing
asked, and SHALL answer a refusal with the guard's reason. A record some earlier firing wrote, and
this firing did not count into, is not this firing's answer. The route SHALL NOT change a record's
requester to whoever pressed Run unless the manual firing wrote that record.

Where the firing declined because every task on the queue is in flight, and an agent those tasks are
staffed to is held, the answer SHALL name that agent and the time its hold ends. It SHALL NOT state
that the work is already being worked, or that nothing is wrong. The work is staffed, but it cannot
start until the hold ends.

#### Scenario: Run while the loop's agent is mid-turn and nobody else is free

- **WHEN** a loop that declares a specification document has its agent running a turn, the loop's queue holds an open task, no other agent in the project is free, and the operator presses Run
- **THEN** the answer is a conflict naming the agent that is running
- **AND** it states that no other agent is free
- **AND** it is not a server error reading "Failed to fire job"

#### Scenario: Run while the loop's agent is mid-turn and its queue is empty

- **WHEN** a loop's agent is running a turn, the loop's queue holds no task in a non-terminal status, another agent in the project is free, and the operator presses Run
- **THEN** the answer is a conflict naming the agent that is running
- **AND** it says the loop's queue holds no open task
- **AND** it does not state that no other agent is free
- **AND** no inbound queue entry is created for the loop's agent

#### Scenario: Run on a documentless loop with an empty queue

- **WHEN** a loop that declares no specification document has its agent running a turn, its queue holds no task in a non-terminal status, and the operator presses Run
- **THEN** the answer says the loop's queue holds no open task
- **AND** it does not describe that as work for another agent to take

#### Scenario: Run on a documentless loop while another agent is free

- **WHEN** a loop that declares no specification document has its agent running a turn, its queue holds a pending task, another agent in the project is free, and the operator presses Run
- **THEN** the answer is a conflict naming the agent that is running
- **AND** it says the loop gives its work only to the agent its job names
- **AND** it does not state that no other agent is free

#### Scenario: Run on a documentless loop while nobody else is free

- **WHEN** a loop that declares no specification document has its agent running a turn, its queue holds a pending task, no other agent in the project is free, and the operator presses Run
- **THEN** the answer says the loop gives its work only to the agent its job names
- **AND** it does not state that no other agent is free

#### Scenario: Run while the loop's agent is held

- **WHEN** a loop's agent's queue is held, no other agent in the project is free, and the operator presses Run
- **THEN** the answer is a conflict naming the agent and the time its hold ends

#### Scenario: Run on a flow whose in-flight work waits on a hold

- **WHEN** every task on a flow's queue is in flight, one of them is staffed to a held agent, and the operator presses Run
- **THEN** the answer names that agent and the time its hold ends
- **AND** it does not state that the work is already being worked, or that nothing is wrong

#### Scenario: Run on a flow whose work is in flight, after an earlier firing stalled

- **WHEN** an earlier firing of a flow recorded a skipped firing with a stall reason, every task now on the flow's queue is in flight and none of them waits on a hold, and the operator presses Run
- **THEN** the answer says the work is already being worked
- **AND** it does not carry the earlier firing's stall reason
- **AND** the earlier record's count of firings and its requester are unchanged

#### Scenario: A firing that recorded its own refusal is answered from that record

- **WHEN** the operator presses Run on a loop, the firing records a skipped firing with its reason, and the loop's agent has become busy since
- **THEN** the answer is a conflict carrying the recorded reason, not the busy guard's

#### Scenario: A continuing stall is answered from the record it counted into

- **WHEN** a loop's latest record is a skipped firing whose stall reason is unchanged, and the operator presses Run
- **THEN** the firing counts itself into that record
- **AND** the answer is a conflict carrying that record's reason
- **AND** that record's requester is unchanged

#### Scenario: An earlier firing's record is not attributed to the press

- **WHEN** Run is pressed on a loop and the firing writes no record
- **THEN** no earlier firing's record has its requester changed
