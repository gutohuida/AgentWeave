## ADDED Requirements

### Requirement: No Copilot hook decides a call or a turn

The Hub SHALL NOT install, for an agent whose tool calls it answers over Copilot's approval protocol, a Copilot hook that allows, denies or rewrites a tool call or that forces a turn to continue, and SHALL NOT trust the agent's workspace folder on Copilot's behalf.

A hook that answers a permission pre-empts the approval protocol: the request never reaches the Hub.
That takes the decision away from the Hub's own judge, from the operator's cards and from the record
of decisions, and a denial made there is one the operator never sees.

A hook that decides before a tool runs lets the call through when it is slow, so it cannot serve as
a denial control.

A hook that forces a turn to continue after the agent stopped is a backstop. The operator-in-the-loop
design deliberately has none: an agent that needs an answer asks, and a turn that ends without asking
has ended.

Trusting the workspace folder would load the repository's own hooks and servers into the run,
including hooks written for a different CLI.

#### Scenario: The agent's Copilot home holds no deciding hook

- **WHEN** the Hub writes a Copilot agent's configuration
- **THEN** it contains no hook for permission requests or for the moment before a tool runs
- **AND** it contains no hook that stops or continues an agent or subagent

#### Scenario: A write reaches the Hub's approval channel

- **WHEN** a Copilot run under the posture the Hub answers asks to write a file
- **THEN** the request reaches the Hub's approval channel
- **AND** the decision is recorded as every other decision is

#### Scenario: A turn that ends is not continued by the Hub

- **WHEN** a Copilot agent ends its turn without asking the operator anything
- **THEN** the turn ends, and nothing the Hub installed makes it continue

#### Scenario: The repository's hooks do not load

- **WHEN** a Copilot run starts in a repository that carries its own hooks
- **THEN** the run's environment does not mark the workspace as trusted
- **AND** the agent's Copilot configuration names no trusted folder
