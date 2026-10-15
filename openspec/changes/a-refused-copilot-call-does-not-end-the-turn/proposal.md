# Proposal — A refused Copilot call does not end the turn

**Round 1, 2026-10-12** (finding **WPC-1 (high)**, from the work-PC Copilot drive, handoff 0162).
Verified on HEAD `6208e9a5`, against the trial DB `profiles\workpc-drive\agentweave.db`, Copilot's
own session logs (`~\.copilot\session-state\<id>\events.jsonl`) and the installed Copilot CLI
1.0.94-3. **Nothing here is implemented yet.**
**Round 2, 2026-10-12**: re-derived independently. The argument holds; the corrections are listed in
design.md's round log.

## Why

On the `copilot` runner, when the Hub answers a **parent-level** `session/request_permission` with
`reject_once`, the Copilot turn ends at once. The run is recorded `completed`, exit 0, with no reply
text. The agent never says what it was trying to do or what it will do instead. A Claude agent in
the same situation is told why and carries on.

### Evidence: three runs, three times out of three

| Run | Who refused | What | Copilot session |
|---|---|---|---|
| `run-047359204292` | Operator Deny on a `manual` card (`perm-02223854bdf7`); the card's `workspace_verdict` had said *allow* | `echo hi` | `af71334e` |
| `run-b175c9ffa621` | The Workspace judge. This was a WPC-2 false positive on `'\\.git\\'` | a directory listing in the parent turn | `c5e3a780` |
| `run-b1f5b4bedc18` (task `task-f4d1edecf35b`) | The Workspace judge: outside the workspace | `Get-ChildItem 'C:\Python*'` | `cd02df15` |

All three `runs` rows read `status=completed`, `exit_code=0` and `error=NULL`. In `agent_outputs`,
each ends with a `tool_use`, then a `tool_result` reading *"The user rejected this tool call."*
(`is_error`), then the status row *"Run completed (exit 0)."*. There is no `text` row after the
refusal. `run-0473…` was charged one premium request.

In `run-b175c9ffa621`, a refusal **inside a subagent** (Copilot's `task` tool) did not end the
parent turn. In Copilot's `events.jsonl` the subagent's events carry the envelope `agentId`, and its
start and complete events carry `parentToolCallId`. After the refusal Copilot emitted:
1. the subagent's `assistant.turn_end`;
2. `subagent.completed`;
3. the root `tool.execution_complete`, reading *"Agent completed but produced no response."*

The parent then continued. A later **root** refusal in the same run ended it.

### Who ends the turn: Copilot, not the Hub

The Hub has exactly one place that sends `session/cancel`: `send_cancel`
(`hub/hub/copilot_acp.py:2226-2231`). It is reached only from Stop (`check_interrupt`, `:2233`), the
turn timeout (`_await_prompt`, `:2773-2776`) and `fail_turn` (`:2244-2248`). A refusal reaches none
of them. `answer_permission` (`:2376-2425`) returns its answer, records the decision and, for a
refusal the Hub made by itself, calls `on_refusal`. It closes nothing and cancels nothing.

Copilot's own log of the same three turns has the same tail after the refused root call:
1. `permission.completed` with `{result: denied-interactively-by-user, decisionSource: human_response}`.
   Copilot labels even the judge's refusal as a human one.
2. `tool.execution_complete` with `{success: false, error: {code: "rejected", message: "The user rejected this tool call."}}`.
3. `assistant.turn_end`.
4. `session.usage_checkpoint`.

There is no further model call. The installed CLI states the rule outright. Its SDK types,
`copilot-sdk\types.d.ts:1338-1345` (1.0.94-3), say the `agentStop` hook fires when the agent "reaches
a natural terminal stop … and was not aborted **or blocked by a rejected tool**".

### Why the agent is told nothing

ACP cannot carry a reason. `permission_answer` (`copilot_acp.py:863-875`) selects `allow_once` or
`reject_once`, and Copilot's ACP adapter maps either reject option, and `cancelled`, to a reject
with no feedback. The SDK's own reject result does carry `feedback` (`types.d.ts:976`), and the
native runtime has a separate "User feedback: " string, but ACP gives the Hub no way to fill it. The
agent's only report is the fixed sentence "The user rejected this tool call.", and its runtime then
stops.

Claude's runner answers the same refusal through `approve_tool_call`
(`hub/hub/mcp_server.py:3726-3757`) with `{"behavior": "deny", "message": "Denied: <reason>."}`.
Claude reads the reason and continues. That is the parity target.

### What the Hub records today

- **The stop reason is thrown away.** `_await_prompt` reads `stopReason` (`copilot_acp.py:2808`) and
  uses it only to tell `cancelled` apart. It is never logged. `TurnOutcome` (`:1962-1977`) has no
  field for it, `Run` has no column for it (`hub/hub/db/models.py:1180`), and `_runtime_failure_fields`
  (`hub/hub/api/v1/agent_trigger.py:2288`) adds runtime facts only to `run_failed`. The fixture
  `turn_write_shell_mcp.jsonl` returns `{"stopReason": "end_turn"}` (it contains no refusal), and
  Copilot's ACP adapter returns `end_turn` for every prompt that was not cancelled, refused or not.
  No record of the three refused turns holds their stop reason; it is inferred from that code (R2,
  design Context). So the Hub cannot tell "the agent finished" from "a refusal stopped it" by the
  stop reason, and keeping it would not change that.
- **The refusal itself is recorded.** The judge's refusal goes through `on_refusal`
  (`copilot_acp.py:2422-2424` → `agent_trigger.py:3965-4018`) as a `permission_denied` event with
  `decided_by: "runtime"` and a reason. The operator's Deny is recorded on its `permission_requests`
  row (`status=denied`). Its `permission_denied` event for `run-0473…` has no `decided_by` and an
  empty `tool_use_id`. That is a separate gap, noted here and not fixed.
- **The outcome reads as success.** `_await_prompt`'s status order (`:2815-2828`) ends at
  `completed`, and the executor maps that to `run_completed`, exit 0 (`agent_trigger.py:4102-4108`).

### Correction to the handoff: "nobody was told"

This is true for the two chat runs. For the task run it is partly wrong. `evaluate_run_end`
(`agent_trigger.py:4214`) raised `run_diverged` `div-d3199cf88f80` for `run-b1f5b4bedc18`, under the
default `surface` policy, so the operator was shown it. It started nothing. *(R2 corrected R1 here,
which said `run-87919e9b45ca` "then continued the task".)* That next run on the task delivered a new
operator message (`entry-61faf255cfd8`, 09:12:38, in a new conversation `conv-1111f5224059`, with
no `divergence_source_run_id`) telling the agent how to run Python. No sweeper or retry picked the
task up. The task was not left silently `in_progress`. It was left with no notes from the turn
that the refusal ended, and the divergence record does not say a refusal caused it.

## What Changes

- **Always: the turn's stop reason is kept.** `_await_prompt` logs `stopReason` on every prompt.
  `TurnOutcome` carries it, and the run's terminal lifecycle event (`run_completed`, `run_failed`,
  `run_stopped`) and its closing status row carry `stop_reason`. This needs no migration: it goes in
  the payload, not a `Run` column.
