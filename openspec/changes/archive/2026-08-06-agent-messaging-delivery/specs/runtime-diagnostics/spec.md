## ADDED Requirements

### Requirement: Collaboration readiness is checkable before it is needed

The Hub SHALL be able to report, for a project's agents, whether agent-to-agent collaboration will
actually work — not merely whether the runner CLI is installed and authorized.

The report SHALL cover whether the tool surface will be invocable by that agent's provider, and
whether the address supplied to runs is the address the Hub is serving on. Each unmet condition
SHALL name what is wrong in terms an operator can act on.

This check MUST NOT require starting an agent run.

#### Scenario: An agent that cannot use its tools is reported

- **WHEN** collaboration readiness is reported for an agent whose provider would refuse its tool calls
- **THEN** the agent is reported as not collaboration-ready
- **AND** the reason names the refusal

#### Scenario: A mismatched callback address is reported

- **WHEN** the address the Hub would supply to runs is not the address it is serving on
- **THEN** collaboration readiness reports the mismatch
- **AND** names both addresses

#### Scenario: Readiness does not spawn agents

- **WHEN** collaboration readiness is reported
- **THEN** no agent run is started
