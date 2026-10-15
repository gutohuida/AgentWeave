# Design — Stop closes the tool card it interrupted

**Built on the recommended answers:**

- `wpc7-a` = (c): the Hub closes open calls, and the UI also derives an ended state.
- `wpc7-b` = the closed card reads `interrupted` and is not counted as a failure.
- `wpc7-c` = every ending except a clean completion closes open calls.
- `wpc7-d` = (i): a tool result pairs with its call across the whole turn, not only within its work
  block (added by R2, D7).

Each open question at the end says what to drop or change if the operator answers differently.

## Context

Run `run-e183cc3e1acd`, trial DB `workpc-drive`, has these rows, in this order:

1. `thinking`
2. `tool_use` (call `toolu_01Ky1xyEL7aTrBkrR3fyKsZX`, `shell`, `Start-Sleep -Seconds 240`)
3. `status` `Run stopped (exit 1).`

No `tool_result` exists for the call. The proposal traces why:

- Copilot's mapper closes a call only on a terminal `tool_call_update` (`copilot_acp.py:896`,
  `:1147`).
- `finish()` (`:1190`) does not sweep open calls.
- No executor and no other runner does either.
- The UI decides "awaiting result" from pairing alone (`AgentTimeline.tsx:802-808`), without the run
  status it already holds (`:281`).

ACP's Cancellation section assigns the close to the client: *"The Client SHOULD preemptively mark
all non-finished tool calls … as `cancelled`"*.

**The grace did not expire (R2).** `stopReason` is not logged anywhere, but the timing settles it.
The drive's `t_stop()` posts the trigger, waits 25 s and then posts Stop. The run started at
09:02:14.650, so Stop arrived no earlier than 09:02:39.65. The run's `ended_at` is 09:02:41.542, so
the turn returned within about 1.9 s of the cancel, well inside `CANCEL_GRACE_SECONDS = 10.0`.
Copilot answered the prompt inside the grace, and sent no terminal
`tool_call_update` for the shell call first: had it sent one, the mapper would have written a
`tool_result` (`copilot_acp.py:1147`). R1 left both readings open.

The design must still hold for a grace that does expire, which is the deadline path in D3.

## D1 — Where the close happens: the executor, not the mapper

**Chosen: each executor tracks the call ids it has recorded and closes the open ones once the turn
has returned.**

- In `_execute_rpc_run`, `_on_event` (`agent_trigger.py:3925`) adds the `call_id` of each `tool_use`
  to an ordered dict of open calls, keyed by call id and holding the tool name. It removes the id on
  the matching `tool_result`.
- After `start_turn` returns (`:4022-4032`), once the status map (`:4097-4105`) has settled
  `final_status`, the executor records one closing `tool_result` per entry left, through the same
  `_on_event`. The rows therefore take the next sequence numbers, and the status row
  (`sequence + 1`, `:4254-4269`) still comes last.
- **Placement within that window (R2).** Put the sweep between the status map and the
  `async with async_session_factory()` that commits the `Run` row (`:4115`), not beside the status
  row. The commit is followed by `_broadcast_run_lifecycle` (`run_stopped`), and the status row is
  written only after that. A sweep beside the status row would let an open app refetch on
  `run_stopped` and render a stopped run with an open card for the time the sweep takes. With D4
  in place the label is the same either way, so this is not a correctness bug, but it is visible if
  `wpc7-a` is (a), and it costs one extra refetch.
- `_execute_run` does the same around `_record_events` (`:2892-2918`), between its status map
  (`:3064-3071`) and the `async with` that commits its `Run` row (`:3079`), for the same reason; its
  status row (`:3266-3280`) comes later still.
- **A failed closing write must not change the run's ending (R2).** `_on_event` writes through
  `_record_observation` (`:2365`), which retries a `database is locked` and then drops the row, but
  lets any other exception propagate. Placed before the `Run` commit, a propagating exception
  would reach the outer `except` and turn a `stopped` run into `failed` with no status row. So the
  sweep catches and logs any exception per row, and the `Run` commit and status row go ahead.
