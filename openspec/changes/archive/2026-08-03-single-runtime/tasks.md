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

- [x] 0.1 Grep every caller of `get_transport()`, `LocalTransport`, and `GitTransport` across
      `src/agentweave/` (not just `cli.py`) to enumerate what breaks when local/git are deleted.
      Found: only `transport/config.py` and `transport/__init__.py` instantiate `LocalTransport`/
      `GitTransport` directly; `messaging.py`/`session.py`/`roles.py`/`logging_handlers.py` only
      call `get_transport()` generically or check `get_transport_type() == "http"` (which becomes
      always-true, not broken, once local/git are gone — no source change needed there beyond
      `messaging.py`'s dead `TransportType.LOCAL` branch, cleaned up below). `cli.py` has 46
      `get_transport()` call sites, nearly all inside `cmd_*` functions this change's phase 2
      deletes wholesale — left untouched here by design (see design.md's deletion-order rationale);
      phase 2 deletes them, not phase 0.
- [x] 0.2 Adjusted `tests/test_transport_config.py` for the collapsed two-branch behavior
      (`AW_RUN_TOKEN`-bound keyless `HttpTransport`; project-key `HttpTransport` from
      `transport.json`) plus a new `TestGetTransportUnconfigured` class asserting `RuntimeError` when
      neither is present or the configured type isn't `http`.
- [x] 0.3 Deleted `src/agentweave/transport/local.py` and `src/agentweave/transport/git.py`;
      collapsed `transport/config.py::get_transport()` to the two branches (raises `RuntimeError`
      otherwise, replacing the old silent `LocalTransport()` fallback); trimmed
      `transport/__init__.py`'s exports and `constants.py`'s `TransportType`/`GIT_COLLAB_BRANCH`/
      `GIT_SEEN_DIR`; removed `messaging.py::MessageBus.mark_read`'s dead
      `TransportType.LOCAL` branch (now always false — `archive_message` is the only remaining
      path). Deleted `tests/test_transport_local.py`, `tests/test_transport_git.py`,
      `tests/test_messaging.py` (100% `LocalTransport`-dependent; `messaging.py`'s own deletion is
      phase 2's job, once its only remaining callers — deleted `cmd_*` functions and the deleted
      watchdog — are gone). Deleted 2 `test_cli.py` tests whose premise (`cmd_switch`/
      `cmd_agent_set_session` "still works for non-http transport") no longer exists; their
      http-transport sibling tests are untouched and still pass.
- [x] 0.4 Verify: full CLI regression passes (919 passed, 4 skipped, was 974/4 before — net -55,
      accounted for above), full Hub regression unaffected (453 passed, 4 skipped, unchanged); grep
      confirms no remaining `LocalTransport`/`GitTransport` import anywhere in `src/`/`tests/`/`hub/`
      (two harmless prose-only mentions remain: a docstring in `transport/base.py`, updated to
      describe the single remaining backend, and a historical-context comment in
      `test_cli.py::TestSubprocessRunHasTimeout` explaining why that regression guard exists, left
      as-is). Hand off and commit.

## 1. Watchdog removal + 2. CLI surface reduction (merged)

> **Merged during implementation.** Tracing `cmd_status`/`cmd_stop`/`cmd_start`'s actual bodies
> showed they are ~100% watchdog logic — phase 1 could not be verified green in isolation without
> phase 2's entry-point consolidation. Executed and verified together in one pass, per
> `AskUserQuestion` confirmation ("do it now, one pass"). `design.md`'s Decision 2 was also
> corrected during this phase — see below.

- [x] 1.1/2.1 Verification was by full-suite regression at each step rather than tests-added-first
      (the working protocol's normal order inverted here because the change is almost entirely
      deletion — there is very little new behavior to write a test *before*; the app-lifecycle
      scenarios are verified by `tests/test_hub_commands.py` (already covers `cmd_hub_start`, and
      now covers renamed `cmd_status`/`cmd_stop`) plus the live smoke test in 2.7 below).
- [x] 1.2 Deleted `src/agentweave/watchdog.py` (~5,157 lines) and its CLI launch/poll/PID helpers
      (`cmd_start`, `_kill_stale_watchdogs`, `_is_watchdog_process`, `_terminate_watchdog`).
      `agentweave-watch` console-script entry removed from `pyproject.toml`.
- [x] 2.2 Bare invocation (no subcommand) now calls `cmd_hub_start` with `app=True`, unchanged
      body. **Correction to design.md's original Decision 2**: it assumed directory-to-project
      auto-registration existed or was buildable here; it does not exist anywhere in the product
      today (no create-project API/UI, single global `proj-default` bootstrapped independent of
      invocation directory) — that's the separate, not-yet-proposed "Local multi-project workspace"
      slice. Design.md and `specs/app-lifecycle/spec.md` corrected to describe actual behavior:
      bare `agentweave` starts the single native Hub in app mode, full stop.
- [x] 2.3 `cmd_hub_destroy` renamed to `cmd_reset`, body unchanged (two-tier `--all` confirmation
      preserved).
- [x] 2.3b `cmd_status`/`cmd_stop` (previously ~100% watchdog-PID/heartbeat logic) rewritten to be
      what `cmd_hub_status`/`cmd_hub_stop` already did; those two now-duplicate functions deleted.
      `create_parser()`/`main()` rewritten from scratch: 5 subcommands
      (`doctor`/`status`/`stop`/`reset` + bare invocation), argparse subparsers for everything else
      removed.
- [x] 2.4 Deleted every other `cmd_*` function (56 → 5) and its subparser: `init`, `checkpoint`,
      `relay`, `quick`, `task-*`, `msg-*`, `inbox`, `agents-list`, `question-*`, `delegate`,
      `update-template`, `sync-context`, `log`, `mcp-setup`, `transport-*`, `spec-push`,
      `hub-heartbeat`, `activate`, `reply`, `yolo`, `agent-*`, `jobs-*`, `roles-*`, `switch`, `run`.
      Also deleted now-fully-orphaned modules with zero remaining importers anywhere in the repo:
      `src/agentweave/messaging.py` (`MessageBus`/`Message`, only used by deleted commands and the
      deleted watchdog) and `src/agentweave/runner.py` (`build_claude_proxy_cmd` etc., same — its
      own docstring said it was "shared between cli.py (switch/run) and watchdog.py," both gone).
      Removed their exports from `src/agentweave/__init__.py`.
- [x] 2.4b Fixed a real bug in `src/agentweave/diagnostics.py` (used only by the surviving
      `doctor`, not touched by the mechanical deletion above): it recommended `agentweave init`/
      `activate`/`start`/`transport setup` in its hints — all now-nonexistent commands. Removed
      `check_watchdog()` (and its only caller, `_process_exists()`) entirely; fixed every
      dead-command hint string; `check_transport()` narrowed to the single supported type (`http`)
      per the `runtime-diagnostics` delta spec. **Not done**: a full redesign of what `doctor`
      checks (the spec's stated target is Python version, runner CLIs on PATH, port availability,
      DB accessibility, permissions — `check_session`/`check_project_config`/
      `check_project_context` still check the old local-session/`agentweave.yml` model, which nothing
      creates anymore, so `doctor` will now permanently report at least one `fail`/`warn`). Flagged,
      not silently dropped — a correct fix here is real, separate design work, not a mechanical
      deletion, and shouldn't be rushed inside an already-large combined phase.
- [x] 2.5 **Deliberately not done**: OpenCode/Kimi/Copilot entries in `constants.py`
      (`RUNNER_TYPES`/`RUNNER_CONFIGS`/`KNOWN_AGENTS`/`AGENT_RUNNER_DEFAULTS`) were left in place.
      They're validation/config infrastructure shared by `config.py`/`session.py`/`validator.py`/
      `diagnostics.py` — not CLI-command bodies — and are already unreachable (no surviving command
      lets anyone configure an agent with these runner types). Removing them safely means auditing
      each of those four modules' tests, a distinct, lower-value cleanup pass; left for later rather
      than rushed here.
- [x] 2.6 Fixed a real bug introduced by a scripted bulk deletion: `HUB_DIR`/`HUB_COMPOSE_URL`/
      `HUB_ENV_URL`/`HUB_COMPOSE_SHA256_URL`/`HUB_ENV_SHA256_URL` module-level constants sat between
      two functions and were silently deleted along with a removed function's range; caught via
      `NameError`-free import not being sufficient proof (they're only referenced inside still-kept
      function bodies) — found by grepping every constant cli.py defines against its own body after
      the deletion pass, not by the test suite (nothing exercises native Hub start without a real
      Hub). Restored verbatim.
- [x] 2.7 Verify: `agentweave --help` lists exactly `doctor`/`status`/`stop`/`reset` plus bare
      invocation and `--version`. Live-smoke-tested in `testbed/` (not repo root): `doctor`,
      `status`, `stop` all run correctly against no running Hub, with no reference to any deleted
      command in their output. Full CLI regression: 384 passed, 3 skipped (was 919/4 after phase 0
      — net further -535, fully accounted for: ~4,000 cli.py lines deleted, `messaging.py`/
      `runner.py`/`watchdog.py` deleted, ~13 whole test files deleted, several individual tests
      trimmed from otherwise-surviving files). Full Hub regression unaffected: 453 passed, 4
      skipped. Hand off and commit.

## 3. Spec reconciliation

- [x] 3.1 Sync this change's delta specs into `openspec/specs/`: create `app-lifecycle`; apply the
      MODIFIED/REMOVED deltas to `agent-tool-surface`, `runtime-diagnostics`, `project-instructions`,
      `agent-context-usage`, `agent-context-onboarding`, `agent-stream-events`, `spec-manifest-sync`,
      `trace-timeline`; retire `opencode-runner` (delete its now-empty main spec file).
- [x] 3.2 Verify every scenario in the touched delta specs against the implementation from phases
      0–2 — not against intent. Verification found two classes of non-conformance that must remain
      open for phase 4 rather than being silently treated as implemented: (a) `app-lifecycle`'s
      `doctor` scenarios promise port/database/permission checks, but the surviving diagnostics
      still inspect the deleted local-session/`agentweave.yml` model; (b) retained, non-delta
      requirements in `agent-context-onboarding` and `runtime-diagnostics` still name deleted
      `activate`/`switch`/`run` commands. Hub launchability does implement missing-runner CLI
      detection and a typed 409 refusal; the broader stale diagnostic requirements need a scoped
      spec/code reconciliation before archive. All other phase-0–2 deletion scenarios were checked
      against the five-command parser, deleted modules, and Hub-owned trigger path.
- [x] 3.3 Hand off and commit.

## 4. Regression, live verification, and docs

- [x] 4.1 Run full CLI, Hub, and frontend regressions. CLI: 387 passed, 3 skipped. Hub after the
      live-found MCP forwarding fix: 454 passed, 4 skipped. Frontend: 289 passed; production build
      succeeded. The CLI count is down from 919/4 after phase 0 because phases 1–2 deliberately
      deleted the watchdog, collaboration CLI, runner helper, messaging module, and their tests.
      This mirrors task 3.16's precedent in the umbrella: deletions are accounted for, not just
      reported as "fewer tests".
- [x] 4.2 Live-verify bare `agentweave` end to end in a throwaway `testbed/` directory: first
      invocation registers + launches, a Claude/Codex run starts and streams output, an agent
      messages/tasks through the capability plane, no `watchdog.pid` or `transport.json` is ever
      created, and `agentweave reset` cleans up. Same rigor as `agent-capability-plane` phase 4 (real
      process, no `TestClient` substitute for the parts that must prove a real spawn). Verified on
      isolated port 8765 with a temporary Windows profile so pre-existing user Hub data was not
      touched. The first Codex capability attempt exposed that dynamically configured MCP servers
      did not inherit `AW_RUN_TOKEN`; added Codex `env_vars` forwarding by name (never token values
      in argv), regression-tested it, restarted the real Hub, and re-ran successfully: real Codex
      spawn, streamed output, task row, message row, and `LIVE_OK` in 17 seconds. No `watchdog.pid`
      or `transport.json` was created. `agentweave stop` + `reset --all --yes` succeeded and the
      validated temporary profile was removed.
- [x] 4.3 `openspec validate --all --strict` passes (19/19).
- [x] 4.4 Update `README.md`'s quick start to bare `agentweave` (finishing task 3.17's partial state)
      and remove any remaining local/git-transport or watchdog claims from docs.
- [x] 4.5 Archive this change; annotate `openspec/changes/2026-07-30-hub-native-experience/tasks.md`
      16.2 with what this successor synced, same pattern as `agent-capability-plane`'s annotation.
- [x] 4.6 Final handoff and commit.
