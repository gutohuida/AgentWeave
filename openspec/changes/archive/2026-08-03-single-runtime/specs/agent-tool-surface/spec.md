## REMOVED Requirements

### Requirement: The access path is chosen per runner from probed capability

**Reason**: Described choosing between a tool-protocol server and a CLI-command adapter per runner.
The command adapter no longer exists — single-runtime removes the CLI collaboration commands it
depended on. `agent-capability-plane`'s "HTTP, MCP, and command access have equal capability"
requirement already establishes HTTP and MCP as the two always-available, equally-capable paths;
there is nothing left to probe or choose between.

**Migration**: None. An agent's access path is no longer an environment-dependent choice — direct
HTTP and MCP are both always available, per `agent-capability-plane`.

### Requirement: The tool surface is available without a tool-protocol server

**Reason**: Asserted that every capability remains reachable via ordinary command invocation when no
tool-protocol server is permitted. That command-based fallback is removed by single-runtime.
Superseded by `agent-capability-plane`'s "HTTP, MCP, and command access have equal capability"
requirement, which already guarantees every capability is reachable through direct HTTP regardless
of whether an MCP server is permitted in the environment.

**Migration**: An environment that prohibits MCP servers uses direct HTTP instead, per
`agent-capability-plane`. No agent-facing capability is lost.
