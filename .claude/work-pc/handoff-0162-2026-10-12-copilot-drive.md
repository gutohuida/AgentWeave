# Handoff 0162: a comprehensive live drive of the Copilot runner on the work PC

**Date:** 2026-10-12T10:20+01:00 · **Branch:** master · **HEAD:** 6208e9a5 (plus this file, uncommitted)
**Agent:** claude-opus-5.5 · GitHub Copilot app (Copilot CLI 1.0.94-3) · interactive (work PC)
**Previous handoff:** handoff-0161-2026-10-02-1510-work-pc-findings.md (same directory)
**Status:** drive complete. Resume **at home**: `/resume .claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md`

> Tracked on purpose, like 0160/0161, so a pull carries it between machines. It holds no key. Do not write one into it.
> The work PC cannot push (403). The operator carries this file home by hand or by a commit made elsewhere.

## Goal

The operator asked what the unattended loops built since 10-09 and whether they work, then asked for
comprehensive testing of the Copilot runner here, where the GHCP licence is. A source trial Hub on
`:8010` (profile `workpc-drive`, outside the repo) drove two real Copilot agents in a throwaway git
project `C:\Users\santosg\aw-workpc-drive\proj-1012-095734` (`proj-d73f8848ee60`). There were 21
turns, 19 premium requests and about 156 AIU, including two checkpoint worker calls.

## Findings to file at home

These are provisional `WPC-n` ids. The home loop had reached F583 on
`autonomous/2026-10-11-daily` and is still filing, so F-numbers taken here would collide. File them in
`scripts/drive/FINDINGS.md` with the next free numbers.

