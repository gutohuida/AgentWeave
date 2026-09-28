## ADDED Requirements

### Requirement: A Copilot run's posture is decided by the Hub over ACP

The Hub SHALL answer every permission request a Copilot run raises over the Agent Client Protocol, deciding it by the run's permission posture with the same shell and path judge the workspace posture uses for Claude, and SHALL NOT make that answer depend on the Hub's MCP server.

The Hub SHALL answer as follows:

- **Workspace only**, which is also how a run that states no posture is decided. A shell command
  SHALL be judged in the dialect of the shell Copilot reports running it. A command whose shell is
  not known SHALL be judged in every dialect the Hub reads, and refused if any refuses. A file change
  and an out-of-directory read SHALL be judged against the run's workspace, path by path, and one
  that names no path SHALL be refused. A call to the Hub's own `agentweave` tools SHALL be allowed.
  A call SHALL count as the Hub's own only when Copilot's own report of the call names the Hub's
  server and a tool the Hub's server serves. Text the model writes, such as a tool call's title,
  SHALL NOT decide which server a call belongs to. A tool call whose server Copilot did not report
  SHALL be refused, as SHALL a request kind the Hub does not recognise.
- **Ask me.** Every request except the Hub's own tools SHALL be put to the operator as a card while
  the request is held open. It SHALL be refused when the operator's wait runs out.
- **Full access.** The run SHALL be put into Copilot's allow-all mode. When the machine's Copilot
  policy has withdrawn that mode, the run SHALL fall back to deciding against its workspace, and
  SHALL say so in its timeline. It SHALL NOT approve through the Hub what the policy withheld.
- **Edit files.** A file change inside the workspace SHALL be allowed. Any other request except the
  Hub's own tools SHALL be refused.

The Hub SHALL answer every request exactly once, and SHALL NOT grant an approval for the rest of a
session in place of the request in front of it. A refusal the Hub decided without the operator
SHALL be recorded as other runtime refusals are.

A turn triggered with a specification document open SHALL have Copilot's file-writing tools
removed, whatever the posture. It SHALL run in Copilot's plan mode unless the Hub has recorded that
plan mode prevents the turn's specification duties.

#### Scenario: A command outside the workspace is refused under Workspace only

- **WHEN** a Copilot run under Workspace only asks to run a PowerShell command that writes to a path outside its workspace
- **THEN** the Hub answers the request with a refusal
- **AND** the refusal is recorded as a runtime refusal in the run's timeline

#### Scenario: A file change inside the workspace is allowed under Workspace only

- **WHEN** a Copilot run under Workspace only asks to edit a file inside its workspace
- **THEN** the Hub answers the request with a one-time allow

#### Scenario: The Hub's own tool is allowed under Ask me

- **WHEN** a Copilot run under Ask me asks to call the `agentweave` server's `send_message`
- **THEN** the Hub allows it without opening an operator card

#### Scenario: A command is put to the operator under Ask me

- **WHEN** a Copilot run under Ask me asks to run a shell command
- **THEN** an operator card opens and the request stays unanswered until the operator decides or the wait runs out
- **AND** a wait that runs out is answered with a refusal

#### Scenario: Full access withdrawn by policy

- **WHEN** a Copilot run is started under Full access and Copilot does not offer its allow-all option
- **THEN** the run decides each request against its workspace
- **AND** its timeline says that Full access is disabled by the machine's Copilot policy

#### Scenario: A run with no posture chosen

- **WHEN** a Copilot run whose conversation and agent state no permission posture asks to run a command that writes outside its workspace
- **THEN** the Hub answers the request with a refusal, as under Workspace only

#### Scenario: A foreign server named like the Hub's

- **WHEN** a Copilot run asks to call a tool of an MCP server named `agentweave-x`
- **THEN** the Hub judges the call as a foreign server's rather than allowing it as its own

#### Scenario: A tool call whose title imitates the Hub's tool

- **WHEN** a Copilot run under Ask me asks to call a tool whose displayed title reads `agentweave-send_message`, and Copilot's own report of the call names another server or no server
- **THEN** the Hub does not allow it as its own tool

#### Scenario: A tool call whose server Copilot did not report

- **WHEN** a Copilot run under Workspace only raises a permission request for a tool call that Copilot has not reported as belonging to any MCP server
- **THEN** the Hub answers the request with a refusal that says the server was not reported

#### Scenario: An unknown request kind

- **WHEN** a Copilot run raises a permission request of a kind the Hub does not recognise
- **THEN** the Hub answers it with a refusal rather than leaving it unanswered

#### Scenario: A specification turn has no write tools

- **WHEN** a Copilot turn is triggered with a specification document open under Full access
- **THEN** the spawned command removes Copilot's file-writing tools
- **AND** the session is set to plan mode unless plan mode has been recorded as preventing specification duties

#### Scenario: Approvals do not depend on MCP

- **WHEN** a Copilot run's `agentweave` MCP server fails to start
- **THEN** the run's permission requests are still answered by the Hub under the run's posture

### Requirement: A Copilot run receives no GitHub token it was not given

The Hub SHALL remove `GH_TOKEN`, `GITHUB_TOKEN` and `COPILOT_GITHUB_TOKEN` from a Copilot run's environment unless the agent's own configured environment names them.

A token in the environment silently replaces the operator's Copilot sign-in. A token the Hub
happened to inherit would therefore change whose plan and whose policy a run is billed and governed
by.

#### Scenario: An ambient token is not passed on

- **WHEN** the Hub process has `GH_TOKEN` set and a Copilot agent's configuration does not name it
- **THEN** the spawned Copilot process's environment has no `GH_TOKEN`

#### Scenario: An agent that names a token keeps it

- **WHEN** a Copilot agent's configured environment names `COPILOT_GITHUB_TOKEN`
- **THEN** the spawned Copilot process receives that variable as the agent configured it
