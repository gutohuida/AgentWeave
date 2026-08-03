## Why

AgentWeave currently ships three deployment models at once — local CLI collaboration
(`src/agentweave/watchdog.py` plus `transport/local.py` and `transport/git.py`), an HTTP-connected
Hub, and (until `agent-capability-plane`) a CLI-command fallback for agent actions. Per the product
direction recorded in `openspec/explorations/2026-08-02-product-direction.md`, this is the diagnosed
cause of AgentWeave being hard to use: "the simplest path — one developer, one machine, a few
agents — carried the ceremony of all three." The decision is to become a single locally-installed
app (the T3 Code model) and delete the other two paths rather than maintain them.

This is buildable now, not aspirational: `agent-capability-plane` (archived
`openspec/changes/archive/2026-08-03-agent-capability-plane/`) already delivered the run-bound,
least-privilege HTTP+MCP application API that the exploration doc named as the prerequisite —
"the single-runtime change must not delete the CLI command fallback until direct HTTP parity and
run-bound attribution exist." It exists now. Separately, `agentweave hub start --app` already
proves the Hub-native direct-execution path end to end with the watchdog not running (umbrella
task 3.18: real Claude spawned directly, streamed output, no watchdog started or consulted) — this
change turns that proof into the *only* path, rather than one path coexisting with the watchdog.

## What Changes

- **BREAKING**: Delete `src/agentweave/watchdog.py` (currently ~5,600 lines: message polling,
  auto-ping, stream-event parsing for claude/codex/kimi, heartbeats, PID-file lifecycle).
- **BREAKING**: Delete `src/agentweave/transport/local.py` and `src/agentweave/transport/git.py`,
  and the `transport/config.py` branches that select them. HTTP (to a locally-owned Hub) becomes
  the only transport; there is no `transport.json` "local" default anymore.
