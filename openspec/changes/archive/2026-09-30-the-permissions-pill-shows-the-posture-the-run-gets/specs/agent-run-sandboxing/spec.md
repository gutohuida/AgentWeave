## RENAMED Requirements

- FROM: `### Requirement: Introducing an enforced posture does not change existing runs`
- TO: `### Requirement: The built-in posture a run receives is the posture shown for it`

## MODIFIED Requirements

### Requirement: The built-in posture a run receives is the posture shown for it

The built-in posture a run receives when neither its conversation nor its agent states one SHALL be decided in one place per provider, and every surface that shows a posture at rest SHALL show that posture.

For a run the Hub can answer, that posture is the one in which the Hub decides each tool call
against the run's workspace. A posture that accepts edits but leaves execution to a prompt nobody
can answer lets an agent write code and never run it. A run the Hub cannot answer receives the
posture that accepts edits, and a provider whose own default already confines the run to its
workspace keeps that default.

Flags that serve the enforced posture SHALL be emitted only for that posture, and only where the
mechanism answering them is present.

#### Scenario: The default spawned is the default shown

- **WHEN** a non-yolo run is spawned with no posture selected by its conversation or its agent
- **THEN** it is spawned under the built-in posture for its provider
- **AND** that is the posture the app showed for it at rest

#### Scenario: Other postures carry no enforcement machinery

- **WHEN** a run selects a posture other than the enforced one
- **THEN** its command carries nothing referring to the enforcement mechanism

#### Scenario: No enforcement is claimed without an answerer

- **WHEN** the enforced posture is selected but no mechanism is present to answer its requests
- **THEN** the command does not claim enforcement it cannot perform

### Requirement: The default posture lets an agent work inside its own workspace

The permission posture the Hub imposes by default SHALL permit an agent to do work within its own
workspace without further configuration.

The Hub MUST NOT impose by default a posture whose decisions can only be resolved by an operator
prompt, unless a surface exists through which an operator can actually answer that prompt. A posture
that defers every decision to an absent answerer denies everything and is indistinguishable from a
broken run.

Isolation SHALL continue to be carried by the agent's workspace boundary, not by withholding
permission inside it. The default posture SHALL NOT widen what an agent can affect outside its own
workspace. Where the default posture is the one in which the Hub decides each tool call against the
workspace, it narrows it: a call the Hub judges to reach outside the workspace is refused.

#### Scenario: A newly created agent can edit files in its own workspace

- **WHEN** the Hub spawns a non-yolo agent that has been given no permission configuration
- **AND** that agent writes a file inside its own workspace
- **THEN** the write succeeds
- **AND** no approval was required from an operator

#### Scenario: A posture requiring an answer is not imposed by default

- **WHEN** no operator-facing approval surface exists for a provider
- **THEN** the Hub does not default that provider's runs to a posture that asks for approval

#### Scenario: The default posture never widens the workspace boundary

- **WHEN** an agent acts under the default posture
- **THEN** its ability to affect anything outside its own workspace is not widened by that posture
- **AND** where the default is the posture in which the Hub decides each tool call, a call the Hub
  judges to reach outside the workspace is refused
