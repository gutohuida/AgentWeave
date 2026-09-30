## MODIFIED Requirements

### Requirement: An agent with no way to be launched SHALL say so, and SHALL NOT name a CLI after itself

Where an agent has no bound runner and nothing else supplies one, the Hub SHALL report that no runner
is bound. It SHALL NOT report a missing executable derived from the agent's own name.

This SHALL hold for every agent, whatever created it. The Hub SHALL NOT exempt an agent from the
unbound verdict on the strength of how it joined the project.

Measured on the trial Hub 2026-08-21: an agent whose `runner_id` was null was reported as
`Runner CLI 'probe-norunner' was not found in PATH.`, sending the operator to look for a binary named
after their own agent. The masking is recorded as already-fixed for the *bound* case in the Hub's own
source comments; this is the branch that fix did not cover.

An agent that carries its runner in synchronised session configuration rather than a bound runner
record SHALL be unaffected: it is launchable, and reporting it as unbound would refuse something that
works.

#### Scenario: An unbound agent is reported as unbound

- **GIVEN** an agent with no bound runner and no runner in its synchronised configuration
- **WHEN** the Hub reports whether it can be launched
- **THEN** the reason states that no runner is bound
- **AND** the reason does not name any executable derived from the agent's name

#### Scenario: A configured agent with no bound runner is still launchable

- **GIVEN** an agent whose synchronised configuration names a runner and which has no bound runner
- **WHEN** the Hub reports whether it can be launched
- **THEN** it is reported exactly as it was before this change

#### Scenario: The bound runner outranks synchronised configuration

- **GIVEN** an agent whose bound runner and synchronised configuration name different runners
- **WHEN** the Hub reports which runner it would use
- **THEN** it reports the bound runner, because that is what would actually be launched

#### Scenario: No agent is exempt by origin

- **GIVEN** any agent in the project with no bound runner and no runner in its synchronised configuration
- **WHEN** the Hub reports whether it can be launched, and when input for it is queued
- **THEN** both the launchability reason and the queue's waiting reason state that no runner is bound
- **AND** neither names an executable derived from the agent's name
