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
the path it renders (`described_path`, R3) is `"mcp"`. `CLAUDE_FAMILY_RUNNERS` is declared once, in `runner_commands.py`, and the
`build_command` branch at `:179` reads it, so the two cannot drift. The HTTP rendering is unchanged.

**Bare mentions outside the list (counted by R2).** A single-line-string grep for the 27 served tool
names, outside `_operations()` and `mcp_server.py`, finds **at least 35** mentions in text that reaches
a turn: ~19 in `agents.py`'s context builders (review verdict `:1749`, spec-document duties
`:1848-1958`, evidence grants `:2011-2032`, checkpoint and recall grants `:2062-2078`, checkpoint
notes `:2991`, `:3027`), 8 in `launchability.py` (phase duties `:353-377`, evidence `:445`, and the
**access-path notice** `:390-393`), 3 in `review_turn.py:230-236`, 2 in `scheduler.py` briefings
(`:2542`, `:2569`) and 1 in `checkpoint_generation.py:365` — a lower bound, since multi-line strings
split across literals are missed. Several are produced where no runner is known (scheduler briefings,
review prompts), so threading a prefix through all of them is a wide change for little gain.

**Recommendation: the list plus the one notice that names `send_message`, not the rest.**

- The **access-path notice** (`launchability.access_path_notice`, `:389-393`) is rendered for every MCP
  run (`agent_trigger.py:1123`) and says *"call send_message / create_task / update_task / ask_user
  directly"* — it names the colliding tool bare, in the one sentence whose purpose is to say how to
  call the tools. It is qualified too: it takes the same `tool_prefix` and, for a Claude-family run,
  names `mcp__agentweave__send_message` etc. Its caller already holds `runner`.
- The prefixed list's preamble gains one clause: *"Elsewhere in these instructions a tool may be named
  by its short name (`ask_user`); call it by the full name listed here."* That makes every other
  mention a reference into the list, which is where an agent looks a tool up, and the collision is
  only with `send_message`, which is covered twice.

**R3 — the prefix is keyed on the *described* path, and a first run is described as HTTP.**
`_render_hub_agent_context` and `access_path_notice` both receive `described_path`, not
`access_path` (`agent_trigger.py:1057-1062`, `:1080`, `:1123`). `described_access_path` answers `mcp`
only where the operator set `hub_client: "mcp"` or a previous run of this agent reported its adapter
online (`launchability.py:281-311`), so a fresh agent's first run is described in the HTTP form while
the server is injected. The prefix applies where the list is rendered in its MCP form
(`described_path == "mcp"`) on a Claude-family runner, the only rendering that names MCP tools at
all; the first-run case names no MCP tool, bare or prefixed, and is outside this change. Task 1.4's
trigger test must establish the grounds (`hub_client: "mcp"` in the agent's config, or a prior `Run`
with `mcp_adapter_online_at` set), or it fails for a reason unrelated to the fix.

## D3 — What the route returns when what it calls raises

No route changes. `GET /agents/agent-context` passes no runner and renders as today.

## Round log

- R1 (2026-09-24): written. Not yet compared by R2/R3.
- R2 (2026-09-24): claims re-read (`agents.py:1533-1537` preamble, `_mcp_lines` `:1468-1473`, `build_command` `runner_commands.py:179`, server key `agentweave` `:252-253`, `access_path` resolved at `agent_trigger.py:1057`). Counted the bare mentions outside the list (≥35 in 7 modules) and found the access-path notice names `send_message` bare on every MCP run; added it to scope, plus one preamble clause for the rest.
- R3 (2026-09-24): the context and the notice are rendered from `described_path`, which a fresh agent's first run has as HTTP; the prefix is keyed on it and task 1.4 now seeds the grounds. Other claims re-read and hold.
