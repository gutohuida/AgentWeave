## ADDED Requirements

### Requirement: Copilot's built-in GitHub server is off unless the operator enables it for that agent

A Copilot agent's runs SHALL start with Copilot's built-in GitHub MCP server disabled unless the operator has enabled it for that agent, and while it is enabled, under the Workspace only posture, a call Copilot asks the Hub to decide for any MCP server other than the Hub's own SHALL be put to the operator and SHALL NOT be allowed by the Hub's own judgement.

That server acts on GitHub as the person signed in to Copilot. It opens issues, comments and pull
requests outside the agent's workspace. The Hub's judgement is about the workspace, and a GitHub
action names no path in it, so that judgement would find nothing to refuse. It therefore has no
ground to allow such an action on the operator's behalf, and the call SHALL be decided before that
judgement is consulted. Copilot may bring more than one built-in server, and a GitHub server need not
carry the name the Hub expects, so the rule SHALL cover every server Copilot reports other than the
Hub's own, not only one named for GitHub.

Copilot approves on its own, without asking the Hub, a call it knows to be read-only, and with the
server enabled it offers only its read-only GitHub tools. Such a call is not put to the operator,
and the setting SHALL be described to the operator as giving the agent read-only GitHub tools that
Copilot runs without asking, in every posture, and as not governing the `gh` command run in a shell.
A runner setting that adds GitHub tools beyond the read-only ones, or adds MCP servers of its own,
SHALL be removed from a run that does not have full access, and the run SHALL say it was removed,
as for every other runner setting that widens what Copilot approves on its own. Tools that write to
GitHub are therefore available only to a run with full access, where every call is allowed. Settings in the
agent's Copilot home that would add them SHALL be removed from that home.

A call whose server Copilot did not report SHALL be refused, as it is with the server disabled. The
Hub cannot say what such a call acts on, and enabling the GitHub server SHALL NOT change how a call
the Hub cannot attribute is treated.

The card SHALL name the server Copilot reported. It SHALL say that the call acts on GitHub as the
operator only for the GitHub server, and SHALL NOT say that Workspace only would allow the call.

A setting stored for the agent SHALL enable the server only when it is the value true; any other
stored value leaves it disabled.

Under Edit files such a call is refused, as a call to any server other than the Hub's own is. Under
full access it is allowed, as every call is. Under Ask me a call Copilot asks the Hub about goes to
the operator, as every such call does.

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

#### Scenario: A call Copilot asks about is put to the operator

- **WHEN** Copilot asks the Hub to decide a call to a tool of the GitHub server for an agent under
  Workspace only
- **THEN** the call is put to the operator as a card saying it acts on GitHub as them
- **AND** the Hub does not allow it on its own

#### Scenario: A read-only GitHub call runs without a card

- **WHEN** the GitHub server is enabled and the agent calls one of its read-only tools, which
  Copilot approves itself
- **THEN** no card is raised and the call is recorded in the run's stream

#### Scenario: A runner setting that adds GitHub write tools is removed

- **WHEN** a Copilot runner's settings would add GitHub tools beyond the read-only ones and the run
  does not have full access
- **THEN** the run starts without that setting
- **AND** the run's stream says it was removed

#### Scenario: The setting says what it gives

- **WHEN** the operator reads the GitHub server setting of a Copilot agent
- **THEN** it says the agent gets read-only GitHub tools that Copilot runs without asking

#### Scenario: Any other server's call is put to the operator under its own name

- **WHEN** the GitHub server is enabled and Copilot asks the Hub to decide a call, for an agent
  under Workspace only, to a tool of an MCP server Copilot reports under a name other than the
  GitHub server's or the Hub's own
- **THEN** the call is put to the operator as a card naming that server
- **AND** the card does not say the call acts on GitHub

#### Scenario: A call whose server is unknown is refused

- **WHEN** the GitHub server is enabled and Copilot asks to run an MCP tool without reporting its
  server
- **THEN** the call is refused, as it is with the server disabled
- **AND** no card is raised for it

#### Scenario: A stored value that is not true leaves the server off

- **WHEN** a Copilot agent's stored setting for the GitHub server is anything other than the value
  true, including the text "false"
- **THEN** its runs start with Copilot's built-in servers disabled

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