- **WPC-1 (high) — on Copilot, any refused tool call ends the turn silently.** On a parent-level
  `reject_once`, whether decided by the Workspace judge or by an operator Deny, Copilot ends the prompt
  at once. The run records `completed`, exit 0, with **no reply text**. Observed 3 of 3 times:
  - `run-047359204292`: manual Deny of `echo hi`.
  - `run-b175c9ffa621`: the Workspace judge refused a listing.
  - `run-b1f5b4bedc18`: a **task** turn. The judge refused `Get-ChildItem 'C:\Python*'`, the turn ended
    mid-work, the task stayed `in_progress` with no notes, and nobody was told.

  A refused call inside a subagent (`task`) does not end the parent; only a parent-level refusal does.
  Claude's `approve_tool_call` returns the reason and the agent carries on, so this is a parity gap.
  `permission_answer` (`hub/hub/copilot_acp.py:863`) can only select `reject_once`, which carries no
  reason. The reason is recorded as a `permission_denied` event (`decided_by: runtime`), but the agent
  sees only "The user rejected this tool call." `stopReason` is not logged, so whether Copilot reports
  `end_turn` or something else is unknown; log it first.

  Fix shape, not decided: after a Hub-decided refusal ends the prompt, send a follow-up
  `session/prompt` in the same session carrying the refusal reason ("that was refused because …;
  continue another way"). Or mark the run as needing attention rather than `completed`.

- **WPC-2 (medium) — the Workspace path check reads regex and script-block text as paths.**
  - `Get-ChildItem -Recurse -Force -File | Where-Object { $_.FullName -notmatch '\\.git\\' } | Resolve-Path -Relative`
    is refused with "'\\\\.git\\\\' is outside your workspace".
  - The `-LiteralPath <worktree>` variant is refused because `'\\.git(\\|$)'` "contains a variable".

  Both are read-only and inside the worktree. Reproduce with
  `mcp_server._decide("Bash", {"command": ...}, workspace=..., hub_url=...)`. Combined with WPC-1, an
  ordinary listing ends the turn. Plain `Get-ChildItem -Recurse -File` and `git ls-files` are allowed.

- **WPC-3 (medium) — Copilot model catalog drift blocks real models.** `hub/hub/model_catalog.py`
  `CATALOG["copilot"]` was checked against CLI 1.0.94-3.
  - Missing from the catalog: `claude-haiku-5.5` and `grok-4.7`. A trigger override with
    `claude-haiku-5.5` gets a 400: "not a model 'copilot' declares".
  - In the catalog but no longer offered: `claude-opus-4.7`, `gemini-3.6-flash`, `gemini-3.5-flash`
    and `kimi-k2.7-code`.

- **WPC-4 (medium) — a stale `.agentweave/calls/*.json` collides with the shim prompt's example.**
  `prepare_calls_dir` (`hub/hub/api/v1/agent_trigger.py:250`) never clears the directory, and the
  prompt's example name is `1.json`. On the second shim turn the agent's create failed twice. It then
  read and edited the leftover file, and the turn cost 151k tokens instead of about 75k.

- **WPC-5 (low) — a Copilot shim spec turn is told to use the file-writing tool, which it does not
  have.** `SPEC_TURN_EXCLUDED_TOOLS` (`copilot_acp.py:142`) removes `edit`, but the shim prompt
  (`launchability.py` ~460, `agents.py` ~1794) says to write the args file with the file-writing tool
  first. Claude keeps `Write` on shim spec turns (D16); Copilot has no equivalent. One call failed
  before a `Set-Content` fallback worked.

- **WPC-6 (low) — Copilot worker credits are outside project accounting.** The two checkpoint
  `worker_invocations` rows carry `premium_requests 1.0` and `ai_nano_aiu` about 1.1 and 0.8 AIU, with
  `input_tokens` NULL. `GET /projects/{pid}/accounting` sums only `turn_usage`, showing 19, so Copilot
  spend is under-reported. The `conversation-checkpoint` spec requires only that they be recorded.
  Also, `preferred_display` is `tokens` for an all-Copilot project, even though AIU and premium
  requests are known.

- **WPC-7 (low) — after a Stop, the shell `tool_use` has no `tool_result`.** The timeline card
  dangles. Seen in the stop-race retry.

### Observations, not findings: decide whether they are intended

- A project with no spec can never have a review turn. `review_task_id` returns 409 "no recorded
  evidence" (`requirement_evidence.py` ~1229), and `record_evidence` needs a requirement id. The
  agent tried the task id as the identifier and got a 404.
- A different `runtime_overrides` on a task trigger opens a new task conversation, without
  resuming the old one. The agent re-discovered its own work from scratch, which cost about 355k
  tokens.
- `claude-sonnet-5.5` answered with 0 reasoning tokens, so no thinking events appeared and the
  thinking UI could not be exercised on Copilot.
- `turn_usage.allowance` is stored as the string `'null'`.
- The `copilot` runner's posture values are `acceptEdits | bypassPermissions | manual | workspace`;
  `full` is refused with a 400, while the UI says "Full access".

## Confirmed working, with evidence in the trial DB

| Area | Result |
|---|---|
| F483 account pointer | Synced into the agent and worker `config.json` at creation; runs signed in |
| Workspace write | `hello.txt` written in the worktree; no `aw_run_`/`aw_live_` in events |
| Model override | `gpt-5-mini` used 0 premium requests and was kept in `runtime_overrides` |
| Manual card | Raised and denied correctly (see WPC-1 for what happened after) |
| `ask_user` | Works over MCP and over the shim |
| Spec turn (MCP) | `rename`/`submit`/`set_spec_size`; doc events carry run attribution |
| Stop | `stopped`, exit 1; `copilot.exe` and the child shell were killed, with no leftovers |
| Shim (`--disable-mcp-server agentweave`) | `harness_mcp_status=absent`, `plane_surface=shim`; `aw-tool` create, ask and **spec submit (F478 fixed)** all work |
| Back to MCP | Resuming the same conversation after removing the flag gives `connected` |
| Subagent | `explore` dispatched, with `subagent_started`/`completed` events |
| GitHub MCP toggle | `search_code`/`get_file_contents` answered correctly while on; toggled off cleanly |
| Checkpoint | Needs `checkpoint_runner_id` set; then 201, probe passed, 23 s, cites outputs, `files_changed` correct |
| Task flow | Under `bypassPermissions`: pytest passed, `update_task` completed, and the Hub auto-snapshot committed |
| Vault MCP | `vault_map` works (empty) |
| Shell persistence | **Does not persist between turns**: `$env:` set in turn N is gone in turn N+1. This answers 0161's item 8 |

Typical cost on Copilot Auto (resolves to `claude-sonnet-5`): 1 premium request and 2.5–21 AIU per
turn, 42k–404k input tokens. Spec turns are the heaviest.

## Environment left running

Nothing. The trial Hub on `:8010` was stopped. The throwaway project and the
`~/.agentweave/hub/profiles/workpc-drive/` profile were left on disk for inspection; both are outside
the repo and safe to delete. The drive script `wpc_drive.py` is in the session files dir, not the repo.

## Constraints and user directives

- Never touch `:8000`. Never point the Hub you are editing at this repo.
- The work PC cannot push; do not commit unless asked.
- The `copilot-test-setup` skill is stale: it still describes the deleted watchdog. Drive a source Hub
  instead.

## Next steps (at home)

1. File WPC-1..7 as F-numbers, with WPC-1 first. It is a correctness bug that makes Copilot task turns
   fail silently in the default posture.
2. Decide the two observations: review without a spec, and a new conversation on an override change.
3. Refresh `CATALOG["copilot"]` (WPC-3) — cheap, Tier 1.


---

## Addendum (same day): specs written for the findings, nothing decided, nothing committed

At the operator's request ("create specs for those fixes and tests"), six openspec changes went through the full spec loop. Each round was a fresh agent: R1 wrote the change, R2 and R3 independently re-derived it against the code. All six pass `npx openspec validate <name> --strict`. **None is committed**, because this PC gets a 403 on push. Carry these files home:

| Change (`openspec/changes/`) | Finding | Capability |
|---|---|---|
| `a-refused-copilot-call-does-not-end-the-turn` | WPC-1 | agent-run-sandboxing |
| `the-workspace-judge-reads-paths-not-patterns` | WPC-2 (security) | agent-run-sandboxing |
| `the-copilot-catalog-matches-the-cli` (+ `evidence/`) | WPC-3 | model-catalog |
| `a-call-file-turn-starts-clean-and-can-write-its-file` | WPC-4/5 | agent-run-sandboxing, agent-tool-surface |
| `copilot-spend-is-counted-in-its-own-units` | WPC-6 (depends on worker-spend D7) | usage-accounting |
| `stop-closes-the-tool-card-it-interrupted` | WPC-7 | agent-stream-events |

Also changed:
- `spec-queue/DECISIONS.md`: new section `wpc-1012` with 38 OPEN rows, each carrying the rounds' recommendation, plus 4 `wpc-obs-*` product questions.
- `.claude/handoffs/DEAD-ENDS.md`: a work-PC block.

The operator chose to decide later, so no row is DECIDED and task 0.3 is unticked in every change. Rows marked KEY are the real tradeoffs: wpc1-f, wpc2-a, wpc3-b, wpc3-c, wpc3-f, wpc4-a, wpc7-d. D7 of worker-spend is still the gate for WPC-6.

Findings to file at home (do not take F-numbers on this PC): wpc4-c (shared project-dir race), wpc4-d (two agents on one task both start in one checkout), wpc4-e (work_dir into another agent's isolated workspace), and F486-adjacent (PATCH /budget commits before reading totals, so an overflow gives a 500 and skips rescheduling).

Implementation preconditions recorded in the tasks:
- WPC-2 needs one live payload captured to learn the subagent's raw toolName.
- WPC-3 task 3.2 needs a prompted run to learn whether `-p` substitutes or errors on a removed model.
