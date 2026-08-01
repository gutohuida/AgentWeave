# Handoff: Codex integration session closed after verified fix

**Date:** 2026-08-01T19:17:23+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `1535af0`
**Agent:** T3 Code / Codex (gpt-5.6-sol)
**Previous handoff:** `.claude/handoffs/2026-08-01-1905-codex-headless-resume-fixed.md`
**Status:** chunk complete

## Goal

Close the completed Codex-integration work with a fresh, durable checkpoint so the next session can
start from verified repository and Hub state without relying on conversational context.

## Current state

The reported Codex defects are fixed. Commit `a324fb0` corrects the resume argument grammar and
launches `codex exec --json` through a hidden, noninteractive `PipeSession` instead of ConPTY;
Claude remains on `PtySession`. Commit `1535af0` contains the detailed implementation checkpoint.
No implementation changed after that checkpoint.

The native Hub is running at `http://localhost:8000`, PID 6344. Codex is configured as the sole
principal agent with model `gpt-5.4-mini`, is currently idle, and the watchdog is intentionally
stopped. There are no active AgentWeave tasks.

Direct and Hub-managed Codex new/resume tests passed on Codex CLI 0.146.0. The complete Hub suite
passed with 337 tests and 4 skips. The only remaining acceptance work is user-visible dashboard
testing: confirm no terminal window appears, and exercise Stop on a PipeSession-backed run.

T3 Code and the official Codex manual were reviewed. A richer future integration should use
`codex app-server` over hidden stdio, but that is a separate protocol project involving persistent
processes, JSON-RPC correlation, approvals, user-input requests, and typed event mapping. It has not
been implemented.

## Files touched

- `.claude/handoffs/2026-08-01-1917-codex-integration-session-close.md` — this fresh session-close
  checkpoint; new and complete.
- `.claude/handoffs/LATEST.md` — updated to point to this checkpoint.

No implementation files were modified after commit `1535af0`. The implementation files and exact
verification evidence are enumerated in the previous handoff.

Pre-existing untracked paths remain untouched and are listed under Git state.

## Key decisions

1. Retain the verified immediate architecture: Codex uses hidden pipes for `exec --json`; Claude
   uses PTY. Rejected putting Codex back on ConPTY because that caused visible terminal chrome and
   adds terminal framing to a noninteractive JSONL protocol.
2. Keep exec-level flags before the `resume` subcommand. `--sandbox` is not a resume option on Codex
   CLI 0.146.0, so the old ordering deterministically failed with exit code 2.
3. Treat `codex app-server` as a separately specified integration, not a command substitution.
   T3's implementation and OpenAI's protocol show that it changes lifecycle, event, approval, and
   request-correlation responsibilities.
4. Require manual desktop confirmation before declaring the visible-window symptom accepted. The
   code path and Windows flags are verified, but the user is the correct observer of desktop chrome.

## Constraints and user directives (verbatim)

- “$handoff”
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

- `codex exec resume <id> ... --sandbox workspace-write` is invalid because resume does not define
  `--sandbox`; keep shared exec options before `resume`.
- ConPTY is inappropriate for Codex's noninteractive JSONL path on Windows and caused the reported
  terminal window. Do not unify Claude and Codex behind one PTY abstraction again without new live
  evidence.
- A Hub resume probe cannot start when the prior agent message has streamed but run-finalization is
  still pending. Wait until the agent reports idle; the Hub correctly rejects overlapping runs.
- Do not hide or weaken the BOLA test when a local `.agentweave/session.json` exists. The product fix
  restricts filesystem fallback to `AW_BOOTSTRAP_PROJECT_ID`.
- A full app-server migration was reviewed but not started because it requires a designed JSON-RPC
  client and approval/user-input behavior.

## Verification

Previously run and passed, still authoritative from commit `a324fb0` and the prior handoff:

