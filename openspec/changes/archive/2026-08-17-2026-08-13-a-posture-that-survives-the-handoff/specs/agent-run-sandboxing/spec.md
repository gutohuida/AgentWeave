# agent-run-sandboxing

## MODIFIED Requirements

### Requirement: The default posture lets an agent work inside its own workspace

The permission posture the Hub imposes by default SHALL permit an agent to do work within its own
workspace without further configuration, and **doing work includes running what it wrote**.

An agent that can edit a file but cannot execute a command can produce code and never evidence. It
is then asked to report whether its work is correct with no way to find out, and the honest answer —
"unverified" — is indistinguishable in a transcript from the dishonest one. Where a provider offers
a posture under which the Hub itself answers each request against the run's own workspace, that
posture SHALL be the default, because it is narrower for writes than one that accepts every edit
unchecked and it permits the verification the work depends on.

The Hub MUST NOT impose by default a posture whose decisions can only be resolved by an operator
prompt, unless a surface exists through which an operator can actually answer that prompt. A posture
that defers every decision to an absent answerer denies everything and is indistinguishable from a
broken run. **Where the answering surface is not configured for a particular run, the Hub SHALL fall
back to a posture that needs no answerer** rather than impose one that cannot be answered.

Isolation SHALL continue to be carried by the agent's workspace boundary, not by withholding
permission inside it.

#### Scenario: A newly created agent can edit files in its own workspace

- **WHEN** the Hub spawns a non-yolo agent that has been given no permission configuration
- **AND** that agent writes a file inside its own workspace
- **THEN** the write succeeds
- **AND** no approval was required from an operator

#### Scenario: A newly created agent can run what it wrote

- **WHEN** the Hub spawns a non-yolo agent that has been given no permission configuration
- **AND** that agent runs a command inside its own workspace
- **THEN** the command executes
- **AND** no approval was required from an operator

#### Scenario: The default names its answerer

- **WHEN** a non-yolo run is spawned with no operator-chosen posture and the Hub's own tool server
  configured
- **THEN** the spawned command names the tool that answers its permission requests

#### Scenario: A run with no answerer configured is not given a posture that needs one

- **WHEN** a non-yolo run is spawned with no operator-chosen posture and no tool server through
  which requests could be answered
- **THEN** the run receives a posture that requires no answerer

#### Scenario: A posture requiring an answer is not imposed by default

- **WHEN** no operator-facing approval surface exists for a provider
- **THEN** the Hub does not default that provider's runs to a posture that asks for approval

#### Scenario: The workspace boundary is unchanged

- **WHEN** an agent acts under the default posture
- **THEN** its ability to affect anything outside its own workspace is unchanged by that posture
