## ADDED Requirements

### Requirement: A Copilot turn refused for its plan quota is a refusal of its allowance

The system SHALL treat a Copilot turn as refused by its usage allowance only when Copilot reports a structured error whose category is quota and whose code says the quota is exceeded, and SHALL then hold the agent's queue under the same rules as any other refusal of a provider's allowance.

The refusal's reset time SHALL be the reset date of the plan quota the refused run itself reported,
or else the newest reset date any Copilot run of the same project reported, provided that date is
still ahead. The quota belongs to the account, not to the agent, so another agent's reading states
the same reset. Only the reset date SHALL be taken from an earlier reading. When no such date is
known, the refusal SHALL be recorded and shown as an exhausted allowance and SHALL NOT hold the
queue, because a hold with no stated end would be a policy nobody has decided.

A refused turn SHALL end as a failed turn whatever stop reason Copilot reports for it, and also
when Copilot answers the prompt with an error response or its process ends before answering. When
the refusal holds the queue, the input it was given returns to the queue without being counted as a
delivery attempt. When it does not hold the queue, because no reset date is known, the input is
returned as any failed turn's input is: counted as a delivery attempt, so that a later attempt
starts a fresh provider session and a further one gives the input up. The refusal SHALL be
recognised from either the structured error event or the structured fields of the prompt's error
response.

The system SHALL NOT recognise a refusal from the wording of an error message. A session cap, a
billing configuration error or a rate limit that carries no reset time SHALL NOT hold the queue. A
turn that was not refused SHALL NOT record a refusal, whatever an earlier reading said.

Every Copilot run that reports its plan quota SHALL record that reading, so that a later refusal
can find the reset date it needs, and so that a served turn ends a hold. Rebinding a held agent to
another runner SHALL NOT by itself end the hold; a turn served after the rebinding does.

While a Copilot refusal holds an agent's queue, the notice the operator is shown for the hold SHALL
state the date and time the hold ends and the way out of it: bind the agent to another runner and
then send it a message, because rebinding alone does not end the hold, and until then the agent's
loops and jobs stay blocked too. The shorter notices given to a loop or a job that such a hold blocks
SHALL state the date the hold ends, not only its time of day. A hold from any other provider SHALL
be described as before.

#### Scenario: A quota refusal holds the queue until the quota resets

- **WHEN** a Copilot turn fails with a quota error whose code says the quota is exceeded
- **AND** Copilot's latest quota reading for the agent resets at the start of next month
- **THEN** the agent's queue is held until that time
- **AND** the hold is reported with its end
- **AND** the refused input is queued again, not counted as a delivery attempt, even when Copilot
  ended the turn with an ordinary stop reason

#### Scenario: A quota error answering the prompt itself is a refusal

- **WHEN** Copilot answers a turn's prompt with an error response whose structured fields say the
  plan quota is exceeded
- **AND** Copilot's latest quota reading for the agent resets at a future time
- **THEN** the turn ends failed, its input is queued again uncounted, and the queue is held until
  that time

#### Scenario: A refusal with no known reset is shown but does not hold

- **WHEN** a Copilot turn fails with a quota-exceeded error
- **AND** no quota reading with a future reset date is known for the project
- **THEN** the allowance is shown as exhausted
- **AND** the queue is not held
- **AND** the input is returned counted as a delivery attempt, like any failed turn's input

#### Scenario: Another agent's reading supplies the reset

- **WHEN** a Copilot agent's turn is refused on its first model call, so it reported no quota
  reading of its own
- **AND** another Copilot agent of the same project recorded a reading whose reset is ahead
- **THEN** the refused agent's queue is held until that reset

#### Scenario: An earlier refusal is not renewed by an unrelated failure

- **WHEN** an agent's queue was held by a Copilot quota refusal
- **AND** a later Copilot turn of that agent fails for a reason other than the quota, reporting no
  quota reading
- **THEN** that turn records no refusal and does not renew the hold

#### Scenario: Error wording alone is not a refusal

- **WHEN** a Copilot turn fails with an error whose message mentions a quota but whose category is
  not quota
- **THEN** no refusal is recorded and the queue is not held

#### Scenario: A session cap does not hold the queue

- **WHEN** a Copilot turn fails because its session's own credit cap was reached
- **THEN** the queue is not held

#### Scenario: A Copilot hold names its end and the way out

- **WHEN** an agent's queue is held by a Copilot refusal whose reset is 00:00 UTC on 2026-10-01
- **THEN** the reason the agent is not running names 2026-10-01 and 00:00 UTC
- **AND** it says to bind the agent to another runner and then send it a message
- **AND** it says that rebinding alone does not end the hold, and that its loops and jobs stay
  blocked until then

#### Scenario: Rebinding without a message leaves the hold

- **WHEN** an agent's queue is held by a Copilot refusal
- **AND** the agent is bound to another runner and no message is sent to it
- **THEN** the queue is still held and its loops and jobs stay blocked

#### Scenario: A Claude hold is described as before

- **WHEN** an agent's queue is held by a refusal from a provider other than Copilot
- **THEN** the reason the agent is not running reads exactly as it did before this change

#### Scenario: A served Copilot turn ends the hold

- **WHEN** an agent's queue is held by a Copilot refusal and a later Copilot turn for it is served
- **THEN** the queue is no longer held
