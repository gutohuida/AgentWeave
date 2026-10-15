# Proposal — Stop closes the tool card it interrupted

**Round 1, 2026-10-12** (finding **WPC-7 (low)**, from the work-PC Copilot drive, handoff 0162).
Verified against HEAD `6208e9a5`. **Nothing here is implemented yet.**

**Round 2, 2026-10-12.** Re-derived from the code and the trial DB. The main corrections are below
and in `design.md` (D7 and the R2 round log):

- Real completed runs already split a call from its result across work blocks. In the trial DB,
  6 of 50 `tool_use` rows in 5 completed runs show as `awaiting result` today. R1's UI rule would
  have relabelled them `no result`.
- The closing row can land in its own block, behind the rows `finish()` emits.
- New open question `wpc7-d` covers both. Its recommended answer pairs results to calls across the
  whole turn, so the per-block pairing requirement is replaced (REMOVED plus ADDED).

## Why

When the operator presses Stop while an agent is in the middle of a tool call, the run ends with a
`tool_use` row that no `tool_result` row ever answers. The timeline then shows that card as
`· awaiting result` under a "Turn stopped" divider, permanently, including after a reload.

### The evidence (trial DB, read-only)

`C:\Users\santosg\.agentweave\hub\profiles\workpc-drive\agentweave.db`, run **`run-e183cc3e1acd`**:

- agent `cop-1`, runner `copilot`, conversation `conv-ddc8df1220cb`
- status `stopped`, exit 1, 09:02:14.650 → 09:02:41.542

It is the only `stopped` run in that DB, and the only run in it whose `tool_use` has no
`tool_result` anywhere. (R2: five completed runs also *show* a card as `awaiting result`, because
their result sits in a later work block. See D7.) Its `agent_outputs` are exactly three rows, in this order:

| seq | kind | timestamp | content / payload |
|---|---|---|---|
| 1 | `thinking` | 09:02:27.369 | — |
| 2 | `tool_use` | 09:02:27.381 | `{"version":1,"call_id":"toolu_01Ky1xyEL7aTrBkrR3fyKsZX","tool":"shell","category":"command","input":"{…\"command\": \"Start-Sleep -Seconds 240; echo done\"…}","summary":"Sleep 240 seconds then print done","truncated":false}` |
| 3 | `status` | 09:02:41.930 | `Run stopped (exit 1).` `{"phase":"completed","exit_code":1}` |

Its `event_logs` are:

- `run_started` (09:02:14.661)
- `run_stopped` (09:02:41.920), with `{agent, run_id, conversation_id, session_id, exit_code: 1}`

The drive's `t_stop()` (session file `wpc_drive.py:293-310`) triggered "Run
`Start-Sleep -Seconds 240; echo done`", waited 25 s, and then called `POST /agent/cop-1/stop`.

### Why the card is never closed (code, opened and checked)

- **Stop on an RPC run only raises a flag.** `stop_agent_run` (`hub/hub/api/v1/agent_trigger.py:
  2121-2179`) adds the run to `_stop_requested` (`:2163`). `_execute_rpc_run` passes
  `should_interrupt=lambda: run_id in _stop_requested` (`:4030`), and the runner sends its own
  cancel.
- **Copilot's cancel path never closes open tools.**
  - `send_cancel` (`hub/hub/copilot_acp.py:2226`) sends `session/cancel` (`:2231`).
  - `_await_prompt` (`:2742`) waits up to `CANCEL_GRACE_SECONDS = 10.0` (`:158`) for the prompt to
    answer. It then calls `emit(mapper.finish())` (`:2806`) and settles `status = "interrupted"`
    (`:2818`).
  - The mapper emits a `tool_result` only for a `tool_call`/`tool_call_update` whose status is in
    `_TERMINAL_STATUSES = ("completed", "failed")` (`:896`, `:1138`, `:1147`).
  - `finish()` (`:1190`) flushes text, thoughts, notices and the review-agents report. It never
    looks at `self._tools`, so a tool Copilot never reported as terminal stays open.
- **The ACP protocol puts this on the client.** The prompt-turn spec's Cancellation section says:
  *"The Client SHOULD preemptively mark all non-finished tool calls pertaining to the current turn as
  `cancelled` as soon as it sends the `session/cancel` notification."* AgentWeave is the client here.
- **The executor writes the status row straight after.** `outcome.status == "interrupted"` maps to
  `stopped` / `run_stopped` (`agent_trigger.py:4099-4100`). The executor then writes the closing
  `Run stopped (exit 1).` row at `sequence + 1` (`:4254-4268`). `_on_event` (`:3925-3945`) is the
  only other writer of the run's outputs, and it records whatever the mapper emitted.
- **No runner closes open tools on any ending.**
  - The only `tool_result_event(` callers are the normal mappers: `codex_appserver.py:499-583`,
    `copilot_acp.py:1163` and `runner_parsing.py:323-589` (Claude).
  - Codex's interrupt (`codex_appserver.py:1095-1102`) waits for `turn/completed`.
  - Claude's PTY stop terminates the process tree.
  - The PTY executor's `_record_events` (`agent_trigger.py:2892-2918`) and its status row
    (`:3266-3277`) have the same gap.
  - Kimi and OpenCode are not bindable runners (R2): `RUNNER_CLIS` and `ADAPTERS` hold only
    `claude`, `codex` and `copilot`. No third executor writes a run's outputs.

  WPC-7 was observed on Copilot only, but the gap is runner-agnostic.
