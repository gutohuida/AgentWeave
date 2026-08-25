## ADDED Requirements

### Requirement: Launchability reports the runner that would actually be spawned

An agent's reported launchability SHALL be derived from the runner bound to it whenever one is
bound, regardless of how the agent came to exist. The probe and the spawn SHALL NOT be able to
disagree about the same agent.

Today the bound-runner merge is gated on the agent not having self-registered. That exemption's
intent — a self-registered agent manages its own execution and legitimately has no runner — is
sound, but it is written as an assumption and never enforced: an agent that is both self-registered
and bound to a runner is reachable through two ordinary API calls. Such an agent is reported
unlaunchable, naming a CLI after the agent itself, while triggering it works normally. The probe is
the one the operator sees.

#### Scenario: A self-registered agent with a runner bound
- **WHEN** launchability is probed for a self-registered agent that has a runner bound
- **THEN** the verdict SHALL describe that runner
- **AND** the agent SHALL be reported launchable if that runner is launchable

#### Scenario: An agent with no runner bound
- **WHEN** launchability is probed for an agent with no runner bound
- **THEN** the verdict SHALL say that no runner is bound and what would fix it
- **AND** SHALL NOT name a CLI after the agent

#### Scenario: The probe and the spawn agree
- **WHEN** an agent is reported launchable
- **THEN** triggering it SHALL use the same runner the probe described
