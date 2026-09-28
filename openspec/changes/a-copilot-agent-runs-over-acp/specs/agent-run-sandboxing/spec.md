## ADDED Requirements

### Requirement: A Copilot run's posture is decided by the Hub over ACP

The Hub SHALL answer every permission request a Copilot run raises over the Agent Client Protocol, deciding it by the run's permission posture with the same shell and path judge the workspace posture uses for Claude, and SHALL NOT make that answer depend on the Hub's MCP server.

The Hub decides only what Copilot asks it. Copilot runs the shell commands it classes as read-only
without raising any request, so the Hub never sees or judges those; that is a difference from a
Claude run, whose every shell command is judged. The Hub SHALL NOT claim to judge what Copilot did
not ask about.

The Hub SHALL answer as follows:

- **Workspace only**, which is also how a run that states no posture is decided. A shell command
  Copilot asks about SHALL be judged in the dialect of the shell Copilot reports running it. A
  command whose shell is not known SHALL be judged in every dialect the Hub reads, and refused if any
  refuses. A shell request that carries no command text SHALL be refused. A file change and an
  out-of-directory read SHALL be judged against the run's workspace, path by path, and one that names
  no path SHALL be refused. A web address request SHALL be allowed only when Copilot reports it as
  coming from its own fetch tool and it does not ask to bypass Copilot's sandbox; any other web
  address request SHALL be judged as the text of a shell command is, so only the run's own Hub
  passes. A call to the Hub's own `agentweave` tools SHALL be allowed. A call SHALL count as the
  Hub's own only when Copilot's own report of the call names the Hub's server and a tool the Hub's
  server serves, and Copilot reported that server as loaded from the Hub's own configuration and
  from no workspace or plugin source. Text the model writes, such as a tool call's title, SHALL NOT
  decide which server a call belongs to. A tool call whose server Copilot did not report SHALL be
  refused before any rule about a particular server applies, as SHALL a request kind the Hub does
  not recognise.
- **Ask me.** Every request except the Hub's own tools SHALL be put to the operator as a card while
  the request is held open. A card for a tool call whose server Copilot did not report SHALL say so,
  and SHALL NOT name the server from text the model wrote. It SHALL be refused when the operator's
  wait runs out.
- **Full access.** The run SHALL be put into Copilot's allow-all mode. When Copilot refuses that
  mode, the run SHALL fall back to deciding against its workspace, and SHALL say so in its timeline,
  quoting the reason Copilot gave. It SHALL NOT approve through the Hub what Copilot withheld.
- **Edit files.** A file change inside the workspace SHALL be allowed. Any other request except the
  Hub's own tools SHALL be refused.

Under every posture except Full access, the Hub SHALL set Copilot's session mode on every turn,
including a resumed one, and SHALL confirm before sending the prompt that Copilot's allow-all mode is
off. A turn whose allow-all mode cannot be turned off SHALL NOT be prompted, and SHALL fail with the
reason. A runner option that widens what Copilot approves by itself SHALL NOT reach a run under any
posture except Full access.

The Hub SHALL answer every request exactly once, and SHALL NOT grant an approval for the rest of a
session in place of the request in front of it. A refusal the Hub decided without the operator
SHALL be recorded as other runtime refusals are. Deciding one request SHALL NOT stall the Hub's
handling of other runs, however long resolving a path takes.

A turn triggered with a specification document open SHALL have Copilot's file-editing tools
removed, except its file-creation tool, whatever the posture. The Hub SHALL refuse every file
change such a turn asks for, in every posture, except a write the Hub itself recognises as the
run's own call to the Hub, and SHALL NOT put such a turn into Copilot's allow-all mode, so that
every file change reaches the Hub. It SHALL NOT run in Copilot's plan mode until a drive has shown
that plan mode leaves the turn's specification duties intact and cannot leave the turn waiting on
a request nobody can answer.

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

#### Scenario: Full access withdrawn by Copilot

- **WHEN** a Copilot run is started under Full access and Copilot does not offer its allow-all option, or refuses to turn it on
- **THEN** the run decides each request against its workspace
- **AND** its timeline says that Full access was not granted, quoting the reason Copilot gave

#### Scenario: A read-only command Copilot does not ask about

- **WHEN** a Copilot run under Workspace only runs a shell command that Copilot classes as read-only
- **THEN** Copilot raises no permission request and the Hub makes no decision about it
- **AND** nothing the Hub records claims that the command was judged

#### Scenario: A web address raised by a shell command

- **WHEN** a Copilot run under Workspace only raises a web address request for `https://example.com` that Copilot reports as belonging to a shell command
- **THEN** the Hub answers the request with a refusal

#### Scenario: A web address from Copilot's fetch tool

- **WHEN** a Copilot run under Workspace only raises a web address request that Copilot reports as belonging to its fetch tool, without asking to bypass its sandbox
- **THEN** the Hub answers the request with a one-time allow

#### Scenario: A request to bypass Copilot's sandbox

- **WHEN** a Copilot run under Workspace only raises a web address request that asks to bypass Copilot's sandbox
- **THEN** the Hub answers the request with a refusal

#### Scenario: A resumed session left in plan mode

- **WHEN** a Copilot conversation's earlier turn left its session in plan mode and the next turn is not a specification turn
- **THEN** the Hub sets the session back to its ordinary mode before sending the prompt

#### Scenario: A resumed session that loads with allow-all on

- **WHEN** a Copilot run under Workspace only loads a session whose allow-all mode is on
- **THEN** the Hub turns allow-all off before sending the prompt
- **AND** if allow-all stays on, the turn fails with the reason and no prompt is sent

#### Scenario: A runner option that widens approvals

