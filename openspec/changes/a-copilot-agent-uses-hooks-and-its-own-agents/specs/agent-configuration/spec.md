## ADDED Requirements

### Requirement: Copilot's built-in GitHub server is off unless the operator enables it for that agent

A Copilot agent's runs SHALL start with Copilot's built-in GitHub MCP server disabled unless the operator has enabled it for that agent, and under the Workspace only posture a call to that server SHALL be put to the operator and SHALL NOT be allowed by the Hub's own judgement.

That server acts on GitHub as the person signed in to Copilot. It opens issues, comments and pull
requests outside the agent's workspace. The Hub's judgement is about the workspace, and a GitHub
action names no path in it, so that judgement would find nothing to refuse. It therefore has no
ground to allow such an action on the operator's behalf, and the call SHALL be decided before that
judgement is consulted. A call whose server cannot be identified SHALL be treated the same way while
the server is enabled.

The card SHALL say that the call acts on GitHub as the operator, and SHALL NOT say that Workspace only
would allow it.

Under Edit files such a call is refused, as a call to any server other than the Hub's own is. Under
full access it is allowed, as every call is. Under Ask me it goes to the operator, as every call does.

Where the server is enabled and Copilot reports it failed, needs sign-in, or was disabled, stopped
or not configured, the run SHALL record that it is unavailable. A server Copilot reports as still
starting SHALL NOT be reported as unavailable.

The setting SHALL be presented only for an agent bound to a `copilot` runner, and SHALL show the
value stored for that agent.

#### Scenario: The server is off by default

- **WHEN** a run starts for a Copilot agent whose operator has not enabled the GitHub server
- **THEN** the run starts with Copilot's built-in servers disabled

#### Scenario: Enabling it starts the server

- **WHEN** the operator enables the GitHub server for a Copilot agent and a run starts
- **THEN** the run starts without disabling Copilot's built-in servers

#### Scenario: A call to it is put to the operator

- **WHEN** a Copilot agent under Workspace only calls a tool of the GitHub server
- **THEN** the call is put to the operator as a card saying it acts on GitHub as them
- **AND** the Hub does not allow it on its own

#### Scenario: A failed server is reported

- **WHEN** the GitHub server is enabled for a Copilot agent and Copilot reports that it failed
- **THEN** the run's stream records that it is unavailable

#### Scenario: A server still starting is not reported

- **WHEN** the GitHub server is enabled and Copilot reports it as still starting
- **THEN** nothing is recorded about it being unavailable

#### Scenario: The setting appears only for Copilot agents

- **WHEN** the operator opens the settings of an agent bound to a runner other than `copilot`
- **THEN** no GitHub server setting is presented

#### Scenario: The setting shows what is stored

- **WHEN** the operator enables the GitHub server for a Copilot agent and reopens its settings
- **THEN** the setting shows it enabled
