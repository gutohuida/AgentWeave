## ADDED Requirements

### Requirement: Copilot's built-in GitHub server is off unless the operator enables it for that agent

A Copilot agent's runs SHALL start with Copilot's built-in GitHub MCP server disabled unless the operator has enabled it for that agent, and under the posture in which the Hub decides, a call to that server SHALL be put to the operator, never allowed by the Hub.

That server acts on GitHub as the person signed in to Copilot. It opens issues, comments and pull
requests outside the agent's workspace. The Hub's own judgement is about the workspace and has no
ground to allow such an action on the operator's behalf.

Under full access such a call is allowed, as every call is. Under the posture in which the operator
decides, it goes to the operator, as every call does.

The setting SHALL be presented only for an agent bound to a `copilot` runner.

#### Scenario: The server is off by default

- **WHEN** a run starts for a Copilot agent whose operator has not enabled the GitHub server
- **THEN** the run starts with Copilot's built-in servers disabled

#### Scenario: Enabling it starts the server

- **WHEN** the operator enables the GitHub server for a Copilot agent and a run starts
- **THEN** the run starts without disabling Copilot's built-in servers

#### Scenario: A call to it is put to the operator

- **WHEN** a Copilot agent under the posture in which the Hub decides calls a tool of the GitHub server
- **THEN** the call is put to the operator as a card
- **AND** the Hub does not allow it on its own

#### Scenario: The setting appears only for Copilot agents

- **WHEN** the operator opens the settings of an agent bound to a runner other than `copilot`
- **THEN** no GitHub server setting is presented
