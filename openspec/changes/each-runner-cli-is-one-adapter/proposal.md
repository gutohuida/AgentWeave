# Proposal — each runner CLI is one adapter

**Depends on:** the 2026-09-27 night ORDER landing first (`spec-queue/APPROVALS.md` 2026-09-27),
in particular `a-claude-run-is-told-its-agentweave-tools-by-their-full-names`,
`the-permissions-pill-shows-the-posture-the-run-gets`, `a-runner-that-cannot-collaborate-says-so-where-it-is-bound`,
`the-codex-models-offered-are-the-ones-its-cli-lists`, `request-agent-models-the-new-agent-on-one-the-operator-made`,
`an-ask-me-card-says-what-workspace-only-would-decide` and `a-run-records-that-its-calls-were-allowed`. Each of them edits a
site this change moves. R2 rebases every `file:line` below onto the tree they leave.
**R2 (2026-09-28):** of these, only `the-codex-models-offered-are-the-ones-its-cli-lists` has landed (5 of the ORDER's 28
on `ef55e6f`). The other six are unbuilt, so design.md marks each site they will edit *(rebase at IMPL)* with what
their designs say they leave. The line numbers below hold on `ef55e6f`.
**Depended on by:** `a-copilot-agent-runs-over-acp`, `a-run-reaches-the-hub-without-mcp`, `a-copilot-run-shows-its-credits`,
`a-copilot-agent-uses-hooks-and-its-own-agents`. They name members of the `RunnerAdapter` defined here.

Slice 1 of 5 of `openspec/explorations/2026-09-27-copilot-as-a-full-runner.md` (operator decision `ghcp-d5-order`:
parity first, 1 → 2 → 3 → 4 → 5). **R1, 2026-09-27. Nothing here is implemented.**

## Why

Adding a third runner today means finding and editing every place that already knows about the first two.
Appendix B of the exploration counts about 12 modules. Read today, the places are:

| Where | What it decides | Evidence (read 2026-09-27) |
|---|---|---|
| `runner_commands.py` | the argv for a turn: `build_command` dispatches on `runner == "codex"` / `runner in ("claude", "claude_proxy", "native")` | `:164`, `:179`; `SUPPORTED_RUNNERS` `:60`; `_CATALOG_PROVIDER_BY_RUNNER` `:110-119` |
| `api/v1/agent_trigger.py` | which process kind is spawned (PTY or pipe), which parser reads it, the post-run rollout accounting, the 501 gate, and the whole Codex app-server executor | `:2345`, `:2451`, `:2574`, `:773`, `:2926-3040`, `:3040-3460` |
| `codex_appserver.py` | whether Codex uses app-server | `uses_app_server` `:79-89` (its `runner_cli != "codex"` is `:85`) |
| `launchability.py` | which binary is probed, a Claude-only env guard, and whether the Hub's MCP server is injected at all | `RUNNER_CLI` `:33-43`; `:190`; `MCP_INJECTABLE_RUNNERS` `:230`; `resolve_access_path` `:233-249` |
| `workspace_writes.py` | which tool names are file writes | `CLAUDE_WRITE_TOOLS` `:39-44`, `CODEX_WRITE_TOOL` `:49` |
| `worker.py`, `conversation_titles.py` | the one-shot argv and the envelope parser | `worker.py:71`, `:142-153`, `:323-328`, `:450`; `conversation_titles.py:68`, `:86-95` |
| `api/v1/agents.py` | the Codex collaboration verdict, and display names | `:249`, `:557-565` |
| `api/v1/model_catalog.py` | which provider's model source is reported (R2: added on 2026-09-28 by the Codex cache change) | `p.provider == "codex"` `:26` |

Three of these are registries that no longer bind anything. Each already carries a `DEAD (2026-09-20)` block
naming `RUNNER_CLIS` as the only registry that binds (F393): `SUPPORTED_RUNNERS`, `_CATALOG_PROVIDER_BY_RUNNER` and
`MCP_INJECTABLE_RUNNERS`.

