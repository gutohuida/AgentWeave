# Handoff 0161: work-PC results for task 10.1, plus two problems to fix at home (F483, R11)

**Date:** 2026-10-02T15:10+01:00 ? **Branch:** master ? **HEAD:** the commit that adds this file (see `## Git state`)
**Agent:** claude-opus-5.5 ? GitHub Copilot app (Copilot CLI 1.0.90-0) ? interactive (work PC)
**Previous handoff:** handoff-0160-2026-10-02-work-pc-checks.md (same directory)
**Status:** chunk complete on the work PC. Resume **at home**: `/resume .claude/work-pc/handoff-0161-2026-10-02-1510-work-pc-findings.md`

> Tracked on purpose, like 0160, so a pull carries it between machines. It holds no key. Do not write one into it.

## Goal

Handoff 0160 sent the human-only checks of `a-run-reaches-the-hub-without-mcp` (task 10.1) to the work PC, on
the premise that company policy blocks MCP there, so a Copilot agent would have to reach the Hub through
`aw-tool`. This session ran setup and item 2, found **the premise does not hold**, and at the operator's call
recorded that and stopped. Two problems were found on the way and are to be fixed at home: **F483** (Copilot
runner "not signed in") and **R11** (the Copilot model list is stale).

## Current state

- **MCP is not blocked for the Hub-launched Copilot on the work PC.** Item 2 ("Create an AgentWeave task titled
  WORKPC-1, then stop.") ran as `run-b9160fb388ca`, exit 0, model Auto resolving to `claude-opus-5`. It
  recorded `harness_mcp_status=connected`, `plane_surface=mcp`; its only Hub call was the MCP tool
  `agentweave-create_task` (`category: mcp` in `agent_outputs.payload`), which created `task-7c9eabf47fd3`. No
  permission card. No `aw-tool` call.
- No policy exists to block it: no `%ProgramFiles%\GitHubCopilot\managed-settings.json`, nothing under
  `HKLM:\SOFTWARE\Policies` for Copilot/GitHub, no `AutoRun`, and the Copilot user cache says plan `business`,
  `is_mcp_enabled: true`. Item 1's interactive `/env` and `/mcp list` were **not** collected, so an org-side
  block that only affects interactive or IDE sessions is not excluded.
- **Not run:** items 3 to 6 and 8, and the credits look. Forcing the shim with `--disable-mcp-server agentweave`
  (how 9.3 did it at home) was offered and declined. So **step 8's question, whether Copilot's shell sessions
  persist between a run's commands on the work PC, is unanswered.**
- **Task 10.1 stays open** (neither done nor waived). The `DECISIONS.md` row `a-run-reaches-hub-10.1` now
  records the remaining choice.
- **Task 10.2 (archive) has a second, older blocker:** `npx openspec validate a-run-reaches-the-hub-without-mcp
  --strict` (openspec 1.13.2) fails:
  `agent-capability-plane/spec.md: MODIFIED "HTTP and MCP access have equal capability" omits scenario(s) the
  current spec still has: "The CLI offers no agent capability"` (delta has 9 scenarios, current spec 8; it adds
  "The application's CLI offers no agent capability" and "The call command is the adapter's own program"). This
  is not from this session; the delta looks like it renamed that scenario. Either copy the old scenario back or
  confirm the rename is intended and restate it so archive does not drop it.

## Problems to fix at home

### 1. F483 (A): a Copilot runner reads "not signed in" right after `copilot login`

Full entry: `scripts/drive/FINDINGS.md`, F483.

- **Symptom:** creating a Copilot agent returns `409` "Copilot CLI is not signed in. Run `copilot login`.", and
  running `copilot login` does not help.
- **Cause (reproduced):** Copilot 1.0.89-1 keeps the token in the Windows Credential Manager
  (`?github.com:<login>.copilot-cli`) but finds which account to read through `lastLoggedInUser` and
  `loggedInUsers` in `$COPILOT_HOME/config.json`. The Hub's worker home
  (`~/.agentweave/hub/copilot-home/worker`) and every per-agent home
  (`copilot-home/projects/<pid>/<agent>`) start without those keys, so `session/new` returns
  `-32000 "Authentication required"`. An empty home fails; the same home with only those two keys succeeds.
  `GH_TOKEN` cannot rescue it: `copilot_guard_env` strips it.
- **Contradicts** `openspec/explorations/2026-09-27-copilot-as-a-full-runner/a-copilot-cli-capabilities.md:249`
  (auth survives an empty `COPILOT_HOME`, measured at home). Check at home whether the home PC has a different
  credential path (a `gh` token, or an older CLI) before deciding the fix; the home PC may never reproduce it.
- **Code paths:** `hub/hub/copilot_home.py` (`ensure_copilot_home`), `hub/hub/copilot_probe.py` (the
  launchability probe and its reason text), `hub/hub/copilot_env.py` (`copilot_guard_env`).
- **Fix candidates (not chosen):** (a) when creating the worker home and each agent home, copy
  `lastLoggedInUser`/`loggedInUsers` from the operator's default Copilot home (`~/.copilot/config.json`, JSONC;
  neither key is a secret or a permission), re-copying when they change; (b) at minimum, make the not-signed-in
  reason name the home that was probed, so "run `copilot login`" stops being advice that cannot work.
  (a) fixes it; (b) only explains it. Probably both.
