## REMOVED Requirements

### Requirement: OpenCode runner type is registered in constants

**Reason**: Single-runtime (`openspec/changes/single-runtime`) drops the OpenCode runner. It was
never ported off the watchdog's execution path onto the Hub-native direct-execution path, and
porting it is out of this change's scope.

**Migration**: None. OpenCode support may return later as its own change if there is demand, at
which point it would target the Hub-native path (`hub/hub/runner_commands.py` /
`runner_parsing.py`) rather than the deleted watchdog.

### Requirement: Watchdog dispatches tasks to OpenCode agents

**Reason**: The watchdog itself is deleted by single-runtime, and the OpenCode runner is dropped
alongside it — see above.

**Migration**: None.

### Requirement: Stable session IDs are used for OpenCode agents

**Reason**: This requirement exists to give OpenCode session continuity across watchdog pings. Both
the watchdog and the OpenCode runner are removed.

**Migration**: None.

### Requirement: MCP server is registered in opencode.json for OpenCode agents

**Reason**: `agentweave mcp-setup` is removed by single-runtime (tool configuration becomes
automatic per `agent-tool-surface`), and the OpenCode runner it configured is dropped.

**Migration**: None.

### Requirement: opencode is listed in KNOWN_AGENTS

**Reason**: The OpenCode runner is dropped; there is nothing to list.

**Migration**: None.
