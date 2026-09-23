# Proposal — a Claude run is told its AgentWeave tools by their full names

**Round 1, 2026-09-24** (bundle B3, decision D10, F139). Finding **F139 (B)**, re-verified on HEAD
`404c7d5`. **Nothing here is implemented yet.**

## Why

Told to *"use the send_message tool"*, a Claude-runner agent called the **host's** `SendMessage`,
loaded the host's roster tool, and reported to the operator that AgentWeave's own roster was
unreachable. The run completed; nothing was sent (F139, `conv-fb23a8232711`). It is intermittent:
the same instruction had succeeded nine minutes earlier.

The canonical context still lists every tool bare and asks the reader to apply the prefix
(`hub/hub/api/v1/agents.py:1533-1537`):

> Names below are as injected; with an MCP surface they are prefixed `mcp__agentweave__`.

followed by lines rendered as `` `send_message(to_agent, …)` `` (`_mcp_lines`, `:1468-1473`). On
Claude Code the callable name is `mcp__agentweave__send_message`. So the shipped requirement
`agent-tool-surface` *"The tools an agent may call are named to it"* — *"by their exact callable
names"* — is not met for the runner family the Hub spawns most.

**What the host's `SendMessage` is today.** Read from the operator's own transcripts (`:8000`,
`mode=ro`, 2026-09-13): Claude Code's subagent result ends *"use SendMessage with to: '<agentId>' … to
continue this agent"*. It continues a subagent the run itself spawned. It cannot reach an AgentWeave
agent, and it is a legitimate tool for a run to have — which rules out disabling it.

## What Changes

- For a run on a Claude-family runner (`claude`, `claude_proxy`, `native` — the runners
  `runner_commands.build_command` builds with `_build_claude_command`, `:179`) whose access path is
  MCP, the "Your tools" list names each tool by its **full callable name**
  (`mcp__agentweave__send_message(…)`), and the "names below are as injected" preamble is replaced by
  one sentence: *"These are AgentWeave's tools. Your host also has tools with similar names —
  `SendMessage` continues a subagent you started — which cannot reach AgentWeave agents or the
  operator."*
- Other runners keep today's rendering (their MCP naming is not the same, and Codex is not driveable
  here to measure it).
- The runner is passed into `_render_hub_agent_context` from `trigger_agent_directly`, which already
  holds it (`agent_trigger.py:1057`).

## Capabilities

### Modified Capabilities

- `agent-tool-surface` — the exact-name requirement gains a scenario for a host tool of a similar name.

## Impact

Backend text only (`agents.py`, `agent_trigger.py`); the agent-facing text tests
(`hub/tests/test_agent_facing_text.py`, `test_tool_surface_matches_server.py`) are updated. No
migration, no UI. `GET /agents/agent-context` (no run, no runner) keeps the unprefixed rendering.
