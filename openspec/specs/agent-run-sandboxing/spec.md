# agent-run-sandboxing

## Purpose

Defines the sandbox posture the Hub imposes on a spawned agent run, independent of whatever
configuration happens to exist on the machine the Hub process runs on. Originated by
`openspec/changes/2026-08-06-claude-non-yolo-permission-mode`.

## Requirements

### Requirement: A non-yolo Claude run's sandbox posture is set by the Hub, not the host machine

The Hub SHALL pass an explicit, non-bypass permission mode to every non-yolo Claude run it spawns. A
non-yolo Claude run's actual permission behavior MUST NOT depend on the config file of the machine the
Hub process happens to run on.

#### Scenario: Non-yolo Claude run gets an explicit permission mode

- **WHEN** the Hub spawns a Claude agent whose run is not `yolo`
- **THEN** the spawned command line includes an explicit non-bypass permission mode flag

#### Scenario: Yolo Claude run is unaffected

- **WHEN** the Hub spawns a Claude agent whose run is `yolo`
- **THEN** the spawned command line includes `--dangerously-skip-permissions`
- **AND** does not include the non-yolo permission mode flag

### Requirement: A sandboxed non-yolo Claude agent can still use the Hub's own MCP tools

When a non-yolo Claude run has the Hub's own MCP server configured, the Hub SHALL allowlist that
server's tools explicitly, so the agent's general sandbox does not also block AgentWeave's own tooling.

#### Scenario: Hub's own MCP tools remain usable under the sandbox

- **WHEN** the Hub spawns a non-yolo Claude agent with its own MCP server configured
- **THEN** the spawned command line allowlists that server's tools
- **AND** an action outside that allowlist is still refused

#### Scenario: No allowlist is added when there is nothing to allowlist

- **WHEN** the Hub spawns a non-yolo Claude agent with no MCP server configured
- **THEN** the spawned command line does not include an MCP tool allowlist flag

### Requirement: The default posture lets an agent work inside its own workspace

The permission posture the Hub imposes by default SHALL permit an agent to do work within its own
workspace without further configuration.

The Hub MUST NOT impose by default a posture whose decisions can only be resolved by an operator
prompt, unless a surface exists through which an operator can actually answer that prompt. A posture
that defers every decision to an absent answerer denies everything and is indistinguishable from a
broken run.

Isolation SHALL continue to be carried by the agent's workspace boundary, not by withholding
permission inside it.

#### Scenario: A newly created agent can edit files in its own workspace

- **WHEN** the Hub spawns a non-yolo agent that has been given no permission configuration
- **AND** that agent writes a file inside its own workspace
- **THEN** the write succeeds
- **AND** no approval was required from an operator

#### Scenario: A posture requiring an answer is not imposed by default

- **WHEN** no operator-facing approval surface exists for a provider
- **THEN** the Hub does not default that provider's runs to a posture that asks for approval

#### Scenario: The workspace boundary is unchanged

- **WHEN** an agent acts under the default posture
- **THEN** its ability to affect anything outside its own workspace is unchanged by that posture

### Requirement: The operator chooses a conversation's permission posture

The operator SHALL be able to select the permission posture used for a conversation's runs, from the
postures the provider supports, and that selection SHALL take effect on the next run of that
conversation.

The selection MUST reach the spawned command. A control that is displayed but does not change what
the run receives is a defect, not a cosmetic issue.

Postures SHALL be presented in terms of what they allow, not by the provider's internal flag spelling.

#### Scenario: A selected posture reaches the run

- **WHEN** the operator selects a permission posture for a conversation and sends a message
- **THEN** the spawned command carries that posture
- **AND** does not also carry the default posture

#### Scenario: Selecting the most restrictive posture restores refusals

- **WHEN** the operator selects the posture that requires approval for every action
- **AND** the agent attempts a write
- **THEN** the write does not succeed

#### Scenario: A posture is described by what it permits

- **WHEN** the permission postures are presented to the operator
- **THEN** each is labelled by the access it grants rather than by its provider flag value
