# agent-configuration

## ADDED Requirements

### Requirement: The operator can grant an agent the authority to accept evidence

The system SHALL let the operator confer, and withdraw, an agent's authority to accept or reject requirement evidence.

Authority over what ships is the operator's to give. A capability enforced in the system but
settable nowhere is one no agent can ever hold, which makes the enforcement a refusal of everyone.

The grant SHALL be presented separately from capabilities that only widen what an agent can read.
Accepting evidence decides whether work is allowed to merge; grouping it with reading tells the
operator it is a kind of reading.

The surface SHALL say what the grant does not confer — that a granted agent still cannot accept
evidence it produced itself.

A project that has granted no agent SHALL still be able to accept evidence, as the operator.

#### Scenario: The operator grants acceptance

- **WHEN** the operator grants an agent the authority to accept evidence
- **AND** reads that agent's configuration back
- **THEN** the grant is shown as held

#### Scenario: The grant is withdrawable

- **WHEN** the operator withdraws the grant
- **THEN** the agent is refused when it next decides evidence

#### Scenario: Granting is not conferred by a charter

- **WHEN** an agent is bound to a charter describing a reviewer
- **THEN** it holds no acceptance authority until the operator grants it
