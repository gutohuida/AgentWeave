## MODIFIED Requirements

### Requirement: Launchability reports the runner that would actually be spawned

An agent's reported launchability SHALL be derived from the runner bound to it whenever one is
bound, regardless of how the agent came to exist. The probe and the spawn SHALL NOT be able to
disagree about the same agent.

No agent is exempt from this by how it came to exist. Every agent is created by the operator or
by a governed agent request; there is no self-registered agent that manages its own execution, so
there is no population for which an absent runner is legitimate rather than unbound.

**The probe SHALL report the same set of agents the roster offers.** An agent the roster excludes
by lifecycle SHALL NOT appear in a launchability report that did not ask for that lifecycle, and
the probe SHALL take the lifecycle selector the roster takes, with the same default. Reporting an
archived agent as runnable is the probe and the spawn disagreeing about the same agent in the other
direction: triggering it is refused with the reason it is archived, one call after the probe said
it could run.

The lifecycle exclusion SHALL be applied after every source of agent names has contributed, not to
the agent query alone. A name reaches this report from the session configuration as well as from
the agent table, and a filter on one source lets the same agent back in through the other. An agent
with no agent-table row cannot have been archived and SHALL count as open.

An agent excluded by lifecycle SHALL be excluded from the report entirely rather than reported with
a lifecycle reason inside its verdict. Lifecycle is the roster's fact and the roster states it; a
second statement of it inside the probe would be a second vocabulary for one condition.

#### Scenario: An agent with a runner bound
- **WHEN** launchability is probed for an agent that has a runner bound
- **THEN** the verdict SHALL describe that runner
- **AND** the agent SHALL be reported launchable if that runner is launchable

#### Scenario: An agent with no runner bound
- **WHEN** launchability is probed for an agent with no runner bound
- **THEN** the verdict SHALL say that no runner is bound and what would fix it
- **AND** SHALL NOT name a CLI after the agent

#### Scenario: The probe and the spawn agree
- **WHEN** an agent is reported launchable
- **THEN** triggering it SHALL use the same runner the probe described

#### Scenario: An archived agent is not reported as launchable
- **WHEN** launchability is probed for a project holding an archived agent, without asking for that lifecycle
- **THEN** the archived agent SHALL NOT appear in the report
- **AND** no agent in the report SHALL be one that triggering would refuse as archived

#### Scenario: An archived agent is probed when explicitly asked for
- **WHEN** launchability is probed for the archived lifecycle
- **THEN** the archived agent SHALL appear with the verdict its bound runner supports

#### Scenario: An archived agent known only to the session configuration is excluded too
- **WHEN** launchability is probed and an archived agent's name is also present in the project's session configuration
- **THEN** that agent SHALL still be absent from the default report