- **The UI never consults the run's status for a card.**
  - `WorkRow` (`hub/ui/src/components/agents/AgentTimeline.tsx:770-870`) sets its suffix to
    `· failed` / `· completed` when `findPairedResult` (`hub/ui/src/lib/agentTimelineModel.ts:76-90`)
    finds a result, and to `· awaiting result` otherwise (`:802-808`).
  - `AgentTimeline` already knows each turn's run status: `runStatus` (`:281`),
    `TERMINAL_STATUSES` (`:60-66`), and the "Turn stopped" label (`:71-72`, `:299`).
  - But `TurnBody` (`:442-557`) and `WorkBlockDisclosure` (`:559-667`) do not pass that status down.
- **A reload shows the same thing.** The chat route returns run facts for every run its entries
  name (`hub/hub/api/v1/agent_chat.py:724`, `:796`, `_run_facts_for`). The rows are persisted, so the
  dangling card is identical after a reload.

**Where the handoff overstates it.** It describes the card as "dangles, running forever". The card
is a static text label, not a spinner. The "Working" indicator does stop, because the run is
terminal. The severity is low, but the label misreports what happened to a command that may have
had side effects.

## What Changes

- **Hub (recommended part (a)).**
  - When a run ends as `stopped` or `failed` on a path that writes its terminal status line, and a
    `tool_use` it recorded has no result, the executor that ran it records one closing
    `tool_result` per open call. Each carries the same `call_id`, `payload.status = "interrupted"`,
    and a summary such as `shell interrupted`.
  - These rows come after every runner-emitted row and before the run's closing status row. A
    closing row that fails to persist is logged and does not change how the run ended.
  - This applies in `_execute_rpc_run` (Copilot, Codex app-server) and in `_execute_run` (PTY:
    Claude, Codex exec).
  - A run that ends without a status line gains no rows: a raising transport, a Hub shutdown, or a
    restart reconcile. Part (b) covers those.
- **UI (recommended part (b)).**
  - An unanswered `tool_use` in a turn whose run is terminal reads as ended, not as
    `· awaiting result`. "Unanswered" means no result anywhere in the turn. The exact wording is
    open question `wpc7-b`.
  - A synthesised result with `payload.status = "interrupted"` reads `· interrupted`, not
    `· completed` or `· failed`.
  - Under `wpc7-d` (i), a `tool_result` pairs with its `tool_use` anywhere in the same turn, not
    only within one work block. This fixes today's split pairs and keeps the closing row on its
    card.
  - This also covers runs the Hub never saw end:
    - runs reconciled at startup;
    - runs reconciled by the open change `stop-clears-a-run-an-earlier-hub-left-running`;
    - every historical run.
- **Payload.** A `tool_result` payload gains one optional key, `status`, whose only defined value
  is `"interrupted"`. The payload stays `version: 1` because the key is additive.

## Capabilities

### Modified Capabilities

- `agent-stream-events`: three ADDED requirements and one REMOVED.
  - ADDED: A run's end closes the tool calls it left open.
  - ADDED: An ended run's unanswered tool call is presented as ended.
  - ADDED: Each work block carries its own state, and pairing spans the turn.
  - REMOVED: Each work block carries independent state. Its expansion and duration rules are
    carried into the ADDED one word for word; only pairing changes, from per block to per turn by
    call identifier (`wpc7-d` (i); both dropped under (iii)). A MODIFIED block cannot drop the
    scenario "Pairing does not cross blocks", so it is a replacement.

## Impact

- `hub/hub/runner_events.py`: `tool_result_event` gains an optional `status` (or a sibling builder
  is added).
- `hub/hub/api/v1/agent_trigger.py`:
  - an open-call tracker in `_on_event` and in `_record_events`;
  - the close, before each executor's closing status row.
- `hub/ui/src/components/agents/AgentTimeline.tsx`: a run-ended flag threaded through `TurnBody` and
  `WorkBlockDisclosure` to `WorkRow`; under `wpc7-d` (i), pairing over the turn's entries instead of
  the block's (`:566-575`, `findPairedResult` in `agentTimelineModel.ts:79-90`).
  - This needs a bundle refresh (`make ui` / `scripts/refresh_ui_bundle.py`).
  - That bundle reaches the operator's `:8000` app on their next reload.
- No migration and no new event kind. The closed taxonomy is unchanged.
- Existing tests: R1 cited `hub/ui/src/__tests__/agentTimeline.test.tsx:846-865` as the
  "no run facts reads awaiting result" control. R2: that test is the cross-block pairing test
  ("does not pair a tool_use with a tool_result across a block boundary"). Under `wpc7-d` (i) it is
  inverted (task 1.14), and the control is a new test (task 1.9).
