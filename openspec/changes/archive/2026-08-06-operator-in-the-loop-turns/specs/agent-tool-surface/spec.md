## ADDED Requirements

### Requirement: An agent can wait for the operator's answer

An agent SHALL be able to ask the operator a question and receive that operator's answer as the
result of asking, without polling for it.

Whether a question waits SHALL remain the asking agent's choice. A question that does not wait keeps
its present behaviour: it is recorded, the operator can answer it later, and the agent continues.

A waiting question SHALL resolve in exactly one of three ways — answered, declined, or expired — and
the agent SHALL be able to tell which. A waiting question MUST NOT wait indefinitely.

An expired question SHALL remain visible to the operator as an unanswered question rather than
disappearing, and answering it afterwards MUST NOT be delivered to a turn that has already moved on.

#### Scenario: A waiting question returns the answer

- **WHEN** an agent asks a waiting question and the operator answers it
- **THEN** the answer is the result of asking
- **AND** the agent did not poll for it

#### Scenario: A declined question is distinguishable from an answered one

- **WHEN** the operator declines to answer a waiting question
- **THEN** the agent is told it was declined
- **AND** can tell that apart from an answer

#### Scenario: Waiting is bounded

- **WHEN** a waiting question is not answered within the Hub's waiting period
- **THEN** the wait ends and the agent is told it expired
- **AND** the agent is not left waiting indefinitely

#### Scenario: An expired question is not lost

- **WHEN** a question has expired
- **THEN** it remains visible to the operator as unanswered
- **AND** a later answer is not delivered into a turn that has already continued

#### Scenario: A non-waiting question is unchanged

- **WHEN** an agent asks a question that does not wait
- **THEN** the agent continues immediately
- **AND** the question is recorded for the operator to answer later

### Requirement: An action the Hub would refuse can be put to the operator

The Hub SHALL be able to put a refusal to the operator instead of refusing silently. This applies
where a provider tells the Hub that an agent is attempting an action requiring approval, and the
Hub's answer under the operator's selected protections would be to refuse.

The operator SHALL be shown what the agent is attempting and the reason the provider supplied, in
terms specific enough to decide on.

An approval given this way SHALL authorise the single attempted action only. It MUST NOT become a
standing permission, MUST NOT alter the run's selected protections, and MUST NOT extend to any
subsequent action.

Where the operator does not answer, the action SHALL be refused. Refusal is the default that
inaction produces.

The Hub MUST NOT put to the operator any decision it would have granted anyway.

#### Scenario: A refusal becomes a question

- **WHEN** an agent attempts an action the operator's protections would refuse
- **THEN** the operator can be shown the action and the stated reason
- **AND** can allow or refuse it

#### Scenario: Allowing authorises one action

- **WHEN** the operator allows an escalated action
- **THEN** that action proceeds
- **AND** a subsequent action requiring approval is put to the operator again
- **AND** the run's selected protections are unchanged

#### Scenario: Not answering refuses

- **WHEN** an escalated action is not answered within the Hub's waiting period
- **THEN** the action is refused

#### Scenario: Granted actions are not escalated

- **WHEN** an action would be permitted under the operator's selected protections
- **THEN** it proceeds without being put to the operator

#### Scenario: A provider without the capability degrades quietly

- **WHEN** a provider gives the Hub no opportunity to ask before refusing
- **THEN** the action is refused as it is today
- **AND** no broken or unanswerable prompt is presented

### Requirement: Operator answers are attributed and recorded

Every question put to the operator and every answer given SHALL be recorded against the run and
agent that caused it, with the time it was asked and the time it was answered.

An escalated action that was allowed SHALL be recorded as such, naming the action allowed. It MUST
NOT be recorded as though the agent had been permitted it by its own protections.

#### Scenario: A question and its answer are recorded together

- **WHEN** an operator answers a question from an agent
- **THEN** the question, the answer, the asking agent, the run, and both times are recorded

#### Scenario: An allowance is recorded as an allowance

- **WHEN** the operator allows an escalated action
- **THEN** the record names the action and that the operator allowed it
- **AND** does not present it as permitted by the run's own protections
