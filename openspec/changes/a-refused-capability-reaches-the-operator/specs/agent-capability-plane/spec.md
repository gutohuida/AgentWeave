## ADDED Requirements

### Requirement: A capability refused for project state reaches the operator durably

Where the Hub refuses an agent capability because of project-level state the agent cannot itself change, it SHALL open a record of that refusal on an operator surface that outlives the refused run, and that record SHALL name the state, its current value, what changing it would allow, and where the operator changes it.

A refusal that exists only in the agent's own transcript reaches nobody. Measured on the operator's
own flow: an agent was refused `create_flow` because scheduled agent work was not allowed for the
project, the project's permission requests held **zero rows**, and the operator — who had said they
were leaving — returned to nothing. The agent fell back to hand-driven messages 37 seconds later and
no task in the flow ever reached approval.

The record SHALL NOT be one whose lifetime is bounded by the refused run or by a waiting caller's
deadline. The state that caused the refusal is true or false independently of any turn, so a record
that is swept when the run ends cannot carry the decision it exists to obtain.

The operator's answer SHALL be delivered to the agent that was refused, and that agent SHALL be woken
for it, even when the run that was refused has already ended.

The refused call SHALL NOT wait for the answer, and the caller SHALL NOT be instructed to poll for
it. A decision that may arrive after the run has ended cannot be waited for inside the run.

The record and its delivery SHALL be the same whichever access path the refused call used, and no
adapter SHALL hold any part of this rule.

#### Scenario: The first refusal opens the record

- **WHEN** an authenticated run's call is refused because scheduled agent work is not allowed for the
  project
- **THEN** a question of record is opened for the operator, attributed to the refused agent and its
  run, naming the setting, its current value, what enabling it would allow, and where it is changed
- **AND** an event is broadcast so the operator's view updates without a reload
- **AND** the refusal returned to the caller carries that record's identifier

#### Scenario: The record outlives the run

- **WHEN** the run that was refused ends before the operator has answered
- **THEN** the record remains open and unanswered on the operator's surface

#### Scenario: An answer given after the run has ended reaches the agent

- **WHEN** the operator answers the record after the refused run has ended
- **THEN** the answer is queued for the agent that was refused and that agent is woken for it

#### Scenario: The refused call does not wait

- **WHEN** the call is refused for that state
- **THEN** the refusal is returned immediately, and it does not instruct the caller to poll or to
  repeat the call once a decision exists

#### Scenario: A second refusal opens no second record

- **WHEN** a further call is refused for the same project state while the record is still unanswered
- **THEN** no second record is opened, and the refusal carries the existing record's identifier

#### Scenario: A negative answer is an answer

- **WHEN** the operator has answered the most recent record for that state by choosing to leave the
  state as it is, or has declined it
- **AND** a further call is refused for that state
- **THEN** no new record is opened, and the refusal names the state without claiming the operator has
  been asked

#### Scenario: Only the agent that was refused first is woken

- **WHEN** a second agent is refused for the same state while one record is open, and the operator
  then answers it
- **THEN** the answer is delivered to the agent named on the record, and the second agent is not woken
  by it

#### Scenario: An operator's own call opens nothing

- **WHEN** the same call is made by the operator rather than by an authenticated run
- **THEN** it is not gated by that state and no record is opened

#### Scenario: The record is the same on either access path

- **WHEN** equivalent calls are refused for that state over HTTP and through an adapter
- **THEN** the record opened, the event broadcast and the failure's meaning are equivalent

### Requirement: A refusal names the state that caused it, never an approval nobody requested

A refusal caused by project-level state SHALL name that state and its current value, and SHALL NOT describe an approval, allowance or decision that the system has not actually opened.

The shipped sentence — *"Scheduled work from agents requires operator approval or an enabled
allowance"* — is false in both halves: no approval is requested, and *"an enabled allowance"* names
nothing the agent can locate or ask for. An agent reading it is told to wait for something nobody was
asked for, which is worse than a plain refusal because it sends the operator looking for an approval
that was never going to arrive.

The refusal SHALL carry a machine-readable code and the identifier of the record opened for the
operator, in addition to the sentence, so a caller need not parse prose to know a decision is pending.

The refusal SHALL state what the caller may do instead, and SHALL state that the operator's answer
will arrive as input rather than as a result of this call.

#### Scenario: The refusal names the setting and its value

- **WHEN** a call is refused because scheduled agent work is not allowed for the project
- **THEN** the refusal names that setting and its current value

#### Scenario: The refusal does not promise an approval that was not opened

- **WHEN** a refusal is returned for that state
- **THEN** it does not claim that an approval or allowance decision is available unless a record for
  it has been opened

#### Scenario: The refusal is machine-readable as well as readable

- **WHEN** a refusal is returned for that state
- **THEN** its body carries a code naming the kind of refusal and the opened record's identifier
- **AND** an adapter's caller receives the sentence intact