- **The sweep runs only where the status row is written.** It is not reached when `start_turn`
  raises:
  - the early `except (FileNotFoundError, AppServerError, TimeoutError, OSError)` (`:4033-4078`)
    marks the run failed and returns, with no status row;
  - any later exception, and the `CancelledError` of a Hub shutdown, goes to the outer `except`
    (`:4277`) and `_record_run_failure_tail` (`:2431`), again with no status row.

  This is deliberate. Those paths already end without a terminal line, and D4 is what covers them
  (D3). The early `except` is also moot for Copilot: `run_turn` raises only before it calls
  `_await_prompt` (`copilot_acp.py:2723`), which is where every `tool_use` is emitted, and
  `_await_prompt` reports a mid-turn failure as a failed `TurnOutcome` instead of raising.
- **Kimi and OpenCode need nothing (R2).** They are not bindable runners. `RUNNER_CLIS` is
  `("claude", "codex", "copilot")` (`hub/hub/launchability.py:32-41`), `ADAPTERS` holds only those
  three (`hub/hub/runner_adapters/__init__.py:23-27`), and `parse_opencode_line`
  (`runner_parsing.py:644`) has no caller. The two executors above are the only writers of a
  run's outputs.

Alternatives considered:

- **Mapper-level `finish(interrupted=True)` in `copilot_acp.py`.** This is closest to ACP's wording,
  and it would place the closing rows before `finish()`'s own flush. But it is Copilot-only: Codex
  and Claude would need their own copies. (R1 also argued that it "cannot see a `start_turn` that
  raised"; R2 found the executor sweep cannot either, see above, so that is not a difference.)
- **A post-hoc sweep at read time in the chat route.** No row is written, so SSE subscribers and any
  other reader of `agent_outputs` still see the call as open. That is the UI derivation (D4) under
  another name.

A call with no `call_id` cannot be paired (`agent-stream-events`, "Provider omits a call
identifier"). It is not tracked, and no result is invented for it. The UI fallback (D4) is all it
gets.

## D2 — The closing row's shape

The closing row is `kind: "tool_result"`, built by `tool_result_event` (`runner_events.py:233-253`)
with:

- the open call's `call_id` and `tool`;
- `output: ""` (the command produced nothing that reached the Hub);
- `summary`: `"<tool> interrupted"`;
- `is_error: false` (see `wpc7-b`);
- a new optional payload key, `status: "interrupted"`.

The key is additive. `Versioned kind-specific payloads` requires `version=1` and the kind's
required fields, and both still hold. The self-report schema (`hub/hub/schemas/agents.py`)
constrains only size, so it is unaffected.

Alternatives considered:

- **A `diagnostic` or `status` row instead of a `tool_result`.** This does not pair. The card would
  still read "awaiting result" unless the UI special-cased it, and the taxonomy says a tool's
  outcome is a `tool_result`.
- **`is_error: true` with no new key.** This needs no schema change, but the work-block header would
  count a stopped command as `1 failed` (`AgentTimeline.tsx:601`), in red. That is a product choice:
  `wpc7-b`.

## D3 — Which endings close open calls

The executor already reduces every ending to `stopped`, `failed` or `completed` (`:4097-4104`), and
the PTY path does the same. The close applies to:

- `stopped`: Stop pressed. This is WPC-7.
- `failed`: this covers a timeout (`_await_prompt` sends cancel at the deadline, `:2773-2775`), a
  runner crash, a forced failure, a quota refusal, and a binding conflict — **on the paths that
  return a `TurnOutcome`**. A `failed` reached by raising is not swept (below).

These are the reductions on both runners that exist: Kimi and OpenCode are not runners, so there is
no third executor (D1).

R2 checked what a real `failed` turn emits before it returns, because it decides where the closing
row lands (D7). It is not always the bare `tool_use` R1's test 1.2 assumed:

- Copilot records a session error as an `error` row when its raw event arrives, and `finish()`
  (`copilot_acp.py:1190`) runs on every ending, cancel included: it flushes buffered `text`, emits a
  `diagnostic` for each unechoed `session.warning|info` (`_notice_event`, `:1272`), and, for a
  reviewer, the review-agents `status` report.
- Codex app-server records `map_turn_failure` (an `error` row) before it breaks out of a failed turn
  (`codex_appserver.py:1206-1209`, `:1222`).

Any of those sits between the open `tool_use` and the closing row.

It does not apply to `completed`. A clean completion with an unanswered call is a runner or mapper
defect. Labelling it "interrupted" would hide that. The UI fallback (D4) shows it as `no result`
instead, provided the call truly has no result anywhere in its turn (D7). `wpc7-c` asks whether to
close on `completed` too.

**Endings the sweep does not reach (R2, corrected).** R1 said only "a Hub that dies cannot write".
The real list is every path that ends without the status row (D1):

- `start_turn` raising: the early `except` (`agent_trigger.py:4033-4078`) or the outer `except`
  (`:4277`) and `_record_run_failure_tail` (`:2431`). The run ends `failed`.
- **A clean Hub shutdown.** `terminate_all_active_runs` (`:2182`) only adds each run to
  `_stop_requested`; `_settle_background_runs` (`hub/hub/main.py:369-410`) then cancels the run
  tasks. The `CancelledError` takes the outer `except`, so the run ends `failed` with no status row
  and no sweep.
- **A Hub that crashes.** Nothing runs. Startup reconciliation sets the run `interrupted`
  (`hub/hub/run_reconciliation.py:77-82`), as will the open change
  `stop-clears-a-run-an-earlier-hub-left-running`. Neither path writes outputs, and this change does
  not add a writer there.

D4 covers all of these.

**Every ending, checked one by one (R3).** "Status line" means the run's terminal `status` row,
which is where the sweep sits.

| Ending | Status line | Run ends | Swept | Card without the sweep |
|---|---|---|---|---|
| Stop, prompt answered in the 10 s grace | yes | `stopped` | yes | D4: `interrupted` |
| Stop, grace expired | yes | `stopped` | yes | D4: `interrupted` |
| Timeout (`send_cancel`, then no wait for the answer) | yes | `failed` | yes | D4: `interrupted` |
| Other `TurnOutcome` failure (forced, root error, quota, binding conflict) | yes | `failed` | yes | D4: `interrupted` |
| Completed | yes | `completed` | no (`wpc7-c`) | D4: `no result` |
| `start_turn` raises (`:4033-4078`, or the outer except and `_record_run_failure_tail`) | no | `failed` | no | D4: `interrupted` |
| Clean Hub shutdown (`_settle_background_runs` cancels the task) | no | `failed` | no | D4: `interrupted` |
| Hub crash, then startup reconcile | no | `interrupted` | no | D4: `interrupted` |

Two things that look like endings are not:

- **A budget or allowance hold, or `queue_agent_paused`.** These act between runs. A run that was
  already going ends by one of the rows above; a held dispatch never starts a run, so it has no
  calls.
- **An `ask_user` wait.** The run stays `running` while the tool waits for the operator, so its
  card correctly reads `awaiting result`. A Stop during the wait is the first row of the table,
  and the `ask_user` call is closed like any other.

For every row without a status line, D4 alone is enough: `failed` and `interrupted` are both in
`TERMINAL_STATUSES`, and the chat routes return the run facts on reload. Until the run's status
commits, the card reads `awaiting result`, which is true at that moment.

## D4 — The UI derives an ended state from the run

`AgentTimeline` passes `runEnded = TERMINAL_STATUSES.has(runStatus)` and the run status into
`TurnBody`, then `WorkBlockDisclosure`, then `WorkRow`. `WorkRow`'s suffix becomes the table below.
"Result" means a `tool_result` with the call's identifier **anywhere in the same turn**, not only in
the same work block. That is `wpc7-d` (i); D7 shows why the table is wrong without it.

| result for the call | run status | suffix |
|---|---|---|
| `payload.status === "interrupted"` | any | `· interrupted` |
| `is_error === true` | any | `· failed` |
| other result | any | `· completed` |
| none | `stopped`, `interrupted`, `failed` | `· interrupted` |
| none | `completed` | `· no result` |
| none | not terminal, or no run facts | `· awaiting result` (today's text) |

This also covers runs written before this change, runs that are reconciled, and runs whose Hub died.
That is why it is part of the recommendation and not only a fallback. It holds on reload, because
the chat route returns run facts for every run its entries name (`agent_chat.py:724`, `:796`).

The header's failure count (`AgentTimeline.tsx:601`) counts only `is_error === true`, so a closing
row with `is_error: false` is already not counted. Task 2.4's "do not count it" is a guard for
`wpc7-b` (ii), not a behaviour change.

**Live behaviour (R2, confirmed; R1 pointed at the wrong file).** The chat query is invalidated in
`hub/ui/src/api/agentChat.ts`, not in `useSSE.ts` (whose own `run_*` handler, `:497-517`, refreshes agents,
accounting, projects and worktrees). `useAgentChatHistory` and `useAgentRecentChat` both invalidate
their chat key on any event `eventTargetsAgent` accepts, which includes every `agent_output` for the
agent and the four `RUN_TERMINAL_EVENT_TYPES` (`run_completed`, `run_failed`, `run_stopped`,
`run_interrupted`). `record_agent_output` commits the row and then broadcasts `agent_output`
(`hub/hub/output_recording.py:108`, `:119`). So both the closing row and the `run_stopped` that
re-reads the run facts reach an open app without a reload.

## D5 — Ordering and duplication

- **Same sequence space.** The closing rows go through `_on_event`, so they share the run's
  `sequence`. A row can never land after the status row.
- **No duplicate after a late update.** A call that Copilot did close, even after `session/cancel`
  (ACP permits updates until the prompt answers), has left the open dict before the sweep. So it
  gets no second result.
- **No late real result can race the sweep (R2, re-derived per runner).** For every runner, the
  last real row is written before the executor gets control back, so the order is always: every
  real row, then the closing rows, then the status row. A real `tool_result` can never take a
  higher sequence than the closing row for the same call, and the UI never has to choose between
  two results.
  - **Copilot.** `session.close(force=...)` runs in `run_turn`'s `finally`
    (`copilot_acp.py:2736-2739`) and cancels the session's reader before `start_turn` returns, so
    nothing from that session reaches `on_event` after the sweep.
  - **Codex app-server.** `run_turn` pulls notifications inline in its own loop
    (`codex_appserver.py:1094-1296`) and calls `on_event` from that loop; there is no background
    reader to deliver one after it returns. `close(force=interrupted)` is in its `finally`.
  - **PTY (Claude, Codex exec).** `_record_events` is the only output writer, called from the
    reader loop (`agent_trigger.py:3019-3029`). A kill ends `pty.read`, the loop ends, and only then
    do `pty.wait` and the status map (`:3064-3071`) run.
- **Codex's own close on interrupt is unmeasured (R2).** The interrupt loop
  (`codex_appserver.py:1094-1102`) sends `turn/interrupt` and keeps reading until `turn/completed`
  (`:1197-1215`); any `item/completed` that arrives first is mapped as usual. Whether Codex sends
  `item/completed` for an in-flight `commandExecution` on interrupt is not known: the only test,
  `hub/tests/test_codex_appserver_run_turn.py:846-875`, feeds just `turn/completed`, and no capture
  exists. `CommandExecutionStatus` has no interrupted value (`inProgress`, `completed`, `failed`,
  `declined`), so if Codex does close the item it will say `failed` — counted red as `· failed`
  under `_FAILED_ITEM_STATUSES` (`:97`) — or something D4 reads as `· completed`. Either way the
  sweep finds the call closed and adds nothing. Task 3.4 measures it; the design is correct for
  both outcomes, but `wpc7-b`'s promise that a Stop never reads as a failure holds for Codex only
  if Codex leaves the item open.
- **Codex exec (PTY)** is killed on Stop like Claude, so its calls stay open and the sweep closes
  them.
- **Copilot can say `failed` too (R3).** ACP's `ToolCallStatus` is `pending`, `in_progress`,
  `completed` or `failed`; it has no cancelled value. ACP asks the client to mark the calls
  cancelled, so a well-behaved agent may send nothing. But if Copilot does send a terminal
  `tool_call_update` with `status: "failed"` after `session/cancel` and before the prompt answers,
  `_tool_call_update` (`copilot_acp.py:1113-1165`) maps it to a `tool_result` with
  `is_error: true`. The card then reads `· failed`, counted red, and the sweep adds nothing. So
  `wpc7-b`'s "a Stop never reads as a failure" holds for Copilot only if Copilot sends nothing or
  `completed`. Task 3.2 measures it. R3 walked every ordering of the three real messages (a
  terminal update after the cancel, the prompt answer, the grace expiring): an update before the
  answer becomes the call's one result; after the answer or the grace, `run_turn`'s `finally`
  has closed the session, so nothing more arrives and the sweep closes the call. No ordering
  leaves the card dangling or gives it two results.

## D6 — Interaction with the open change `stop-clears-a-run-an-earlier-hub-left-running`

That change makes Stop settle an orphaned `running` row to `interrupted` with no runner attached.
It writes no outputs. This change neither depends on it nor conflicts with it:

- D1 cannot reach those runs.
- D4 renders their open cards as `interrupted` once their status is `interrupted`.

If both land, they can land in either order.

## D7 — A result in a different work block (added by R2)

D4's fallback rows decide "no result" from the paired result. Today the pairing looks only inside
one work block (`AgentTimeline.tsx:566-575`), and the current spec requires it
(`openspec/specs/agent-stream-events/spec.md:334-336`: "A tool result MUST NOT be paired with a tool
use from a different block", scenario "Pairing does not cross blocks"). A work block is a run of
`thinking`, `tool_use` and `tool_result` rows (`agentTimelineModel.ts:8-16`); any `diagnostic`,
`status`, `error` or `text` row ends it.

Real runs already split a call from its result. The completed run `run-08d33fa23f8e` in the trial
DB:

| seq | kind | content |
|---|---|---|
| 4 | `tool_use` | `edit`, call `toolu_01MBqBcf…` |
| 5 | `diagnostic` | Copilot `session.info` for the file it created |
| 6 | `tool_result` | `edit`, call `toolu_01MBqBcf…`, "Created file …" |
| 10 | `status` | `completed`, exit 0 |

Across the trial DB, 6 of 50 `tool_use` rows, in 5 completed runs, are separated from their real
result by a non-work row (`diagnostic` in five, `status` rows in `run-b175c9ffa621`). The UI shows
each as a card reading `· awaiting result` beside a second block holding an orphan result.

That is a pre-existing defect, but this change makes it worse and makes its own fix unreliable:

1. **D4 as R1 wrote it mislabels those calls.** "No paired result, run `completed`" reads
   `· no result`; in a stopped or failed run it reads `· interrupted`. Both are false: the call has
   a result two rows down.
2. **The closing row can itself land in a separate block.** D3 lists what a stopped or failed
   Copilot or Codex turn writes before it returns: `finish()`'s flushed `text`, notice
   `diagnostic`s and review `status`, and `error` rows. Any of them between the open `tool_use` and
   the sweep's `tool_result` puts the closing row in its own block. The open card still reads by
   D4's fallback (correct by accident, since the run is stopped), and an orphan `· interrupted`
   result row appears below it.

`wpc7-d` asks the operator how to resolve it. The recommendation, (i), pairs every `tool_result` to
its `tool_use` by call identifier across the whole turn: the result renders at its call's card, an
emptied work block is dropped, and D4's "result" means "a result anywhere in the turn". That
replaces the per-block pairing rule. The spec delta therefore REMOVES the existing "Each work block
carries independent state" requirement and ADDS "Each work block carries its own state, and pairing
spans the turn". It is a replacement rather than a MODIFIED block because openspec's validator
refuses a MODIFIED block that drops a scenario, and "Pairing does not cross blocks" must go.
Expansion state and duration stay per block. A block's failure count counts the results it renders,
so a result moved to its call's block is counted there. A result whose call is not in the turn
still renders as its own row, as it does today.

**What "the turn" is, and whether a result can reach the wrong card (R3).**

- A turn is the entries of one run: `groupIntoTurns` keys on `run_id` (`agentTimelineModel.ts:46-69`),
  and the current spec says the same. Turn-wide pairing therefore never crosses runs. A call id a
  provider reuses in a later run cannot pick up an earlier run's result. In the trial DB no call id
  repeats at all, within a run or across runs. A legacy row with no `run_id` is a turn of its own,
  so it pairs with nothing, as today.
- Copilot subagent calls carry their own ids (`call_…`, beside the parent's `toolu_…`), so a
  subagent's result cannot close the parent's card.
- One call can get two results. The mapper drops a repeated `tool_use` by call id, but not a
  repeated `tool_result` (for example a `tool_call` that already carries a terminal status, then a
  terminal update). Today `findPairedResult` (`agentTimelineModel.ts:79-90`) takes the first, and
  the second renders as its own row. Turn-wide pairing keeps that: the first result in the turn
  pairs, and any later one renders on its own. The spec delta now says so, and control test 1.15
  pins it.
- The recent-chat route caps the number of entries and cuts the oldest first
  (`agent_chat.py:728-800`). It can drop a call and keep its later result, which then renders as an
  orphan row (control 1.13). It can never keep a call and drop its result. So truncation can make
  an orphan, but never a wrong label. The conversation route is uncapped.

## Round log

- **R1 (2026-10-12): written.**
  - Evidence: the trial DB, read-only (one stopped run, three rows), and the drive script.
  - Code read at HEAD `6208e9a5`:
    - `agent_trigger.py`: the stop route, both executors, and the status rows;
    - `copilot_acp.py`: the mapper, `_await_prompt`, and the cancel;
    - `codex_appserver.py`: the interrupt;
    - `runner_events.py`;
    - `AgentTimeline.tsx` and `agentTimelineModel.ts`;
    - `agent_chat.py`: the run facts.
  - ACP's Cancellation section was read from agentclientprotocol.com.
  - No captured Copilot cancel transcript exists. `hub/tests/fixtures/copilot_acp/` holds only
    `oneshot_ok.jsonl` and `turn_write_shell_mcp.jsonl`. So test 1.1 is assembled from a captured
    `tool_call` line plus the existing cancel test's prompt answer, and task 3.2 captures the real
    one.
- **R2 (2026-10-12, work PC): re-derived from the code at HEAD `6208e9a5`; not trusting R1.**
  - Read: the stop route (`POST /{agent}/stop`, `api/v1/agent_trigger.py:2120`); `_execute_run` (PTY) to its status row, and
    `_execute_rpc_run` through its except paths and the Run commit; `start_turn`/`run_turn`/
    `_await_prompt`/`finish()` in `copilot_acp.py`; `run_turn`'s interrupt and `turn/completed`
    handling in `codex_appserver.py`; `record_agent_output`; `terminate_all_active_runs`,
    `_settle_background_runs` and the startup reconcile; the chat and outputs routes and their
    ordering; `agentChat.ts`, `useSSE.ts`, `AgentTimeline.tsx`, `agentTimelineModel.ts`; the
    current `agent-stream-events` spec; and the overlapping change.
  - Evidence: the trial DB, read-only. `run-e183cc3e1acd` (stopped, rows 1-3) and
    `run-08d33fa23f8e` (completed, 10 rows), plus a scan of all 50 `tool_use` rows.
  - Fixed:
    - **D7 added (HIGH).** 6 of 50 real calls have their result in a different work block. D4's
      fallback rows would label them `no result` or `interrupted`. New question `wpc7-d`; the
      spec delta replaces the per-block pairing requirement (REMOVED plus ADDED).
    - **The closing row can be orphaned (MEDIUM).** `finish()` and error rows can land between the
      open call and the sweep (D3, D7).
    - **D1/task 2.2 overclaimed (MEDIUM).** A runner that raises skips the status row and the
      sweep; so does shutdown cancellation (`_settle_background_runs`). The sweep goes between the
      status map and the Run commit, not beside the status row, so `run_stopped` never refetches a
      run whose card is still open. The spec's "observes" is scoped to endings that write the
      terminal status line.
    - **A closing write that raises would have flipped the ending (MEDIUM).** Before the `Run`
      commit, an exception other than a lock propagates to the outer `except` and turns `stopped`
      into `failed`. The sweep now catches and logs per row (D1).
    - **Task 1.9 pointed at the wrong test (MEDIUM).** The "no run facts" control R1 cited
      (`agentTimeline.test.tsx:846-865`) is the test that pins per-block pairing; its call has a
      result. 1.9 is now a new test, and 1.14 inverts the old one under `wpc7-d` (i).
    - **D3's "Hub that dies" text was wrong (LOW).** Clean shutdown ends `failed` with no status
      row; a crash is reconciled to `interrupted`. D4 covers both.
    - **Context's grace claim (LOW).** The stop came about 1.9 s before `ended_at`; the 10 s
      grace did not expire.
    - **D4's live path pointed at `useSSE.ts` (LOW).** It is `agentChat.ts`; confirmed.
    - **Kimi and OpenCode (LOW).** Not runners; no third executor.
    - **Test order (LOW).** Tasks 1.1, 1.10 and 1.11 and the spec's scenarios now use the order the
      outputs route returns, and the test guide and proposal carry the R2 findings.
  - Confirmed, no change: no late real result can race the sweep on any runner (D5); the routes
    return ascending `(timestamp, sequence, id)` and the closing rows sort after every real row;
    no Hub consumer reads `tool_result` rows for side effects (`outside_writes` reads only
    `write_paths`); D6 holds.
  - Not resolved: whether Codex closes an in-flight item on interrupt, and with what status (D5,
    task 3.4); Copilot's real cancel traffic (task 3.2).
- **R3 (2026-10-12, work PC): a fresh comparison from the operator's side, at HEAD `6208e9a5`.**
  - Traced: the Stop button (`AgentOutputPanel.tsx:867-885`) → `POST …/agent/{name}/stop`
    (`agent_trigger.py:2120-2177`) → `check_interrupt` and `send_cancel` (`copilot_acp.py:2226-2242`)
    → `_await_prompt` (`:2742-2830`) → `_execute_rpc_run`'s `_on_event` (`agent_trigger.py:3925-3948`),
    status map and except paths → the outputs and both chat routes (`agent_chat.py:645-800`) →
    `groupIntoTurns`, `findPairedResult`, `WorkBlockDisclosure` (`AgentTimeline.tsx:559-667`) and
    `WorkRow` (`:770-870`). Also `_settle_background_runs`, the `ask_user` tool, and openspec's
    validator (`validator.js:292`) and archive (`specs-apply.js:387-389`).
  - Evidence, re-counted from the trial DB (read-only): 6 of 50 `tool_use` rows have their result in
    another work block (diagnostic splits in `run-ef33bdff4090`, `run-08d33fa23f8e`,
    `run-335903d6e932` and twice in `run-b1f5b4bedc18`; a `status` split in `run-b175c9ffa621`; all
    five runs completed). R2's count holds. No call id repeats in the DB, and no two outputs of a
    run share a timestamp.
  - Fixed:
    - **Copilot can close a cancelled call as `failed` (MEDIUM).** ACP has no cancelled tool
      status. If Copilot sends a `failed` update after the cancel, the card reads `· failed` and
      `wpc7-b`'s promise breaks for Copilot as well as Codex. D5 and `wpc7-b` now say so; task 3.2
      measures it.
    - **Duplicate results were unspecified (LOW).** The ADDED pairing rule did not say which of two
      results for one call pairs. It now says the first pairs and any later one renders on its own,
      which is today's behaviour; new scenarios "A second result for a call still renders" and
      "Pairing does not cross runs", and control test 1.15.
    - **Line citations (LOW).** `TurnBody` is `:442-557` and `WorkBlockDisclosure` `:559-667`, not
      `:442-555` and `:558-665` (proposal).
    - **No full list of endings (LOW).** D3 now has one table of every ending, whether it writes a
      status line, and how its card reads.
  - Confirmed, no change:
    - REMOVED plus ADDED is required, not a style choice: the validator and the archive both refuse
      a MODIFIED block that drops a scenario, and RENAMED plus MODIFIED would hit the same refusal.
      The REMOVED header matches `openspec/specs/agent-stream-events/spec.md:327` exactly and has a
      Reason and a Migration. The kept expansion and duration text is word for word.
    - Turn-wide pairing cannot attach a result to the wrong card: a turn is one run, and Copilot
      subagent ids are distinct (D7).
    - No ordering of real Copilot messages leaves the card dangling or gives it two results (D5).
    - Every ending without a status line is covered by D4 alone (D3's table). An `ask_user` wait
      and a budget hold are not endings.
    - Every §1 test marked failing fails on today's code; 1.3, 1.4, 1.9, 1.13 and 1.15 are
      controls. The Hub tests read the outputs route unsorted, which returns ascending
      `(timestamp, sequence, id)`. The vitest `entry()` helper builds the `TimelineEntry` shape
      the chat routes return, and `runs` uses `AgentRunFacts`.
  - Info only, not part of this change: the recent-chat route builds its list newest first and then
    sorts by timestamp alone, so two rows with the same timestamp would come out reversed. No real
    rows tie, and the closing rows are separate writes, so it cannot reorder them in practice.
  - Not resolved: Copilot's real cancel traffic (task 3.2) and Codex's close on interrupt
    (task 3.4).

## Open questions for the operator

### wpc7-a — Who closes the card: the Hub, the UI, or both?

- **(a) Hub only.** The executor persists a closing `tool_result` for each open call.
  - Every reader agrees, and the rows are self-describing.
  - Runs reconciled after a Hub death, and every historical run, keep their dangling cards.
- **(b) UI only.** `WorkRow` derives the label from the run status.
  - Covers history and reconciled runs, with no Hub change and no new payload key.
  - The DB still says the call never ended. Any other reader of `agent_outputs` (exports, a future
    trace view, a reviewing agent reading the timeline) sees an open call.
- **(c) Both. Recommended.** (a) records the fact where the Hub observed it, and (b) covers the runs
  it could not observe.
  - The extra cost is one UI branch.

**If (a):** drop D4 and UI tests 1.6-1.8 (keep 1.9 as is), and drop the second ADDED requirement.
`wpc7-d` still matters: without D4, a closing row that lands behind a notice is the card's only
way to read `interrupted`, and it can do so only if pairing crosses blocks (tests 1.10, 1.12).

**If (b):** drop D1, D2 and D5, Hub tests 1.1-1.5 and 1.10, the `status` payload key, and the first
ADDED requirement. D4's first row then never fires. `wpc7-d` still matters: D4's fallback rows are
wrong for a call whose result is in another block (D7, test 1.11).

### wpc7-b — How does a closed card read, and does it count as a failure?

- **(i) `· interrupted`, neutral colour, not counted in the "N failed" header. Recommended.** The
  operator chose to stop it, and nothing failed. Counting it would put a red `1 failed` on every
  stopped turn.
- **(ii) `· failed` / `is_error: true`.** No new payload key, and it reuses today's styling. But it
  reports the operator's own Stop as a tool failure.
- **(iii) `· stopped` for a `stopped` run and `· interrupted` otherwise.** More precise, but it
  needs the run status even when the Hub row exists. Payload `status` would carry two values.

**If (ii):** D2 sets `is_error: true` and omits `status`. D4's first row goes away. Tests 1.1 and
1.6 assert `failed`.

**If (iii):** D2's `status` takes `"stopped"` or `"interrupted"`, chosen from `outcome.status`.

Whichever is chosen, it governs only the rows the Hub writes and the UI's fallback. If real Codex
closes an interrupted command itself as `failed` (unmeasured, D5, task 3.4), that card reads
`· failed` under every answer, because the sweep finds nothing open. (R2 note; the question is
unchanged.) R3: the same holds for Copilot if it sends a `failed` update after the cancel (D5,
task 3.2). The question is still unchanged.

### wpc7-c — Close open calls on a `completed` run too?

- **(i) No, only on `stopped` and `failed`. Recommended.** A completed run with an open call is a
  mapper defect worth seeing. The UI shows it as `· no result` (D4), which is honest without
  inventing an interruption — provided "open" means no result anywhere in the turn (`wpc7-d`, D7);
  otherwise five real completed runs in the trial DB would read `· no result` wrongly.
- **(ii) Yes, on every ending, with the same `interrupted` row.** Simpler: one unconditional sweep.
  But it labels a defect as an interruption, and it would hide WPC-class mapper bugs behind a
  plausible label.

**If (ii):** D3 drops its `completed` exclusion, test 1.4 flips from control to failing, and D4's
`no result` row only ever fires for history.

### wpc7-d — How does a card find its result when a non-work row splits the block? (new, R2)

Today a result pairs with its call only inside one work block, and the current spec requires that
("Pairing does not cross blocks"). In the trial DB, 6 of 50 real calls, in 5 completed runs, have a
`diagnostic` or `status` row between the call and its result, so their cards already read
`· awaiting result` beside an orphan result row (D7). This change makes the label depend on whether
a result exists, so the rule now decides whether it is right.

- **(i) Pair across the whole turn, by call identifier. Recommended.** Each result renders at its
  call's card, a work block left empty is dropped, and D4's "no result" means none in the turn.
  Fixes the six existing cards and the closing row that lands behind a notice. Expansion state and
  duration stay per block. Needs the existing "Each work block carries independent state"
  requirement replaced (REMOVED plus a renamed ADDED), and inverts one UI test (1.14).
- **(ii) Look across the turn for the label only; keep rendering per block.** Smaller UI change.
  But the orphan result row still shows, a second time, in another block, and it bends rather than
  replaces "MUST NOT be paired with a tool use from a different block".
- **(iii) Keep per-block pairing; drop D4's fallback rows.** Only a result with
  `payload.status: "interrupted"` changes the label. No pairing change, but the stopped card in the
  WPC-7 run itself, and every reconciled or pre-change run, keep `· awaiting result`, and a closing
  row behind a notice leaves its card dangling.

**If (ii):** the replacement requirement keeps "a tool result is rendered inline only within its
block" but lets the label read the turn; tests 1.11 and 1.12 assert the label only, and 1.14 is
dropped.

**If (iii):** drop D7, D4's rows 4-5 (every unanswered call keeps today's `awaiting result`),
the REMOVED requirement and its replacement, the second ADDED requirement's fallback scenarios, and tests 1.6, 1.8,
1.11, 1.12 and 1.14. `wpc7-a` (b) and (c) then lose their main benefit.