- **Test idea:** a unit test that seeds a fake default home with the two keys and asserts `ensure_copilot_home`
  writes them into the agent home without touching other keys. The repro script used here was
  `probe_login.py` (session scratch, not committed): it ran the probe's `PROBE_ARGS` with `copilot_guard_env`
  against an empty and a seeded home.
- This is a spec-worthy change (it touches Copilot slice 2's home contract): run the spec loop (R1/R2/R3) or ask
  the operator whether it is a small direct fix.

### 2. R11: update the Copilot model list

Full entry: `spec-queue/REQUESTS.md`, R11.

- `_COPILOT_MODEL_IDS` in `hub/hub/model_catalog.py` (around lines 186-212) was copied from `copilot help config`
  on 1.0.88. On 1.0.89-1, that command adds `claude-opus-5.5` (after `claude-fable-5`), and `gpt-6-sol`,
  `gpt-6-luna` (before `gpt-6-astra`).
- The operator said Copilot also offers **Sonnet 5.5**, but 1.0.89-1's `help config` lists no
  `claude-sonnet-5.5` (only `claude-sonnet-5`). Confirm the exact id with `copilot help config` / `/model` on a
  newer build before adding it.
- Open design question in R11: read the catalog from `copilot help config` at probe time instead of a hand copy.

## Files touched

- `scripts/drive/FINDINGS.md`: F483 appended. Finished.
- `spec-queue/REQUESTS.md`: R11 appended. Finished.
- `spec-queue/DECISIONS.md`: dated bullet under the `a-run-reaches-hub-10.1` row (still OPEN). Finished.
- `openspec/changes/a-run-reaches-the-hub-without-mcp/design.md`: Round log entry "Work PC, task 10.1
  (2026-10-02 ?)". Finished.
- `.claude/handoffs/DEAD-ENDS.md`: seven "(work PC)" entries. Finished.
- `.claude/work-pc/handoff-0161-2026-10-02-1510-work-pc-findings.md`: this file.
- Not touched: `tasks.md` (10.1 deliberately left unticked), `model_catalog.py`, any `copilot_*.py`.

## Key decisions

- **Stop after item 2 and record "MCP not blocked"** (operator's choice). Rejected: forcing the shim with
  `--disable-mcp-server agentweave` to finish items 3 to 6 and 8. That would still have tested the work PC's
  lockdown (AppLocker, PowerShell policy, the Copilot shell) against `aw-tool`, so it remains an option.
- **10.1 not ticked**: the checks were neither completed nor waived; ticking it on a partial run would claim
  verification that did not happen.
- **F483 seeding was done by hand on the work PC only** as a workaround, not committed as code.

## Constraints and user directives (verbatim)

- "pull the lattest changes and run a /resume"
- "Apply all that in a handoff and the problems found so I can fix it in my machine. Push this as well so I can
  pull and continue the work"
- From 0160, still binding: never point a Hub you are editing at this repo; never touch `:8000`; never write a
  key into a tracked file; keep model prompts few and one sentence; do not archive until 10.1 is settled; item 6
  failing on F478 is expected (add a line to F478, not a new finding). Durable: `CLAUDE.md`, `AGENTS.md`.

## Dead ends

All seven are in `.claude/handoffs/DEAD-ENDS.md` ("(work PC)"): no `py` launcher (`uv venv -p 3.11`,
`UV_NATIVE_TLS=1`), `reg.exe` blocked, the agent `view` tool refused by a repo hook, JSONC breaking
`ConvertFrom-Json`, F483's auth pointer, MCP not blocked. One more, session-only: **the work PC cannot push to
`gutohuida/AgentWeave`**; its only GitHub account is the enterprise-managed `gustavo-santos_hiscox` (`403`).

## Environment left running

None. The test Hub on `127.0.0.1:8010` was stopped and the port checked free. Left on disk (work PC only, not in
git): venv `~/.agentweave/venv-workpc`, database `~/.agentweave/hub/profiles/workpc/agentweave.db`, throwaway
project `~/aw-workpc-throwaway` (`proj-3b13e6dd753b`), and the hand-seeded `config.json` in the worker home and
in `copilot-home/projects/proj-3b13e6dd753b/test/`.

## Verification

- Ran: the Hub's runner launchability (flipped to `runnable: true` after seeding); item 2 through the app; a
  read-only SQLite inspection of `runs`, `agent_outputs`, `permission_requests`, `event_logs`; checks for
  managed-settings files and HKLM policies; `copilot help config` on 1.0.89-1; a secret scan of the diff
  (no `aw_live_` or `aw_run_`); `npx openspec validate a-run-reaches-the-hub-without-mcp --strict` (fails, see
  above).
- **Not tested:** no code changed, so no pytest/vitest run. The shim path on the work PC. Item 1's interactive
  `/env` and `/mcp list`. Whether F483 reproduces at home.

## Git state

Branch `master`. Base `84c024b1` (handoff 0160). Commits from this session:
- `e49ab6bf` Work PC 10.1: MCP not blocked for the Hub's Copilot; F483, R11, traps
- the commit adding this file.
Review range: `84c024b1..<this commit>`. Tree clean after commit.

## Corrections to the previous handoff

- 0160 said the work PC is "the only machine where company policy blocks MCP". **False for the Hub-launched
  Copilot**, see Current state.
- 0160's setup step 2 says `py -3.11 -m pip ?`: the work PC has no `py`; use a uv venv.
- 0160 assumed `copilot login` is enough for the Hub's Copilot. It is not on 1.0.89-1 (F483).

## Next steps

1. At home: `git pull`, then reproduce F483: start a trial Hub on a fresh profile, delete the worker home's
   `config.json` keys `lastLoggedInUser`/`loggedInUsers` (or point at a fresh `copilot-home`), and read
   `/api/v1/projects/<pid>/runners/launchability`. If it reproduces, implement fix (a)+(b) in
   `hub/hub/copilot_home.py` / `copilot_probe.py` with a test; if not, record in F483 why the home PC differs.
2. R11: run `copilot help config` on the home build, update `_COPILOT_MODEL_IDS`, confirm the Sonnet 5.5 id,
   and run the model-catalog tests (`pytest hub/tests -q -k model_catalog`).
3. Fix the strict-validate failure in `openspec/changes/a-run-reaches-the-hub-without-mcp/specs/
   agent-capability-plane/spec.md` (the dropped scenario).
4. Ask the operator to settle `a-run-reaches-hub-10.1`: waive 10.1 on this evidence, or go back to the work PC
   and force the shim. Only then tick 10.1 and do 10.2.

## Open questions for the user

- 10.1: waive, or force the shim on the work PC next visit? (Carried once; first asked this session.)
- F483: copy the account pointer into each Copilot home (fix a), or only improve the message (fix b)?

## Read on resume

- `scripts/drive/FINDINGS.md` (F483, at the end): the problem and fix candidates.
- `spec-queue/REQUESTS.md` (R11, at the end): the model list change.
- `hub/hub/copilot_home.py`: where fix (a) lands.
- `openspec/changes/a-run-reaches-the-hub-without-mcp/design.md`, Round log "Work PC, task 10.1": the evidence.
- `.claude/handoffs/DEAD-ENDS.md`: the work-PC entries.