- **WHEN** a Copilot runner's options include `--yolo` or `--allow-tool` and a run is started under Workspace only
- **THEN** the spawned command does not carry that option
- **AND** the run's timeline names the option that was removed

#### Scenario: A path that names a network share

- **WHEN** a Copilot run asks to edit a path on a network share that takes many seconds to resolve
- **THEN** other runs and the Hub's routes keep being served while that request is decided

#### Scenario: A run with no posture chosen

- **WHEN** a Copilot run whose conversation and agent state no permission posture asks to run a command that writes outside its workspace
- **THEN** the Hub answers the request with a refusal, as under Workspace only

#### Scenario: A foreign server named like the Hub's

- **WHEN** a Copilot run asks to call a tool of an MCP server named `agentweave-x` or `agentweave__x`
- **THEN** the Hub judges the call as a foreign server's rather than allowing it as its own

#### Scenario: The Hub's server name with a tool the Hub does not serve

- **WHEN** a Copilot run under Workspace only asks to call a tool the Hub's server does not serve, on a server Copilot reports as `agentweave`, with a command argument that writes outside the workspace
- **THEN** the Hub judges the call as a foreign server's and answers it with a refusal

#### Scenario: A repository claims the Hub's server name

- **WHEN** Copilot reports that the server named `agentweave` was loaded from the workspace or from a plugin
- **THEN** no call to that server is allowed as the Hub's own
- **AND** the run's timeline says why

#### Scenario: A tool call whose title imitates the Hub's tool

- **WHEN** a Copilot run under Ask me asks to call a tool whose displayed title reads `agentweave-send_message`, and Copilot's own report of the call names another server or no server
- **THEN** the Hub does not allow it as its own tool

#### Scenario: A tool call whose server Copilot did not report

- **WHEN** a Copilot run under Workspace only raises a permission request for a tool call that Copilot has not reported as belonging to any MCP server
- **THEN** the Hub answers the request with a refusal that says the server was not reported

#### Scenario: A shell request with no command text

- **WHEN** a Copilot run under Workspace only raises a shell permission request that carries no command text
- **THEN** the Hub answers the request with a refusal

#### Scenario: An unknown request kind

- **WHEN** a Copilot run raises a permission request of a kind the Hub does not recognise
- **THEN** the Hub answers it with a refusal rather than leaving it unanswered

#### Scenario: A specification turn has no write tools

- **WHEN** a Copilot turn is triggered with a specification document open under Full access
- **THEN** the spawned command removes Copilot's file-editing tools other than its file-creation tool
- **AND** the session's allow-all mode is off before the prompt is sent
- **AND** a request to create a file in the workspace is refused and recorded as a runtime refusal
- **AND** the session is not put into plan mode while no drive has shown plan mode to be safe for specification turns

#### Scenario: Approvals do not depend on MCP

- **WHEN** a Copilot run's `agentweave` MCP server fails to start
- **THEN** the run's permission requests are still answered by the Hub under the run's posture

### Requirement: A Copilot run receives no GitHub token or permission override it was not given

The Hub SHALL remove `GH_TOKEN`, `GITHUB_TOKEN` and `COPILOT_GITHUB_TOKEN` from every Copilot process's environment unless the agent's own configured environment names them, and SHALL remove Copilot's allow-all and folder-trust variables from it always.

A token in the environment silently replaces the operator's Copilot sign-in. A token the Hub
happened to inherit would therefore change whose plan and whose policy a run is billed and governed
by.

`COPILOT_ALLOW_ALL` approves every tool without asking and, set to `true`, also trusts the working
folder, which loads the repository's own hooks, plugins and MCP servers. The Hub SHALL remove it,
and the other variables Copilot reads to widen approvals or trust a folder, from every Copilot
process it starts, whether the Hub inherited them or the agent's configuration names them. When the
agent's configuration names one, the run's timeline SHALL say it was removed and that the Full
access posture is the way to grant it. The Copilot home a run uses SHALL be the one the Hub chose
for it, whatever the environment names.

Copilot also reads its model provider, its model and an offline switch from the environment. A
provider variable the Hub happened to inherit would silently send a subscription run to another
provider. The Hub SHALL remove every provider variable, the model variable and the offline variable
from every Copilot process it starts for a runner that has no provider configured, whether the Hub
inherited them or the agent's configuration names them, and when the agent's configuration names
one, the run's timeline SHALL say it was removed.

#### Scenario: An ambient token is not passed on

- **WHEN** the Hub process has `GH_TOKEN` set and a Copilot agent's configuration does not name it
- **THEN** the spawned Copilot process's environment has no `GH_TOKEN`

#### Scenario: An agent that names a token keeps it

- **WHEN** a Copilot agent's configured environment names `COPILOT_GITHUB_TOKEN`
- **THEN** the spawned Copilot process receives that variable as the agent configured it

#### Scenario: An ambient allow-all variable is not passed on

- **WHEN** the Hub process has `COPILOT_ALLOW_ALL=true` set and a Copilot run is started under Workspace only
- **THEN** the spawned Copilot process's environment has no `COPILOT_ALLOW_ALL`
- **AND** the run's permission requests are still decided by the Hub

#### Scenario: An ambient provider variable is not passed on

- **WHEN** the Hub process has `COPILOT_PROVIDER_BASE_URL` and `COPILOT_MODEL` set and a Copilot run is started on a runner with no provider configured
- **THEN** the spawned Copilot process's environment has neither variable, nor any other variable whose name begins `COPILOT_PROVIDER_`

#### Scenario: An agent that names the allow-all variable

- **WHEN** a Copilot agent's configured environment names `COPILOT_ALLOW_ALL`
- **THEN** the spawned Copilot process's environment has no `COPILOT_ALLOW_ALL`
- **AND** the run's timeline says it was removed and names the Full access posture
