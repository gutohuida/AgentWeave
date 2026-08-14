# agent-capability-plane

## ADDED Requirements

### Requirement: An agent can record, read and decide requirement evidence

The system SHALL offer agents tools to record evidence against a requirement, to read the evidence a project holds, and to accept or reject it.

Evidence is what opens integration. A system that gates merging on accepted evidence and offers no
way for an agent to produce any has built a pipeline only its operator can drive, one HTTP call at a
time.

Deciding SHALL be a single operation covering both acceptance and rejection. Offering only
acceptance would make rejection unreachable from the agent plane while the underlying operation
allows it, which is the surface disagreement this capability exists to prevent.

Reading SHALL be offered alongside deciding. A decision names a specific piece of evidence, so an
agent with no way to discover what evidence exists cannot decide anything, and the capability to
decide is decorative without it.

The evidence an agent reads SHALL identify who produced it. An agent may not decide evidence it
produced itself, so one that cannot see the producer discovers that rule only by being refused.

Recording SHALL state, where the agent will read it, that evidence is what allows approved work to
merge. The consequence of recording nothing is reported to the operator and never to the agent that
could have prevented it.

Constrained values SHALL be constrained identically on both surfaces, and open ones SHALL stay open.
A tool that accepts less than its route makes the plane narrower than the system, which this
capability forbids in either direction.

#### Scenario: An agent records evidence

- **WHEN** an agent records evidence against a requirement it has satisfied
- **THEN** the evidence is held against that requirement
- **AND** it awaits a decision

#### Scenario: An agent reads what is awaiting a decision

- **WHEN** an agent asks for the evidence a project holds
- **THEN** it receives it, including who produced each piece

#### Scenario: A granted agent accepts another agent's evidence

- **WHEN** an agent the operator has granted acceptance decides evidence another agent produced
- **THEN** the decision is recorded

#### Scenario: An agent cannot decide its own evidence

- **WHEN** an agent decides evidence it produced itself
- **THEN** the system refuses
- **AND** says another agent or the operator decides

#### Scenario: An ungranted agent is refused

- **WHEN** an agent without the grant decides evidence
- **THEN** the system refuses
- **AND** says the capability is the operator's to confer

#### Scenario: Rejection is available

- **WHEN** an agent with the grant rejects evidence
- **THEN** the rejection is recorded, as an acceptance would be
