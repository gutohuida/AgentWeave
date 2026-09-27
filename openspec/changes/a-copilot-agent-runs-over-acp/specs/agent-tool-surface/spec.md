## ADDED Requirements

### Requirement: A Copilot run's MCP tool calls outlast the Hub's longest wait

The Hub SHALL configure its MCP server for a Copilot run with a tool-call timeout longer than the longest wait any of its tools can make, and SHALL name the server's tools to a Copilot run by the names Copilot gives them.

Copilot ends an MCP tool call after 30 seconds unless the server's configuration says otherwise. The
Hub's `ask_user` waits for the operator for up to the agent's question timeout, and waiting on the
operator for other decisions can take as long. A Copilot run whose calls were cut at 30 seconds
could never receive an answer the operator took a minute to write.

On Copilot, an MCP tool is called `<server>-<tool>`, so the Hub's `send_message` is
`agentweave-send_message`. The tool list and the turn-start access notice of a Copilot run SHALL use
those names.

#### Scenario: A question longer than 30 seconds reaches the agent

- **WHEN** a Copilot agent calls `agentweave-ask_user` and the operator answers after 90 seconds
- **THEN** the tool call returns the operator's answer rather than a timeout

#### Scenario: The tool list uses Copilot's names

- **WHEN** a Copilot run's context lists the Hub's tools in the MCP form
- **THEN** each tool is named `agentweave-<tool>`