- Direct PipeSession new/resume: `PIPE_NEW_OK` and `PIPE_RESUME_OK`, same thread, both exit 0.
- Hub new run `run-16ed2f4d`: `HUB_PIPE_NEW_OK`, exit 0.
- Hub resume run `run-23f767c8`: `HUB_PIPE_RESUME_OK`, same session, returned to idle.
- Focused final suite: 77 passed.
- Complete Hub suite: 337 passed, 4 skipped, 4 existing Alembic deprecation warnings.
- `py -m ruff check hub/ tests/` — clean.
- `py -m black --check hub/ tests/` — 91 files unchanged; existing interpreter/target warning only.
- Implementation commit: `a324fb0 Fix Codex resume and hidden headless execution`.
- Prior checkpoint commit: `1535af0 Checkpoint Codex headless integration fix`.

Run while writing this checkpoint:

- `git branch --show-current` — `hub-native-experience`.
- `git status --short` — no tracked modifications; only the seven pre-existing untracked paths
  listed under Git state.
- `git log --oneline -8` — HEAD `1535af0`; no upstream configured.
- `agentweave hub status` — native Hub ready at `http://localhost:8000`, PID 6344.
- `agentweave status` — Codex idle, watchdog stopped, zero active/completed AgentWeave tasks.

Not tested after the prior checkpoint:

- No new implementation exists to retest.
- The user has not yet manually confirmed absence of a terminal window from the dashboard.
- Dashboard Stop/cancel was not manually exercised on `PipeSession`.
- Claude was not rerun because its PTY path was unchanged.
- `codex app-server` was not implemented or integration-tested.
- Docker was intentionally not involved.

## Git state

- Branch: `hub-native-experience`.
- HEAD before this checkpoint commit: `1535af0`.
- No upstream configured; all commits are local and unpushed.
- Tracked working tree was clean before adding this checkpoint and updating `LATEST.md`.
- Pre-existing untracked paths, intentionally untouched:
  - `.claude/handoffs/2026-07-29-1803-change4-6-archived-spec-navigation-proposed.md`
  - `.claude/handoffs/2026-07-29-2110-spec-navigation-t1-t9-implemented.md`
  - `.claude/handoffs/2026-07-30-0004-agentweave-strategy-discussion-resolved.md`
  - `.claude/handoffs/2026-07-30-1912-spec-navigation-closed-r1-audit-next.md`
  - `.claude/handoffs/2026-07-31-2049-hub-native-phase1-feel-foundation.md`
  - `.claude/handoffs/2026-07-31-2112-hub-native-phase1-complete.md`
  - `.claude/skills/aw-spec-reindex/`

## Next steps

1. Open `http://localhost:8000`, resume the existing Codex chat, send
   `Reply with exactly MANUAL_HIDDEN_RESUME_OK`, and record whether the response completes without
   any terminal window appearing; then repeat once from New chat.
2. Start a longer Codex request, click Stop, confirm the run becomes stopped, and confirm a later
   prompt launches normally.
3. Decide whether to retain the verified `codex exec --json` integration or authorize a new
   specification for `codex app-server`. If authorizing app-server, reread the complete active
   change and use spec exploration before implementation.

## Open questions for the user

- After manual acceptance, should the next work specify a full `codex app-server` integration, or
  proceed to the existing Phase 4 identity/tool-surface work with `codex exec --json` retained?

## Read on resume

- `.claude/handoffs/2026-08-01-1905-codex-headless-resume-fixed.md` — full implementation evidence,
  T3/app-server review, and detailed dead ends.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — authoritative phase ledger,
  including completed follow-ups 3.20–3.21.
- `hub/hub/runner_commands.py` — corrected Codex new/resume command grammar.
- `hub/hub/pty_runner.py` — hidden PipeSession and retained PTY implementation.
- `hub/hub/api/v1/agent_trigger.py` — runner-specific process selection and lifecycle.
- `agentweave.yml` — current one-agent Codex scaffold using `gpt-5.4-mini`.
