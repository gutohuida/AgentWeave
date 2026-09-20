## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: A refusal that names a runner's holders names where to reach each one

Deleting a runner that agents are bound to SHALL be refused, and the refusal SHALL name every
holder together with enough to reach it: where a named holder is archived, the refusal SHALL say so
and SHALL say where an archived agent is found.

A refusal naming a repair the operator cannot locate is a wall, not a refusal. The default roster
excludes archived agents deliberately, so a bound-delete refusal that names one without qualifying
it sends the operator to a list the name is not in. The same shape was met once already on the
charter route and cost the operator the deletion.

The archived state SHALL be stated as part of the holder's name in the refusal rather than as a
separate count, so that an operator reading one sentence knows which of the named agents they will
not find.

#### Scenario: A runner held only by an archived agent
- **WHEN** an operator deletes a runner whose only bound agent is archived
- **THEN** the refusal SHALL name that agent as archived
- **AND** SHALL state where an archived agent can be found

#### Scenario: A runner held by both an open and an archived agent
- **WHEN** an operator deletes a runner bound to one open and one archived agent
- **THEN** the refusal SHALL name both
- **AND** SHALL qualify only the archived one

#### Scenario: A runner held only by open agents
- **WHEN** an operator deletes a runner bound only to agents in the default roster
- **THEN** the refusal SHALL name them without any archived qualification
