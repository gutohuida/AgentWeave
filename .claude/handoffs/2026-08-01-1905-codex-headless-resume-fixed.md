# Handoff: Codex resume and hidden headless execution fixed

**Date:** 2026-08-01T19:05:23+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `a324fb0`
**Agent:** T3 Code / Codex (gpt-5.6-sol)
**Previous handoff:** `.claude/handoffs/2026-08-01-1839-fresh-codex-hub-scaffolded.md`
**Status:** chunk complete

## Goal

Fix the user's manual-acceptance failures in the native Hub's Codex integration: resumed turns
rejected `--sandbox`, and sending a message opened unintended terminal chrome on Windows. Review
T3 Code's current Codex implementation and the official Codex integration surfaces before deciding
whether the fix should remain `codex exec`-based or become an app-server rewrite.

## Current state

Both reported defects are fixed and committed at `a324fb0`. Codex `exec --json` now runs through a
hidden, noninteractive `PipeSession`; Claude remains on `PtySession`. All `codex exec`-level options,
including sandbox or yolo bypass, are placed before the `resume` subcommand. A real direct
new/resume pair and a real restarted-Hub new/resume pair succeeded on Codex CLI 0.146.0 with the
same typed session IDs and exit code 0.

The native Hub was restarted after the commit and is currently ready at `http://localhost:8000`,
PID 6344. The watchdog is intentionally stopped, Codex is idle, and no AgentWeave tasks are active.

The review found that current T3 Code uses `codex app-server` over a hidden stdio child process for
its rich persistent conversation runtime; it uses `codex exec` only for bounded one-shot text
generation. OpenAI's current manual likewise recommends app-server for deep product integrations
needing conversation history, approvals, and streamed agent events. This chunk deliberately fixes
the blocking compatibility defects without silently broadening into that larger protocol rewrite.

During full-suite verification, the fresh local scaffold exposed a separate cross-project fallback
leak: a project without a synchronized DB session could inherit the bootstrap checkout's unscoped
`.agentweave/session.json`. The filesystem fallback is now restricted to
`AW_BOOTSTRAP_PROJECT_ID`; the existing BOLA regression passes.

## Files touched

- `hub/hub/runner_commands.py` — finished and committed; Codex exec options now precede the
  `resume` subcommand so `--sandbox` is parsed by `codex exec`.
- `hub/hub/pty_runner.py` — finished and committed; added `PipeSession`, hidden with
  `CREATE_NO_WINDOW` on Windows, closed stdin, merged stdout/stderr, live line reads, POSIX process
  groups, forced process-tree termination, and safe `.cmd`/`.bat` shim invocation.
- `hub/hub/api/v1/agent_trigger.py` — finished and committed; Codex runs use `PipeSession`, while
  Claude/Claude-proxy/native retain the wide structured-output PTY path.
- `hub/hub/api/v1/agents.py` — finished and committed; local filesystem session fallback is allowed
  only for the configured bootstrap project, preventing cross-project config leakage.
- `hub/tests/test_runner_parsing.py` — finished and committed; resume ordering regressions for safe
  sandbox and yolo modes.
- `hub/tests/test_pty_runner.py` — finished and committed; pipe output/lifecycle, hidden Windows
  flags, closed stdin, and Windows `.cmd` shim coverage.
- `hub/tests/test_agent_trigger.py` — finished and committed; asserts Codex selects the pipe path and
  never calls the PTY spawn path.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — finished and committed; records
  completed follow-ups 3.20 (Codex integration) and 3.21 (bootstrap fallback isolation) with live
  evidence.
- `.claude/handoffs/2026-08-01-1905-codex-headless-resume-fixed.md` — this checkpoint; new.
- `.claude/handoffs/LATEST.md` — updated to point to this checkpoint.

Six older untracked handoffs and `.claude/skills/aw-spec-reindex/` predate this implementation and
remain intentionally unstaged, as listed under Git state.

## Key decisions

1. Codex's `--sandbox` is an `exec`-level option. The failing order was
   `codex exec resume <id> ... --sandbox workspace-write`; Codex's resume parser does not define
   that option. The accepted shape puts shared exec options before `resume`, followed by the thread
   ID and prompt.
