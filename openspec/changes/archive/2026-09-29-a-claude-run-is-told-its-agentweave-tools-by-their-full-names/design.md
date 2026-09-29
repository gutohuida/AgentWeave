# Design — a Claude run is told its AgentWeave tools by their full names

## Operator review, 2026-09-24

The Opus adversarial review (`spec-queue/tracks/reviews/B3-2026-09-24.md` §6) verdict was
**APPROVE WITH FIXES**; the operator approved with the fixes applied. The server key is verified
(`mcpServers.agentweave`, `runner_commands.py:252-256`; `--allowedTools mcp__agentweave__*`,
`:262`). Fixes, re-verified on HEAD `a50a49b`:

- **MEDIUM — a spec scenario claimed more than the change does.** *"A run whose harness prefixes
  injected tools → each AgentWeave tool is named with that prefix"* was unscoped, but a first run has
  `access_path == "mcp"` and `described_path == "cli"` (`launchability.described_access_path`,
  `:281-311`), and its HTTP rendering labels each operation with its bare tool name
  (`_http_lines`, `agents.py:1484`). The review offered two fixes; **both are taken**, because each
  covers a different half (D2, *The first run*): the prefix scenario is scoped to *a run described
  as having the injected surface*, and the sentence naming the host's `SendMessage` is rendered for
  **every Claude-family run, in either form**. That sentence is a fact about the harness, not about
  the injected surface, so it asserts nothing the Hub has no grounds for — and the first run is the
  one F139's collision can hit with no full name to steer it.
- **LOW — the unknown-harness wording disagreed with control 1.2.** The scenario said the harness
  *may* prefix; today's preamble (`agents.py:1536-1537`) says *"with an MCP surface they are
  prefixed `mcp__agentweave__`"*, which is unmeasured for Codex (design D1 option 3). Aligned on
  **"may"**: the non-Claude MCP preamble becomes *"Names below are as declared; your harness may show
  them with a prefix such as `mcp__agentweave__`."* Task 1.2 now asserts that wording (so it fails
  today) plus bare names (control).

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
`build_command` branch at `:179` reads it, so the two cannot drift. The HTTP rendering's names are unchanged; it gains only the host-`SendMessage` sentence on a Claude-family run (operator review, *The first run* below).

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
all; the first-run case names no MCP tool, bare or prefixed, and gets no prefix (but see *The first run*, below). Task 1.4's
trigger test must establish the grounds (`hub_client: "mcp"` in the agent's config, or a prior `Run`
with `mcp_adapter_online_at` set), or it fails for a reason unrelated to the fix.

**The first run (operator review).** "Names no MCP tool" was true of the list but not of the risk:
the HTTP rendering labels each operation `` (`send_message`) `` (`_http_lines`, `agents.py:1484`), the
server *is* injected, and the host's `SendMessage` is in the model's tool list — the F139 collision is
available on exactly this run. So the disambiguating sentence is keyed on the **runner family alone**
(`runner in CLAUDE_FAMILY_RUNNERS`), and rendered after the preamble in both forms; only the prefix
is keyed on `described_path == "mcp"`. A Claude run given no server (`hub_client: "cli"`) still has
the host tool, so it gets the sentence too; that is correct, not a leak of surface. The prefix is not
extended to the first run's HTTP labels: those name an operation, not a tool to call, and asserting
the injected name there is what `described_access_path` exists to refuse.

**Non-Claude preamble (operator review).** For a run in the MCP form on a runner outside
`CLAUDE_FAMILY_RUNNERS`, the preamble says the harness *may* prefix the names
(*"Names below are as declared; your harness may show them with a prefix such as
`mcp__agentweave__`."*) instead of asserting that it does: Codex's naming is not measured here.

## D3 — What the route returns when what it calls raises

No route changes. `GET /agents/agent-context` passes no runner and renders as today.

## Round log

- R1 (2026-09-24): written. Not yet compared by R2/R3.
- R2 (2026-09-24): claims re-read (`agents.py:1533-1537` preamble, `_mcp_lines` `:1468-1473`, `build_command` `runner_commands.py:179`, server key `agentweave` `:252-253`, `access_path` resolved at `agent_trigger.py:1057`). Counted the bare mentions outside the list (≥35 in 7 modules) and found the access-path notice names `send_message` bare on every MCP run; added it to scope, plus one preamble clause for the rest.
- R3 (2026-09-24): the context and the notice are rendered from `described_path`, which a fresh agent's first run has as HTTP; the prefix is keyed on it and task 1.4 now seeds the grounds. Other claims re-read and hold.
- Operator review (2026-09-24): prefix scenario scoped to a run described as having the injected surface; the host-`SendMessage` sentence rendered for every Claude-family run in either form; non-Claude preamble says "may". Tasks 1.1a, 1.2, 1.4, 2.2 and the spec follow. Line numbers on HEAD `a50a49b`: `_render_hub_agent_context` is at `agents.py:1601` (not `:1616`), the preamble strings at `:1536-1537`.