`resolve_access_path(runner, override) -> "mcp" | "cli"` (`launchability.py:233`) answers three separate questions with
one value: can the Hub give this agent its tools, can the Hub approve this agent's tool calls, and how does the agent
reach the capability plane. Its docstring admits the coupling: the value *"also decides the run's permission
posture"*. For Claude and Codex the three answers happen to move together. Copilot is the runner where they do not.
Copilot approves over ACP `session/request_permission` whether or not MCP is allowed (exploration, "The 09-20 question,
answered"; appendix A §A–B, VERIFIED-LOCAL). So the one value has to be split before Copilot can be correct.

## What changes

- **One `RunnerAdapter` per runner CLI.** A new package, `hub/hub/runner_adapters/`, holds `ClaudeAdapter`,
  `CodexAdapter` and the table `ADAPTERS`, keyed by runner CLI. Each adapter owns every runner-specific decision
  listed in the table above. The runner-agnostic code (trigger, executors, probe, worker, titler, agents routes)
  looks up the adapter and calls it. After this change no code outside the adapter package compares a runner name to
  a literal.
- **The adapter members the later slices need are defined here**, with their contracts (design D3). The first twelve
  are the ones the brief names: `build_launch`, `map_events`, `inject_mcp`, `instruction_channel`, `decide_posture`,
  `usage_from`, `context_window`, `stop`, `one_shot`, `write_tool_kinds`, `catalog_provider` and `launchability`.
  Members no Claude or Codex code would call are **not** added here. Their contract is written down, and each is
  added by the slice that first reads it (design D16).
- **`resolve_access_path` is split into three independent axes** (design D4): `tool_surface` (does the Hub inject its
  MCP server), `approvals` (which channel, if any, lets the Hub answer this run's tool calls) and `plane` (how the run
  reaches the capability plane). They are resolved per run from the adapter and the operator's `hub_client`. Claude and
  Codex get exactly today's values. For Codex app-server this makes one existing fact visible: its approvals already
  do not depend on MCP.
- **Dead registries are deleted** (design D5): `SUPPORTED_RUNNERS`, `_CATALOG_PROVIDER_BY_RUNNER` with
  `catalog_provider_for_runner`, `MCP_INJECTABLE_RUNNERS`, `worker.SUPPORTED_CLIS`, `conversation_titles._SUPPORTED_CLIS`,
  `codex_appserver.uses_app_server` (its body becomes the Codex adapter's transport choice), and the unreachable
  `claude_proxy`/`native` arms of command building and parser selection. `RUNNER_CLI` becomes
  `LEGACY_RUNNER_CLI`. It is consulted only for a runner string that has no adapter, which only a session-configured
  agent can carry. Its `copilot` row stays until slice 2 gives Copilot an adapter (design D5, reason given there).
- **No behaviour change.** Command lines, parsed event sequences, one-shot argv, launchability verdicts, collaboration
  verdicts, postures and every API response are byte-identical. The proof is golden files captured from today's code
  before any edit (tasks 1.1–1.3), the existing suites, and a Claude drive on the trial Hub.
- **Zero migrations.** `RUNNER_CLIS` and the database's `ck_runners_cli` constraint stay `('claude', 'codex')`. A test
  binds them to `ADAPTERS` and `CATALOG`.

## Out of scope

- Anything Copilot. That is slice 2, `a-copilot-agent-runs-over-acp`, which adds one adapter, one table row and the
  migration widening `ck_runners_cli` (design D2).
- F325: Codex app-server receives no canonical context. The Codex adapter declares its app-server instruction channel
  as `None` (design D11), so the gap becomes a declared value instead of an absent branch. It is not fixed here.
- The Codex MCP env allow-list omitting `AW_QUESTION_TIMEOUT` and three other variables (appendix B §12). It is kept
  as is, declared once instead of twice (design D12).
- `src/agentweave/constants.py` `RUNNER_CONFIGS`, which the CLI's `doctor` reads. F393 annotated it on 2026-09-22.
  The Hub does not import it.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `runner-registry`: ADDED *Each supported runner CLI is served by exactly one runner adapter*.
- `agent-capability-plane`: ADDED *A run's tool surface, approval channel and plane access are decided separately*.

## Impact

Backend only: `hub/hub/runner_adapters/` (new), `runner_commands.py`, `api/v1/agent_trigger.py`, `launchability.py`,
`workspace_writes.py`, `worker.py`, `conversation_titles.py`, `api/v1/agents.py`, `api/v1/runners.py`,
`codex_appserver.py`, `model_catalog.py` and `api/v1/model_catalog.py` (R2: a `catalog_source(provider)` helper replaces the
route's `== "codex"`). Tests that import `build_command` from `runner_commands` or patch
`hub.api.v1.agent_trigger.codex_run_turn` change import path or patch target (design D6, D9). No migration, no API
shape change, no UI change, and so no bundle refresh. `mcp_server.py` is not touched.
