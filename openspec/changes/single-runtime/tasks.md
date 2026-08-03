# Implementation plan

## Working protocol

1. Re-read proposal, design, and the delta specs touched by a phase before starting it.
2. Tests precede implementation within each phase — write the test for the behaviour first.
3. Commit and hand off every verified phase.
4. Never mark work complete from a plan alone — only real, verified implementation closes a task.
5. Grep every caller before deleting a module (`get_transport`, `watchdog.*`, `cmd_*`), not just the
   obvious ones — `design.md`'s risk section flags `transport/config.py::get_transport()` as used
   beyond the CLI's own command bodies (the MCP compatibility shim, test helpers).

## 0. Transport layer

- [ ] 0.1 Grep every caller of `get_transport()`, `LocalTransport`, and `GitTransport` across
      `src/agentweave/` (not just `cli.py`) to enumerate what breaks when local/git are deleted.
- [ ] 0.2 Add/adjust tests asserting `get_transport()` has exactly two branches left: the
      `AW_RUN_TOKEN`-bound keyless `HttpTransport` (from `agent-capability-plane`) and a project-key
      `HttpTransport` for the app UI / surviving CLI commands.
- [ ] 0.3 Delete `src/agentweave/transport/local.py` and `src/agentweave/transport/git.py`; collapse
      `transport/config.py::get_transport()` and update every caller found in 0.1.
- [ ] 0.4 Verify: full CLI regression passes with no reference to local/git transport remaining;
      hand off and commit.

## 1. Watchdog removal

- [ ] 1.1 Add/adjust tests proving no code path starts `watchdog.py`, writes
      `.agentweave/watchdog.pid`, or writes `.agentweave/agents/*-session.json`.
- [ ] 1.2 Delete `src/agentweave/watchdog.py` and the CLI helpers whose only purpose was launching,
      polling, or reading its state (`cmd_start`'s watchdog launch, `_kill_stale_watchdogs`,
      `_is_watchdog_process`, `_terminate_watchdog`, the watchdog sections of `cmd_stop`/`cmd_status`).
- [ ] 1.3 Delete `tests/test_watchdog*.py`, `tests/test_opencode_cli_override.py`, and any other test
      file whose only subject is the watchdog or a dropped runner (OpenCode/Kimi/Copilot).
- [ ] 1.4 Verify: full CLI regression passes; grep confirms `watchdog` has no remaining import
      outside historical openspec/changelog text; hand off and commit.

## 2. CLI surface reduction

- [ ] 2.1 Add tests for the app-lifecycle capability's five surviving commands per
      `specs/app-lifecycle/spec.md`'s scenarios (bare invocation registers + launches, idempotent
      repeat invocation, `doctor` runs without a registered project, `status`/`stop` reflect a real
      running/stopped instance, `reset` destroys local state).
- [ ] 2.2 Consolidate `cmd_init`/`cmd_activate`/`cmd_quick`/`cmd_hub_start` into the bare-invocation
      entry point per design.md Decision 2 (auto-register the current directory against the Hub's
      project table if unregistered, then call `_hub_native_start(app=True)`).
- [ ] 2.3 Rename `cmd_hub_destroy` to `reset`, preserving its two-tier (`--all`) confirmation
      behavior per design.md's open question, unless implementation surfaces a reason to change it.
- [ ] 2.4 Delete every other `cmd_*` function and its argparse subparser: messaging, tasks,
      questions, agent roster, jobs, roles, transport setup, relay/delegate/switch/run,
      checkpoint/summary/log, `mcp-setup`, `spec-push`, `sync-context`. Delete their CLI tests.
- [ ] 2.5 Delete OpenCode/Kimi/Copilot runner configs from `constants.py`
      (`RUNNER_TYPES`/`RUNNER_CONFIGS`/`KNOWN_AGENTS`) and any remaining runner-specific code paths
      those commands' removal doesn't already take with them.
- [ ] 2.6 Verify: `agentweave --help` lists exactly 5 subcommands plus `--version`; full CLI
      regression passes; hand off and commit.

## 3. Spec reconciliation

- [ ] 3.1 Sync this change's delta specs into `openspec/specs/`: create `app-lifecycle`; apply the
      MODIFIED/REMOVED deltas to `agent-tool-surface`, `runtime-diagnostics`, `project-instructions`,
      `agent-context-usage`, `agent-context-onboarding`, `agent-stream-events`, `spec-manifest-sync`,
      `trace-timeline`; retire `opencode-runner` (delete its now-empty main spec file).
- [ ] 3.2 Verify every scenario in the touched delta specs against the implementation from phases
      0–2 — not against intent. Note any scenario that cannot be verified and why.
- [ ] 3.3 Hand off and commit.

## 4. Regression, live verification, and docs

- [ ] 4.1 Run full CLI, Hub, and frontend regressions. Expect a large CLI test-count drop (mirrors
      task 3.16's precedent in the umbrella: deletions are accounted for, not just "fewer tests").
- [ ] 4.2 Live-verify bare `agentweave` end to end in a throwaway `testbed/` directory: first
      invocation registers + launches, a Claude/Codex run starts and streams output, an agent
      messages/tasks through the capability plane, no `watchdog.pid` or `transport.json` is ever
      created, and `agentweave reset` cleans up. Same rigor as `agent-capability-plane` phase 4 (real
      process, no `TestClient` substitute for the parts that must prove a real spawn).
- [ ] 4.3 `openspec validate --all --strict` passes.
- [ ] 4.4 Update `README.md`'s quick start to bare `agentweave` (finishing task 3.17's partial state)
      and remove any remaining local/git-transport or watchdog claims from docs.
- [ ] 4.5 Archive this change; annotate `openspec/changes/2026-07-30-hub-native-experience/tasks.md`
      16.2 with what this successor synced, same pattern as `agent-capability-plane`'s annotation.
- [ ] 4.6 Final handoff and commit.
