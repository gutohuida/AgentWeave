# Handoff: Single runtime completed and archived

**Date:** 2026-08-03T11:53:47+01:00 · **Branch:** hub-native-experience · **HEAD:** a677935
**Agent:** Codex gpt-5.6-sol
**Previous handoff:** .claude/handoffs/2026-08-03-1129-single-runtime-phase3.md
**Status:** chunk complete

## Goal

Complete the Hub-native-experience umbrella one independently proposed successor at a time. The
single-runtime successor makes the native Hub the only collaboration/execution runtime and reduces
the CLI to application lifecycle commands.

## Current state

`single-runtime` is implemented, regression-tested, live-verified, spec-synced, and archived at
`openspec/changes/archive/2026-08-03-single-runtime/`. Local/Git transports, the watchdog, and the
collaboration CLI were deleted in prior commits. This phase repaired instance diagnostics, current
specs/docs, and a real Codex MCP run-token forwarding bug found only by live verification.

The umbrella remains open until all successors are complete. Archived successors now include
conversation workspace, accounting and budgets, agent capability plane, composer intelligence, and
single runtime. The strongest next implementation candidate is runner/agent/charter separation;
the repository instructions already warn against extending the legacy role model before that slice.

## Files touched

- `README.md` — replaced with the single-runtime product/quick-start documentation; finished.
- `mkdocs.yml` — removed retired guides from active navigation and added a historical archive entry; finished.
- `docs/index.md`, `docs/getting-started/quickstart.md`, `docs/reference/cli-commands.md`, `docs/architecture/overview.md` — rewritten for single runtime; finished.
- `docs/getting-started/installation.md`, `docs/guides/aw-spec-workflow.md`, `docs/reference/hub-api.md` — removed retired command/runtime references; finished.
- `docs/archive/legacy-multi-runtime/README.md` — labels the preserved pre-single-runtime documentation as historical.
- `docs/archive/legacy-multi-runtime/{adding-new-agents,agentweave-yml,ai-jobs,alternative-modes,claude-proxy-agents,configuration,context-files,cross-machine-collab,faq,logging-guide,messaging,migration,opencode-agents,opencode-models,session-modes,transport-layer,watchdog}.md` — preserved retired active docs; finished.
- `src/agentweave/diagnostics.py` — non-mutating instance-level Python/Hub/runner/port/database/permission checks; finished.
- `src/agentweave/cli.py` — status now reports bootstrap project identity; finished.
- `src/agentweave/tool_surface.py` — removed obsolete multi-runtime identity wording; finished.
- `tests/test_diagnostics.py`, `tests/test_hub_commands.py` — readiness/status coverage; finished.
- `hub/hub/runner_commands.py` — Codex MCP `env_vars` forwarding by name for run identity; finished.
- `hub/tests/test_runner_command_env.py` — proves run-token names are forwarded without token values in argv; finished.
- `hub/hub/api/v1/agent_trigger.py`, `hub/hub/launchability.py`, `hub/hub/output_recording.py`, `hub/hub/pty_runner.py`, `hub/hub/runner_parsing.py` — removed false watchdog/local/git descriptions; finished.
- `openspec/specs/agent-context-onboarding/spec.md`, `openspec/specs/runtime-diagnostics/spec.md` — reconciled Hub-owned context/readiness flows; finished.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — annotated the additional partial 16.2 sync; umbrella remains open.
- `openspec/changes/archive/2026-08-03-single-runtime/` — complete archived change, including the final task state.
- `.claude/handoffs/2026-08-03-1153-single-runtime-archived.md`, `.claude/handoffs/LATEST.md` — final handoff chain update.

## Key decisions

- Existing user Hub state was not touched. Live verification used a temporary `USERPROFILE` and
  port 8765, then stopped/reset and deleted only that validated temporary profile.
- Retired documentation was preserved under `docs/archive/legacy-multi-runtime/` instead of being
  destroyed, but removed from active navigation and labeled historical.
- The first real Codex capability run revealed its MCP subprocess did not inherit `AW_RUN_TOKEN`.
  Official Codex documentation identifies `mcp_servers.<id>.env_vars` as the safe whitelist. The
  fix forwards names only, avoiding secret token values in command arguments.
- MkDocs was unavailable, so active-doc grep/path inspection replaced the site build; this is
  explicitly unverified rather than implied green.

## Constraints and user directives (verbatim)

> "I want you to work on the entire umbrella project with the same parameters that we discussed previously"

> "Ignore the aw-spec skills. I'm using openspec only."

> "At the end of every implementation run handoff aaand spawn a new run with the skill resume."

No root AgentWeave state. Stateful product checks only under `testbed/` or isolated temporary
locations. Never mark implementation complete from a plan alone.

## Dead ends

- First live Codex run had approvals enabled, so both MCP mutations were cancelled as designed.
- Second live run enabled approvals but exposed `AW_RUN_TOKEN` missing in the Codex MCP subprocess;
  fixed with documented `env_vars` forwarding and verified on the third real run.
- `mkdocs` is not installed in this environment, so `mkdocs build --strict` could not run.
- Python 3.12 is not installed; Black 3.11 safety parsing rejects the project target, so formatting
  used the existing `black --fast` workaround.
- Ruff remains unavailable.
- Hub and CLI `test_mcp_server.py` modules collide if collected together; suites were separate.

## Verification

- CLI: `py -3.11 -m pytest tests/ -q` — 387 passed, 3 skipped.
- Hub after live-found fix: `py -3.11 -m pytest tests/ -q` from `hub/` — 454 passed, 4 skipped.
- Frontend: `npm run test -- --run` — 289 passed; `npm run build` succeeded with the known duplicate-case warning.
- OpenSpec: `openspec validate --all --strict` — 18/18 passed after archive.
- `git diff --check` passed; active docs grep found no retired runtime/command claims outside archives.
- Live: isolated bare `agentweave --port 8765`, real Codex spawn, streamed output, authenticated
  task and message creation, `LIVE_OK`, no retired runtime files, stop/reset, temporary profile removed.
- Not tested: MkDocs site build (tool unavailable); Claude live spawn (Codex covered the real spawn contract).

## Git state

Branch `hub-native-experience`, pre-final-commit HEAD `a677935`. The tree contains the final
single-runtime implementation/docs/archive/handoff changes and will be clean after the commit that
contains this file. Upstream status was unavailable.

## Next steps

1. Re-read the runner/agent/charter-separation row in
   `openspec/changes/archive/2026-08-02-agent-conversation-workspace/design.md`, inspect current
   agent/runner/role code and the deprecation note in `AGENTS.md`, then propose that successor with
   OpenSpec unless the user redirects.
2. Continue remaining umbrella successors and technical explorations; only after all are complete,
   finish umbrella tasks 16.1–16.4 and archive it.

## Open questions for the user

None.

## Read on resume

- openspec/changes/archive/2026-08-02-agent-conversation-workspace/design.md
- openspec/changes/2026-07-30-hub-native-experience/tasks.md
- openspec/changes/archive/2026-08-03-single-runtime/tasks.md
- AGENTS.md
- src/agentweave/constants.py
- hub/hub/launchability.py