- **BREAKING**: Reduce `src/agentweave/cli.py` from 56 `cmd_*` functions to 5, per the survivor
  table already agreed in the exploration doc: bare `agentweave` (launch the app on the current
  directory, replacing `init`/`activate`/`quick`/`start`), `doctor`, `status`, `stop`, `reset`
  (successor to `hub-destroy`). Every command that manipulates collaboration state (messaging,
  tasks, questions, agent roster, jobs, roles, transport setup, relay/delegate/switch/run,
  checkpoint/summary/log, `mcp-setup`, `spec-push`, `sync-context`) is removed — the app UI and the
  agent capability plane (HTTP/MCP) are its only replacements. `--version`/`--help` are unaffected.
  `sync-context` specifically generated `.agentweave/context/<agent>.md` for CLI-launched agents;
  Hub-triggered runs already inject turn-start state directly (`agent-tool-surface`'s "The Hub
  supplies state; the tool surface carries intent"), so the generated-file step has no reader left.
- **BREAKING**: Drop the OpenCode, Kimi, and GitHub Copilot runners. They were never ported to the
  Hub-native direct-execution path (`hub/hub/runner_commands.py` / `runner_parsing.py` cover only
  `claude`, `claude_proxy`, `native`, `codex` — umbrella task 3.5 explicitly deferred the rest: "kimi
  /opencode/copilot explicitly deferred... ignore the others for now"). Porting all three is a
  separate, larger effort than this slice and is out of scope; they can return later if there's
  demand. The `opencode-runner` capability (`openspec/specs/opencode-runner/spec.md`) is retired,
  and every OpenCode/Kimi/Copilot-specific requirement in `agent-stream-events` and
  `agent-context-usage` (event normalization and context-usage mapping for those three runners) is
  removed alongside them, not just their watchdog-specific wording.
- **BREAKING**: Retire the Zero-relay MCP mode and manual message relay (`cmd_relay`,
  `cmd_delegate`) — both were local/git-transport-only collaboration mechanisms with no meaning once
  HTTP/the Hub is the only transport.
- Roles CLI (`cmd_roles_*`) is removed as part of this change (it manipulates collaboration/agent
  configuration state, which is the app UI's job now), independent of and ahead of the separate
  runner/agent/charter successor that will eventually replace the underlying multi-role *concept*.
- `openspec/specs/agent-tool-surface/spec.md`'s two-path model ("a tool-protocol server or
  commands... established by the Hub... An operator MAY override the chosen path") no longer
  applies: the CLI-command adapter it describes is gone, and `agent-capability-plane` already
  established HTTP/MCP as the two equally-capable paths. This requirement is superseded by
  `agent-capability-plane`'s existing "HTTP, MCP, and command access have equal capability"
  requirement, adjusted to drop "command access" (there is no longer a third adapter).
- Diagnostics, telemetry, and instruction-loading requirements that assume the watchdog or
  local/git transport as one of several live configurations are narrowed to the single Hub-owned
  runtime (see Modified Capabilities).

## Capabilities

### New Capabilities

- `app-lifecycle`: the 5 surviving CLI commands and what each does — bare launch (register + start
  the app on the current directory), `doctor` (environment readiness), `status` (is it running, on
  what port, against which project), `stop`, `reset` (destroy local state, the wedged-state escape
  hatch).

### Modified Capabilities

- `agent-tool-surface`: remove the per-runner tool-protocol-server-vs-commands access-path
  requirements (`### Requirement: The access path is chosen per runner from probed capability`,
  `### Requirement: The tool surface is available without a tool-protocol server`) — there is no
  command-based adapter left to choose between; HTTP and MCP are both always available, per
  `agent-capability-plane`.
- `runtime-diagnostics`: remove watchdog-heartbeat-based readiness checks and transport-choice
  reporting (`agentweave doctor` currently reports "transport" and "watchdog heartbeat" among its
  checks; both narrow to a single Hub-process-liveness check), and reword "the watchdog" as the
  preflight actor to name the Hub's own `probe_agent`/`agent_trigger.py` preflight
  (`hub/hub/launchability.py`), which already performs equivalent checks for the runners that
  survive. This spec's remaining references to `agentweave activate`/`switch` as command names are
  pre-existing and not fully reconciled by this bullet — those commands are removed by this same
  change, but rewriting every scenario that names them is left to this capability's own
  implementation phase, per "specs follow implementation."
- `project-instructions`: remove the local-transport instructions-file read path (`### Requirement:
  Local transport reads instructions file`) — only the Hub DB / HTTP path remains.
- `agent-context-usage`: remove watchdog-specific telemetry/session-binding requirements (OTel
  exporter setup on watchdog launch, watchdog-restart session reconstruction) — session binding
  becomes purely the Hub-owned run's concern, already the case for claude/codex today. Also remove
  the OpenCode, Copilot, and Kimi context-mapping requirements entirely (not just their watchdog
  wording), since those runners are dropped.
- `agent-context-onboarding`: reword the watchdog-trigger scenario to a Hub-trigger scenario (the
  underlying behavior — prompt-level shared context injection — is unaffected). This capability's
  broader CLI-era model (`.agentweave/context/<agent>.md` generated by the now-removed
  `sync-context`/`activate`) is not fully reconciled by this change beyond that one scenario — it is
  already superseded in practice by `agent-tool-surface`'s turn-start injection for Hub-triggered
  runs, and a fuller rewrite of this capability is left to whichever change next touches it, per
  "specs follow implementation."
- `agent-stream-events`: reword requirements naming "the watchdog" as the actor to name the Hub's
  direct-execution path (`hub/hub/api/v1/agent_trigger.py`) instead, since that is now the only
  place stream events originate. Also narrow "Supported runner normalization" and the conformance
  fixture list from five runners to `claude` and `codex` only, matching the runner drop above.
- `spec-manifest-sync`: this capability describes the `aw-spec-workflow` feature AgentWeave ships to
  its own users (see CLAUDE.md) — local `spec/*.html` files synced to the Hub over HTTP by either
  the watchdog's poll loop or manual `spec-push`. Both actors are removed elsewhere in this change,
  so the two requirements that describe the sync/reconciliation mechanism itself are removed; the
  manifest-format and discovery requirements (which describe `spec/index.json`'s shape, independent
  of what triggers a sync) are kept, reworded to drop watchdog references. **This is an accepted
  regression, not a redesign**: syncing local specs to the Hub has no replacement in this change.
  The exploration doc already flags local-only as simplifying spec-file authority and names the
  specification program as the slice that reworks this properly (a locally-running Hub can read
  `spec/` directly from its own working directory instead of needing anything synced to it at all)
  — this change does not attempt that redesign, only removes the mechanism whose actors it deletes.
- `trace-timeline`: reword the "Hub or watchdog" trigger scenario to name the Hub alone.
- `opencode-runner`: retired. All requirements removed; the capability's shipped behavior no longer
  exists in the product.

## Impact

- **Code removed**: `src/agentweave/watchdog.py`, `src/agentweave/transport/local.py`,
  `src/agentweave/transport/git.py`, ~51 of 56 `cmd_*` functions and their argparse subparsers in
  `src/agentweave/cli.py`, `.agentweave/agents/*-session.json` / `.agentweave/watchdog.pid` file
  formats, OpenCode/Kimi/Copilot runner configs in `constants.py`.
- **Code kept/repurposed**: `hub/hub/api/v1/agent_trigger.py`, `runner_commands.py`,
  `runner_parsing.py` (already the sole execution path for surviving runners); `agent-capability-plane`
  HTTP/MCP surface (unaffected, already the agent-facing contract); `cmd_doctor`, `cmd_status`,
  `cmd_stop`, `cmd_hub_start`/`cmd_hub_destroy` (renamed/consolidated into bare launch and `reset`).
- **Tests**: every CLI test exercising a removed command or the watchdog/local/git transports is
  deleted, not adapted — there is no reduced-functionality fallback to preserve. Expect a large test
  count drop in `tests/` (parallels task 3.5's precedent: -14 tests for one much smaller removal).
- **Docs**: `README.md`'s quick start already points at `agentweave hub start --app` (task 3.17);
  this change updates it to the bare `agentweave` entry point and removes the now-false claim that
  local/git transports or the watchdog remain supported.
- **No migration path**: per product direction, there is no external install base to protect. Users
  on local/git transport or OpenCode/Kimi/Copilot lose that capability with no compatibility shim.
