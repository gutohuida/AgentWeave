## ADDED Requirements

### Requirement: A Copilot turn refused for its plan quota is a refusal of its allowance

The system SHALL treat a Copilot turn as refused by its usage allowance only when Copilot reports a structured error whose category is quota and whose code says the quota is exceeded, and SHALL then hold the agent's queue under the same rules as any other refusal of a provider's allowance.

The refusal's reset time SHALL be the reset date of the plan quota Copilot last reported for the
agent, provided that date is still ahead. When no such date is known, the refusal SHALL be recorded
and shown as an exhausted allowance and SHALL NOT hold the queue, because a hold with no stated end
would be a policy nobody has decided.

A refused turn SHALL end as a failed turn whatever stop reason Copilot reports for it, so that the
input it was given returns to the queue without being counted as a delivery attempt.

The system SHALL NOT recognise a refusal from the wording of an error message. A session cap, a
billing configuration error or a rate limit that carries no reset time SHALL NOT hold the queue.

Every Copilot run that reports its plan quota SHALL record that reading, so that the agent's
latest reading states the reset date a later refusal needs, and so that a served turn ends a hold.

#### Scenario: A quota refusal holds the queue until the quota resets

- **WHEN** a Copilot turn fails with a quota error whose code says the quota is exceeded
- **AND** Copilot's latest quota reading for the agent resets at the start of next month
- **THEN** the agent's queue is held until that time
- **AND** the hold is reported with its end
- **AND** the refused input is queued again, not counted as a delivery attempt, even when Copilot
  ended the turn with an ordinary stop reason

#### Scenario: A refusal with no known reset is shown but does not hold

- **WHEN** a Copilot turn fails with a quota-exceeded error
- **AND** no quota reading with a future reset date is known for the agent
- **THEN** the allowance is shown as exhausted
- **AND** the queue is not held

#### Scenario: Error wording alone is not a refusal

- **WHEN** a Copilot turn fails with an error whose message mentions a quota but whose category is
  not quota
- **THEN** no refusal is recorded and the queue is not held

#### Scenario: A session cap does not hold the queue

- **WHEN** a Copilot turn fails because its session's own credit cap was reached
- **THEN** the queue is not held

#### Scenario: A served Copilot turn ends the hold

- **WHEN** an agent's queue is held by a Copilot refusal and a later Copilot turn for it is served
- **THEN** the queue is no longer held
