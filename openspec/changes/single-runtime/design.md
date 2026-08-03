## Context

Two things already exist that this change is stitching together, not inventing:

1. **The Hub-native direct-execution path is proven with no watchdog involved.** `_hub_native_start`
   (`src/agentweave/cli.py:3132`) already runs migrations, scaffolds a local API key, and launches
   `uvicorn hub.main:app` as a plain subprocess (no Docker). `hub/hub/api/v1/agent_trigger.py`
   already spawns `claude`/`claude_proxy`/`native`/`codex` directly and streams their output over
   SSE, using `hub/hub/runner_commands.py` and `runner_parsing.py` — reimplementations of the
   watchdog's command-building and line-parsing that owe it nothing at runtime. Umbrella task 3.18
   verified this end to end with the watchdog neither started nor consulted.
2. **The agent capability plane closes the one gap that blocked deleting the CLI fallback.**
   `agent-capability-plane` (archived, `openspec/changes/archive/2026-08-03-agent-capability-plane/`)
   gives a spawned run a short-lived, run-bound `AW_RUN_TOKEN` and a least-privilege HTTP+MCP API
   (`/api/v1/agent-actions`), independently verified live against a real Hub process with no project
   credential in the spawned environment. Before this existed, an agent's only way to message a peer
   or touch the task ledger without a full project key was the CLI commands this change removes.

What's left is deletion and consolidation: remove the watchdog and the two transports that only the
watchdog (or CLI-collaboration commands) used, collapse the CLI's entry points onto the native
Hub-start path, and reconcile every spec that still describes the watchdog or local/git transport as
live behavior.

## Goals / Non-Goals

**Goals:**

- Bare `agentweave`, run from a project directory, is the only supported way to start AgentWeave:
  it registers the directory if needed and launches the native Hub-owned runtime in app mode.
- No code path in the shipped product starts `watchdog.py`, reads `transport.json`, or writes
  `.agentweave/watchdog.pid` / `.agentweave/agents/*-session.json`.
- Every capability an agent needs (messaging, tasks, questions, agent requests, jobs) remains
  reachable, but only through the app UI (operator) or the agent capability plane (agent) — never
  through a CLI command that manipulates collaboration state directly.
- `doctor`, `status`, `stop`, `reset` describe *app* lifecycle (is the single owned process up, on
  what port) rather than *collaboration-session* lifecycle (is my watchdog polling).
- Every existing openspec capability spec is either unaffected, or updated to state the
  single-runtime behavior — none is left describing a watchdog or transport choice that no longer
  exists.

**Non-Goals:**