2. Codex does not need a PTY for `exec --json`. The CLI describes this as non-interactive mode and
   emits JSONL; ConPTY added visible terminal behavior, ANSI handling, line-wrap corruption risk,
   and socket-exit complexity. A hidden pipe is the smaller and more correct process boundary.
3. Claude stays on PTY. The reported behavior and explicit headless protocol apply to Codex; the
   completed Phase 3 Claude PTY work captures its TTY-dependent behavior and must not be reverted as
   collateral damage.
4. `PipeSession` uses `CREATE_NO_WINDOW` and `stdin=DEVNULL` on Windows. This guarantees no spawned
   console and no interactive input wait. Native `codex.exe` is launched directly; npm `.cmd` or
   `.bat` shims are routed through the system command processor without `shell=True` and remain
   hidden.
5. A full `codex app-server` migration is recommended for a later rich-integration phase, not
   disguised as this bug fix. It entails a persistent JSON-RPC client, initialize/initialized
   handshake, thread start/resume, turn start/interrupt, correlated server requests, approval and
   user-input UI, typed event mapping, and different lifecycle ownership. T3's implementation and
   OpenAI's official contract confirm the direction, but the user should choose that expansion.
6. Restricted filesystem fallback instead of weakening the BOLA assertion. Session JSON has no
   project ID, so it can only safely represent the explicitly configured bootstrap project; any
   other project must use its own synchronized DB row.

## Constraints and user directives (verbatim)

- “There are some issues: error: unexpected argument '--sandbox' found”
- “Another thing is that a new terminal screen is created when I send the message. That is unintended behaviour.”
- “Maybe we need to change codex invocation method and integraation.”
- “Please review the codex integration. You can get inspiration from T3 Code.”
- “Please set codex to a weak model that is inexpensive”
- “Docker doesn't matter anymore.”
- “Yeah and always commit the changes.”
- “After every threshold of implementation you must run the skill `/handoff`”
- “Before starting a new implementation revise the entire session for the spec”
- “let's make sure it works with claude and codex first locally”
- Repository rule: never commit runtime `.agentweave/` state; stage explicitly rather than using
  `git add -A`.

## Dead ends

- The old builder placed `resume <session_id>` immediately after `codex exec`, then appended
  `--sandbox workspace-write`. This happened to satisfy an old hand-written unit assertion but is
  invalid for Codex CLI 0.146.0 because resume has no sandbox option.
- Treating every agent CLI as an interactive terminal was rejected for Codex. The Phase 3 ConPTY
  work solved real Claude/structured-PTY issues but imposed terminal behavior on a CLI surface that
  explicitly does not need a terminal.
- A first Hub resume probe watched for the agent message marker and immediately submitted the next
  turn. The marker arrives before final run bookkeeping; the Hub correctly returned “codex already
  has a run in progress.” Waiting for the agent status to become idle made the same resume pass.
- The initial full suite produced 1 failure (`test_cross_project_list_reads_return_empty_data`):
  the newly present root `.agentweave/session.json` made `_get_session_data`'s unscoped fallback
  visible. Changing the test or hiding the scaffold would have masked a real project-isolation bug;
  the product fallback was restricted instead.
- A full app-server migration was investigated but not begun. It is not a drop-in command swap:
  the process stays alive, requests and responses are correlated, and app-server can initiate
  approval/user-input requests that the current one-turn `exec` parser cannot answer.

## Verification

Ran and passed:

- `codex exec --help` and `codex exec resume --help` on Codex CLI 0.146.0 — confirmed sandbox is
  defined on exec but absent from resume.
- Reviewed installed T3 Code sourcemap sources including `codexLaunchArgs.ts`,
  `CodexTextGeneration.ts`, `CodexSessionRuntime.ts`, and its app-server stdio client. Confirmed rich
  sessions use `codex app-server`, while bounded text generation uses hidden child-process
  `codex exec`.
- Fetched the current official Codex manual and reviewed the App Server protocol, lifecycle,
  thread/start, thread/resume, turn/start, turn/interrupt, events, approvals, and non-interactive
  exec sections.
- Test-first focused baseline after adding regressions failed during collection because
  `PipeSession` did not yet exist; after implementation, the focused runner/process/trigger suite
  passed.
- Direct real `PipeSession` run: new thread `019fbe76-3859-7a02-8807-892688dde544` returned
  `PIPE_NEW_OK`, then resume on the same thread returned `PIPE_RESUME_OK`; both exit 0.
