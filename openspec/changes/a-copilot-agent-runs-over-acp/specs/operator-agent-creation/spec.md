## ADDED Requirements

### Requirement: A Copilot agent's native files are written into a Hub-owned home

When a Copilot agent is created, or its runner binding or charter changes, the Hub SHALL write that agent's Copilot files into a Copilot home the Hub owns for that agent, and SHALL NOT write them into the project's repository.

The files SHALL include two things:

- A Copilot custom agent named after the agent. It carries the agent's stable context (its identity,
  the project's instructions and its charter) and a statement that this context takes precedence
  over the repository's own instruction files where they conflict.
- The configuration that gives Copilot the Hub's `agentweave` MCP server.

Per-turn material SHALL NOT be written there. That means the workspace, the specification in view,
the team, other agents' history and the turn notices, which reach each turn with its prompt.

The Hub SHALL bring these files up to date before every Copilot turn, so that a charter,
instructions or model edit made anywhere reaches the next turn. The home's location SHALL be derived
only from identifiers the Hub has checked to be single, safe path components, because a project's
identifier can come from a marker file inside the project's own folder. The files SHALL carry no credential. A failure to write
them SHALL NOT undo the agent's creation. The same failure before a turn SHALL refuse that turn with
a reason.

The Hub SHALL own the home's whole configuration surface, not only the files it writes. Before every
Copilot turn it SHALL remove from the home any hook, plugin, MCP configuration or custom agent it did
not write, and any setting that trusts a folder or grants a permission, so that nothing left in the
home can answer a permission request in the Hub's place.

When Copilot does not select the Hub's custom agent for a turn, the Hub SHALL leave no other custom
agent selected for that turn, and SHALL NOT send the prompt while a custom agent it did not write is
selected.

#### Scenario: Creating a Copilot agent writes its custom agent

- **WHEN** an operator creates an agent bound to a `copilot` runner
- **THEN** the agent's Hub-owned Copilot home contains a custom agent file named after the agent, holding its charter and the precedence statement
- **AND** the project's repository contains no new file

#### Scenario: An edited charter reaches the next turn

- **WHEN** an operator edits the charter of a Copilot agent and then triggers it
- **THEN** the custom agent file the turn uses carries the edited charter

#### Scenario: The files hold no credential

- **WHEN** a Copilot agent's home has been written for a run
- **THEN** none of its files contains the run's token

#### Scenario: A project identifier that is not a safe path component

- **WHEN** a Copilot turn is triggered in a project whose identifier contains a path separator or is `..`
- **THEN** the Hub writes no file for it and refuses the turn with a reason

#### Scenario: The custom agent is not selected

- **WHEN** Copilot does not select the Hub's custom agent for a turn, or selects one that is not the Hub's
- **THEN** the turn receives its stable context with its prompt instead
- **AND** no custom agent is selected for the turn
- **AND** the run's timeline says why

#### Scenario: A hook left in the agent's Copilot home

- **WHEN** a file the Hub did not write has been placed in the hooks directory of a Copilot agent's home, and the agent is triggered
- **THEN** the file is gone before the Copilot process starts
- **AND** the turn's permission requests reach the Hub
