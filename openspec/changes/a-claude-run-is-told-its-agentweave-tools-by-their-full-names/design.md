# Design — a Claude run is told its AgentWeave tools by their full names

**Built on the recommended answer to D10/F139**: *name the tools as the harness names them, for the
runner family where the name is known; do not disable the host's tools.* **If the operator answers
otherwise** — e.g. "disable `SendMessage` on Hub-spawned Claude runs" — the change becomes a
`--disallowedTools` addition in `runner_commands._build_claude_command` (merged with the
`restrict_spec_writes` list at `:229`, since two `--disallowedTools` flags are not known to combine),
and loses subagent continuation for every Hub run.

## Context — re-verified on HEAD `404c7d5`

- Preamble and rendering: `agents.py:1533-1554`, `_mcp_lines` `:1468-1473`. No `runner` parameter
  reaches `_tool_surface_lines` (`:1500`) or `_render_hub_agent_context` (`:1616`).
- The runner at render time: `trigger_agent_directly` holds `runner = probe["runner"]`
  (`agent_trigger.py:~728`) and resolves `access_path`/`described_path` from it (`:1056-1062`)
  before calling `_render_hub_agent_context` (`:1073-1081`).
- Claude-family runners: `build_command` routes `("claude", "claude_proxy", "native")` to
  `_build_claude_command` (`runner_commands.py:179`), which injects the server as `agentweave`
  (`:247-256`) — hence `mcp__agentweave__<tool>`.
- `git log -S "Names below are as injected"`: the preamble is unchanged since it was written; F139's
  filing (2026-08-30) did not touch it.

## D1 — Options

1. **Full names for Claude-family runs, plus one disambiguating sentence** (recommended). Meets the
   shipped exact-name requirement where the exact name is known, and names the collision once, with
   what the host tool is actually for.
2. **Disable the host's `SendMessage`** (`--disallowedTools`). Removes the wrong referent entirely,
   but `SendMessage` is how a run continues a subagent it spawned (measured in real transcripts), so
   this trades a sometimes-wrong call for a never-available capability. Also relies on host tool names
   staying fixed across Claude Code releases.
3. **Full names for every runner.** Codex's MCP naming is not the same and cannot be measured here
   (Codex is undrivable on this machine); guessing would reintroduce the problem there.

## D2 — Where the name is decided

`_tool_surface_lines(..., tool_prefix: str = "")`; `_mcp_lines` renders
`f"{tool_prefix}{operation.tool}({operation.args})"`. `_render_hub_agent_context` takes an optional
`runner` and passes `tool_prefix="mcp__agentweave__"` when `runner in CLAUDE_FAMILY_RUNNERS` and
`access_path == "mcp"`. `CLAUDE_FAMILY_RUNNERS` is declared once, in `runner_commands.py`, and the
`build_command` branch at `:179` reads it, so the two cannot drift. The HTTP rendering is unchanged.

Other bare mentions elsewhere in the context (e.g. `ask_user` inside `SPEC_PHASE_DUTIES`,
`agents.py:1560-1575`) are **not** rewritten in this change; R2 should count them and say whether the
list alone is enough, given the list is where the agent looks a tool up.

## D3 — What the route returns when what it calls raises

No route changes. `GET /agents/agent-context` passes no runner and renders as today.

## Round log

- R1 (2026-09-24): written. Not yet compared by R2/R3.