- Restarted-Hub run `run-16ed2f4d`: new session
  `019fbe78-a18b-7643-a96a-90a7e748a0db`, marker `HUB_PIPE_NEW_OK`, exit 0.
- Restarted-Hub run `run-23f767c8`: resumed the same session, marker `HUB_PIPE_RESUME_OK`, returned
  to agent status idle.
- Focused final suite: 77 passed.
- Complete Hub suite: 337 passed, 4 skipped, 4 existing Alembic deprecation warnings.
- `py -m ruff check hub/ tests/` — clean.
- `py -m black --check hub/ tests/` — all 91 files unchanged; existing Python 3.11 versus configured
  Python 3.12 safety-check warning only.
- `git diff --check` and `git diff --cached --check` — clean before commit.
- `git commit -m "Fix Codex resume and hidden headless execution"` — commit `a324fb0`.
- Post-commit native Hub restart — ready at `http://localhost:8000`, PID 6344.

Not tested:

- The user has not yet manually confirmed that no terminal window appears from the dashboard on
  their desktop; the Windows creation flag is unit-tested and the real hidden runs succeeded.
- Codex stop/cancel through the dashboard was not re-run specifically on `PipeSession`; its forced
  process-tree termination shares the existing lifecycle API and has unit coverage, but manual UI
  cancellation remains useful acceptance coverage.
- Claude was not rerun in this chunk because its PTY path was deliberately left unchanged.
- `codex app-server` was reviewed but not implemented or integration-tested in AgentWeave.
- Docker was intentionally not involved.

## Git state

- Branch: `hub-native-experience`.
- HEAD before this checkpoint commit: `a324fb0`.
- No upstream configured; commits are local and unpushed.
- Tracked implementation state is clean after `a324fb0`; only this handoff and `LATEST.md` are
  intended for the checkpoint commit.
- Pre-existing untracked paths, intentionally untouched:
  - `.claude/handoffs/2026-07-29-1803-change4-6-archived-spec-navigation-proposed.md`
  - `.claude/handoffs/2026-07-29-2110-spec-navigation-t1-t9-implemented.md`
  - `.claude/handoffs/2026-07-30-0004-agentweave-strategy-discussion-resolved.md`
  - `.claude/handoffs/2026-07-30-1912-spec-navigation-closed-r1-audit-next.md`
  - `.claude/handoffs/2026-07-31-2049-hub-native-phase1-feel-foundation.md`
  - `.claude/handoffs/2026-07-31-2112-hub-native-phase1-complete.md`
  - `.claude/skills/aw-spec-reindex/`

## Next steps

1. In the dashboard at `http://localhost:8000`, resume the existing Codex conversation and send
   `Reply with exactly MANUAL_HIDDEN_RESUME_OK`; confirm the response completes and no terminal
   window appears. Then start a new chat and repeat once.
2. Start a longer Codex request and use the dashboard Stop control; confirm the PipeSession-backed
   run becomes stopped and a subsequent prompt launches normally.
3. Ask the user whether AgentWeave should now specify and implement the deeper
   `codex app-server` integration. If yes, reread the whole active change and use a spec exploration
   phase before coding; define approval/user-input behavior and persistent process ownership first.
4. If app-server is approved, generate the version-matched JSON schema from the installed Codex CLI,
   design a stdio JSON-RPC client with request correlation and server-request handling, and map
   thread/turn/item events into AgentWeave's typed timeline before replacing `exec`.

## Open questions for the user

- After manually confirming this compatibility fix, does the user want the larger
  `codex app-server` migration now, or should AgentWeave retain `codex exec --json` until the later
  approvals/persistent-session phase?

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — completed follow-ups 3.20–3.21 and
  the remaining phase order.
- `hub/hub/runner_commands.py` — corrected Codex new/resume CLI grammar.
- `hub/hub/pty_runner.py` — PTY versus hidden-pipe process adapters and Windows lifecycle details.
- `hub/hub/api/v1/agent_trigger.py` — runner-specific spawn selection and run lifecycle.
- `hub/hub/runner_parsing.py` — current `codex exec --json` event mapping that an app-server mapper
  would supersede.
- `.claude/handoffs/2026-08-01-1818-phase3-native-runtime-complete.md` — Phase 3 PTY decisions and
  ConPTY dead ends that remain authoritative for Claude.