- Porting OpenCode, Kimi, or GitHub Copilot to the Hub-native execution path. Explicit product
  decision (this change's proposal): drop them now, revisit later if there's demand.
- Renaming "Hub" to anything else. Deferred per the exploration doc, to avoid doubling churn before
  this change's structure settles.
- Any remote/multi-tenant capability. This change makes the single-operator assumption more explicit
  (deleting `transport/git.py`, which was the only cross-machine path), it does not add multi-user
  scope.
- Reworking the runner/agent/charter model. Roles CLI commands are removed here because they
  manipulate collaboration state (the thing this change removes CLI access to generally), not
  because this change redesigns roles — that's the separate runner/agent/charter successor.
- Docker deployment is unaffected by this change's *runtime* argument (native vs. watchdog); the
  existing `--docker`/`--local` branches of Hub start remain, since Docker is a packaging choice
  for the same single Hub process, not a second collaboration substrate.

## Decisions

### 1. Deletion order: transports and watchdog first, then CLI surface, then specs

Deleting `transport/local.py` and `transport/git.py` first makes every CLI command that depends on
them (message/task/question/relay/delegate/switch/run — anything that calls `get_transport()` and
expects a non-HTTP branch) fail fast in tests, which is the fastest way to find every command that
needs deleting rather than adapting. Concretely:

1. Delete `transport/local.py`, `transport/git.py`; collapse `transport/config.py::get_transport()`
   to the two branches that remain (`AW_RUN_TOKEN` bound path from `agent-capability-plane`, and a
   plain project-key `HttpTransport` for the app UI / the 5 surviving commands that still need one,
   e.g. `doctor` checking Hub connectivity).
2. Delete `watchdog.py` and every CLI command whose only job was to start it, poll it, or read its
   PID/heartbeat file (`cmd_start`, `cmd_stop`'s watchdog branch, `cmd_status`'s watchdog section,
   `_kill_stale_watchdogs`, `_is_watchdog_process`, etc.).
3. Delete the remaining ~45 `cmd_*` functions per the proposal's survivor table, and their argparse
   subparsers in `create_parser()`.
4. Consolidate `cmd_init`/`cmd_activate`/`cmd_quick`/`cmd_hub_start` into the bare-invocation entry
   point (see Decision 2). Rename `cmd_hub_destroy` to the `reset` command name (behavior is already
   correct — see Context; only the name and default confirmation UX may need adjusting for a
   general-purpose "wedged" escape hatch rather than a Hub-specific one).
5. Sync every affected delta spec (`agent-tool-surface`, `runtime-diagnostics`,
   `project-instructions`, `agent-context-usage`, `agent-context-onboarding`, `agent-stream-events`,
   `spec-manifest-sync`, `trace-timeline`) and retire `opencode-runner`, only after the code changes
   they describe are real — per this repo's standing rule, specs follow implementation, never the
   reverse.

### 2. Bare `agentweave` is `_hub_native_start` plus auto-registration, not new orchestration

`_hub_native_start(port, detach=True, app=True)` already does everything the exploration doc asks of
the bare command except decide *which* directory to register as a project. The new top-level
handler:

- If the current directory has no registered project (checked against the Hub's own project table,
  not a local `agentweave.yml` — there is no more local-only project state), create one scoped to
  `Path.cwd()`, the same way the app's own "add project" UI flow will.
- Then call `_hub_native_start` with `app=True` unconditionally (an operator running the bare command
  wants the window; `--no-detach`/headless remains an explicit flag for scripting/CI, not the
  default).

Rejected alternative: keep `init`/`activate`/`quick` as separate subcommands that call into shared
logic. Rejected because the exploration doc's whole point is removing ceremony — three names for one
action is the ceremony being removed, and `_hub_native_start` already does the idempotent
"already running → just open the window" check that makes repeated bare invocations safe.

### 3. `opencode-runner` capability: retire by removing every requirement, not deleting the file silently

OpenSpec's delta vocabulary (`ADDED`/`MODIFIED`/`REMOVED`/`RENAMED` requirements) has no first-class
"remove capability" verb. This change's delta spec for `opencode-runner` lists every existing
requirement under `## REMOVED Requirements`, which the sync step turns into deleting
`openspec/specs/opencode-runner/spec.md` entirely (an empty capability spec is not meaningful to
keep around). This keeps the retirement auditable in the change's own delta rather than a silent
`rm` with no spec trail.

### 4. Test migration: delete, don't adapt

Every test in `tests/test_watchdog*.py`, `tests/test_transport_local.py`,
`tests/test_transport_git.py`, `tests/test_opencode_cli_override.py`, and the CLI test coverage for
every removed `cmd_*` is deleted outright. This mirrors the precedent already set inside the umbrella
(task 3.16: "-14, all accounted for" when a much smaller watchdog branch was removed) rather than
retrofitting them to assert the new behavior — there is no reduced-functionality mode to keep
covered.

## Risks / Trade-offs

- **[Risk] Large, mechanical deletion (~5,600-line watchdog, 2 transport modules, ~45 CLI commands)
  is easy to under-verify by skimming rather than exercising.** → Mitigation: same live-verification
  standard as `agent-capability-plane` phase 4 — a real bare-`agentweave` invocation against a real
  (throwaway) project directory, confirming an agent run starts, streams output, and can message/task
  through the capability plane, with no `watchdog.pid` file ever created and no `transport.json`
  ever read.
- **[Risk] Deleting OpenCode/Kimi/Copilot support is user-visible capability loss, not just internal
  cleanup.** → Mitigation: called out as **BREAKING** in the proposal and confirmed as an explicit
  product decision (not inferred) before writing this design; `opencode-runner`'s retirement is
  auditable via its delta spec rather than a silent deletion.
- **[Risk] `transport/config.py::get_transport()` is used by more than the CLI** — the MCP compat
  shim (`src/agentweave/mcp/server.py`) and any remaining test helper import it too. → Mitigation:
  grep every caller of `get_transport` before deleting the local/git branches (Decision 1, step 1),
  not just the CLI's own call sites.
- **[Trade-off] No migration/compatibility shim for existing local/git-transport or watchdog users.**
  Accepted per product direction — there is no external install base to protect, and a shim would
  reintroduce the exact "carries the ceremony of all three" problem this change exists to remove.

## Migration Plan

Implementation proceeds in the deletion order from Decision 1, each phase gated on its own tests
before the next starts (mirrors `agent-capability-plane`'s phase discipline):

1. Transport layer: delete `local.py`/`git.py`, collapse `get_transport()`, update every caller.
2. Watchdog and its CLI launch/status/stop surface.
3. Remaining collaboration `cmd_*` functions and subparsers; consolidate the entry point.
4. `reset` naming/UX pass over `cmd_hub_destroy`.
5. Spec sync for the eight modified capabilities plus `opencode-runner` retirement.
6. Full regression (CLI, Hub, frontend) + a real live bare-launch verification, matching the rigor
   of `agent-capability-plane` phase 4.
7. README and docs pass (quick start already points at `agentweave hub start --app`; finish the
   rename to bare `agentweave` and remove now-false watchdog/transport claims).

No rollback strategy beyond normal git revert — this is a local dev tool with no deployed state to
roll back in place, and the umbrella's own precedent (task 3.10 onward) has not needed one.

## Open Questions

- Exact flag/UX for `reset` vs. the current `hub-destroy --all` two-tier (data-only vs.
  data+config) — carry the existing two-tier behavior forward under the new name unless review
  surfaces a reason to collapse it.
- Whether `doctor` needs a new "no project registered in this directory" check now that `init` no
  longer exists as a separate ceremony, or whether bare `agentweave`'s own auto-registration makes
  that state unreachable in practice. Resolve during implementation once the bare-launch path is
  written, rather than guessing now.