- **The Hub knows when a refusal ended the turn.** The turn tracks the last refusal it gave a
  parent-level call: who decided it (the Hub or the operator), the reason, and the tool call id. A
  call is parent-level when its raw `tool.execution_start`, already held in `calls`, carries no
  subagent marker. Any later root activity clears the record: agent text, or a new root tool call.
  A prompt that returns `end_turn` with the record still set has **ended on a refusal**.
- **Then, depending on the operator's choice** (design, `wpc1-a`):
  - **(a) Continue.** The Hub sends one bounded follow-up `session/prompt` in the same ACP session,
    carrying the refusal's reason and telling the agent to continue another way or to call
    `ask_user`. There is at most N per turn (recommended N = 1), none after Stop, a timeout or a
    forced failure, and each continuation is shown on the timeline.
  - **(b) Make it visible.** The turn emits a `copilot.turn_ended_on_refusal` diagnostic, the
    lifecycle payload carries `ended_on_refusal`, and a task's divergence record names the refusal.
  - **(c) Both** (recommended). It continues within the bound, and a turn that still ends on a
    refusal is shown as such.
- **Spec.** If continuation is chosen, the `agent-run-sandboxing` requirement *No Copilot hook
  decides a call or a turn* gains a bounded carve-out (design D6, `wpc1-f`).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-run-sandboxing`:
  - **ADDED**: *A Copilot turn's stop reason is recorded* and *A Copilot turn that a refusal ended
    does not end silently*.
  - **MODIFIED**: *No Copilot hook decides a call or a turn*. The carve-out applies only if `wpc1-f`
    is answered yes.

## Impact

- **`hub/hub/copilot_acp.py`**:
  - `CallFacts` gains a subagent flag, fed from the raw start's envelope and data (`track_call`, `:369`).
  - `answer_permission` records the last parent-level refusal.
  - `on_notification` and the mapper clear that record on later root activity.
  - `_await_prompt` is split, so that the prompt and its wait can run again while `mapper.finish()`
    and the outcome are worked out once.
  - `TurnOutcome` gains `stop_reason`, `ended_on_refusal` and `refusal_continuations`.
  - New constant `REFUSAL_CONTINUATIONS_PER_TURN`.
- **`hub/hub/api/v1/agent_trigger.py`**: a new `_runtime_turn_fields(outcome)` beside
  `_runtime_failure_fields`, added to every terminal lifecycle broadcast and to the closing status
  row's payload.
- **`hub/hub/run_divergence.py`**: the divergence it raises for a run that ended on a refusal names
  the refusal (only under (b) or (c)).
- **`hub/hub/copilot_usage.py`**: no change. `observe_prompt_result` keeps the *last* prompt's
  `usage` (`:291-293`), and that figure is cumulative within the process, so it already includes
  the continuation. Summing it would double-count (design D5, corrected by R3).
- **No migration, no UI change required.** The diagnostic renders through the existing diagnostic
  row; a banner is optional (`wpc1-e`).
- **Tests.**
  - New file: `hub/tests/test_copilot_acp_refusal_continuation.py`.
  - Several tests in `hub/tests/test_copilot_acp_run_turn.py` script a reject followed by `_END_TURN`
    and will now meet a continuation prompt. They are named in `tasks.md` 1.12.
- **Cost.** Each continuation is one more billable `session/prompt`: one premium request times the
  model's multiplier.
- **Overlaps.**
  - `the-workspace-judge-reads-paths-not-patterns` (WPC-2) removes the false positive behind
    `run-b175…`'s ending.
  - `copilot-spend-is-counted-in-its-own-units` owns how a continuation's premium request is shown.
  - `stop-closes-the-tool-card-it-interrupted` touches the same Stop path that must forbid a
    continuation.
