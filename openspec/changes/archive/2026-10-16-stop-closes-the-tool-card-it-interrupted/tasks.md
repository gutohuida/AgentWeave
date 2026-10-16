## 0. Rounds and decision

- [x] 0.1 R2 — an independent trace, starting from the producers rather than from this proposal.
  **Done 2026-10-12 on the work PC.** Findings are in the design's round log; in short:
  - **Codex:** the interrupt loop keeps mapping notifications until `turn/completed`
    (`codex_appserver.py:1094-1102`, `:1197-1215`); `CommandExecutionStatus` has no interrupted
    value. Whether Codex sends `item/completed` for an in-flight command on interrupt is
    **unmeasured** (the only test, `test_codex_appserver_run_turn.py:846-875`, sends none). Task
    3.4 measures it; test 1.5 keeps a Codex case shaped like that test.
  - **Claude (PTY):** `_record_events` (`agent_trigger.py:2892-2918`) is the only output writer;
    the reader loop ends (`:3019-3029`) before `pty.wait`, the status map (`:3064-3071`) and the
    status row (`:3266-3280`).
  - **Raises:** an early raise from `start_turn` goes to the except at `:4033-4078` and any later
    raise to the outer except at `:4277` (`_record_run_failure_tail`, `:2431`). Neither writes the
    status row nor reaches the sweep. Copilot's `run_turn` raises only before `_await_prompt`
    (`copilot_acp.py:2723`), so no call is open then. D4 covers the rest. Task 2.2 no longer says
    "or raises".
  - **Shutdown:** `terminate_all_active_runs` (`:2182`) only flags; `_settle_background_runs`
    (`main.py:369-410`) cancels the task, which ends `failed` through the outer except with no
    status row and no sweep. A crash is reconciled to `interrupted`
    (`run_reconciliation.py:77-82`). D4 covers both.
  - **Side tables:** nothing in `hub/hub/` acts on `kind == "tool_result"`; `outside_writes` reads
    only `write_paths`. No effect.
  - **Live UI:** the chat query is invalidated in `hub/ui/src/api/agentChat.ts` (on `agent_output`
    and the four terminal run events), not in `useSSE.ts`. Confirmed.
  - **New:** a result in a different work block (design D7, question `wpc7-d`).
- [x] 0.2 R3 — a fresh comparison from the operator's side, not a re-read of R2. Start at the Stop
  button in `AgentOutputPanel.tsx`, follow the request through `stop_agent_run`
  (`agent_trigger.py:2121`) to the cancel in `copilot_acp.py` (`send_cancel` `:2226`,
  `_await_prompt` `:2742`), back out through `_execute_rpc_run`, and into `WorkRow`
  (`AgentTimeline.tsx:770-870`) on both the live path and a reload. The question to break: is there
  any ordering of real Copilot messages (a terminal `tool_call_update` after `session/cancel`, a
  prompt answer before it, the grace expiring) under which the card still dangles, or gets two
  results? Check that each test in section 1 drives a sequence the real producer emits. Run
  `npx openspec validate stop-closes-the-tool-card-it-interrupted --strict`.
  **Done 2026-10-12 on the work PC.** Findings are in the design's round log; in short:
  - **No ordering dangles or doubles.** An update before the prompt answer becomes the call's one
    result; after the answer or the grace, the session is closed and the sweep closes the call (D5).
  - **But Copilot may say `failed`.** ACP has no cancelled tool status, so a post-cancel `failed`
    update reads `· failed` and breaks `wpc7-b`'s promise for Copilot too. Task 3.2 measures it.
  - **6 of 50 re-counted and confirmed.** Turn-wide pairing cannot reach the wrong card: a turn is
    one run, and subagent ids are distinct. The spec now says the first result pairs and a later
    duplicate renders on its own (test 1.15).
  - **Every ending listed** in D3's table; each one without a status line is covered by D4 alone.
  - **REMOVED plus ADDED is required** by the validator and the archive; the header, Reason and
    Migration are correct.
  - **Section 1 checked.** Every test marked failing fails today, the Hub tests use the route's
    order, and the vitest fixtures match `TimelineEntry` and `AgentRunFacts`.
  - Citation fixed: `WorkBlockDisclosure` is `:559-667`.
- [ ] 0.3 The operator answers `wpc7-a`, `wpc7-b`, `wpc7-c` and `wpc7-d` in `spec-queue/DECISIONS.md`.
  Apply the design's "If …" consequences before writing any test.

## 1. Tests first — each must fail on today's code unless marked as a control

Hub tests go in a new file, `hub/tests/test_stop_closes_open_tool_calls.py`. They drive the real
executor through the trigger route, the way `hub/tests/test_a_turn_says_how_it_ended.py:411-444`
and `hub/tests/test_a_refused_turn_holds_the_queue.py:659-680` do: patch the transport's `run_turn`
with a fake that feeds the executor's own `on_session`/`on_event` callbacks, then returns the
transport's `TurnOutcome`. Read rows back through the outputs route
(`GET /agents/{agent}/output`, `agents.py:3530`, which returns them ascending by `timestamp`,
`sequence`, `id`) and assert on the list **in the order the route returns it — never re-sorted**, so
an assertion fails if the route's order is reversed.

UI tests feed entries in the order the chat route returns them (`agent_chat.py:714`, ascending), and
each asserts something that order decides: the closed card renders above the `Run stopped` line.

The sequence each fake replays is the one the real producer emits, and its source is named:

- **Copilot.** The `tool_use` is what `CopilotACPMapper._tool_call` (`copilot_acp.py:1113`) makes of
  the captured shell `tool_call` at `hub/tests/fixtures/copilot_acp/turn_write_shell_mcp.jsonl`
  line 48 (`kind: "execute"`, `status: "pending"`, `rawInput.command`). The outcome is
  `TurnOutcome(status="interrupted")`, which `run_turn` returns after `stopReason: "cancelled"`
  (the existing `test_copilot_acp_run_turn.py:1171`). Nothing in between: the drive's run
  `run-e183cc3e1acd` recorded exactly `thinking`, `tool_use`, `status` (sequence 1-3). Other real
  endings do put rows in between: `finish()` (`copilot_acp.py:1190`) flushes buffered `text` and
  emits a `diagnostic` per unechoed notice, and a session error is an `error` row (design D3). Test
  1.10 covers that.

- [ ] 1.1 **Copilot, stopped mid-call.** The fake emits a `thinking` event, then the shell
  `tool_use` (call id `toolu_01Ky1xyEL7aTrBkrR3fyKsZX`, command `Start-Sleep -Seconds 240; echo
  done`, taken from the DB row), then returns `interrupted`. Assert:
  - the run is `stopped`;
  - the rows, in the order the outputs route returns them, are `thinking`, `tool_use`,
    `tool_result`, `status`. Today's code
    writes `thinking`, `tool_use`, `status`, which is the DB's sequence, so this fails;
  - the `tool_result` has the same `call_id` and `tool`, `payload.status == "interrupted"`,
    `payload.is_error is False`, `payload.version == 1`;
  - the `status` row is still last and still reads `Run stopped (exit 1).`
- [ ] 1.2 **Copilot, failed mid-call.** The same sequence, but the fake returns
  `TurnOutcome(status="failed", error="timed out")`, which is what `_await_prompt` returns when the
  deadline cancel (`copilot_acp.py:2773-2775`) gets no answer. Assert the run is `failed` and the
  same closing `tool_result` sits before the status row. A second case emits an `error` row (a
  Copilot session error, as the mapper records it) after the `tool_use` and before returning
  `failed`; assert the order `tool_use`, `error`, `tool_result`, `status`.
- [ ] 1.3 **Control: a call Copilot closed itself is not closed twice.** The fake emits the
  `tool_use`, then the `tool_result` the mapper makes of the captured terminal `tool_call_update`
  for the same call (`turn_write_shell_mcp.jsonl` line 67, `status: "completed"`), then returns
  `interrupted`. ACP allows updates after `session/cancel` and before the prompt answers; which
  terminal status Copilot actually sends after a cancel is unknown until task 3.2. Assert exactly
  one `tool_result` for the call id, and it is Copilot's. Passes today; must still pass.
- [ ] 1.4 **Control: a completed run is not closed** (per `wpc7-c`, recommended). The fake emits the
  `tool_use` and returns `completed`. Assert no `tool_result` row. Passes today; must still pass.
  If the operator picks `wpc7-c` (ii), this becomes a failing test asserting the closing row.
- [ ] 1.5 **The PTY path, stopped mid-call.** Seeded with `_stoppable_pty`
  (`hub/tests/test_agent_trigger.py`) after one stream-json `assistant` line carrying a `tool_use`
  block, as Claude prints it (the shape in `runner_parsing.py`'s parser tests). Stop through the
  route, as `test_a_turn_says_how_it_ended.py:331-367` does. Assert a closing `tool_result` before
  the `Run stopped (exit 15).` row. Add the Codex app-server case too, through `_fake_run_turn`
  emitting a `commandExecution` `tool_use` and returning `interrupted` with no `item/completed`,
  the sequence the only existing interrupt test feeds (`test_codex_appserver_run_turn.py:846-875`).
  Whether real Codex sends an `item/completed` first is unmeasured (task 3.4); if it does, the case
  becomes a control asserting no second result.
- [ ] 1.6 **UI: an unanswered call in a stopped run reads "interrupted".** In
  `hub/ui/src/__tests__/agentTimeline.test.tsx`, render the DB's three rows for one run (`thinking`,
  `tool_use`, `status` "Run stopped (exit 1)."), in that order, with
  `runs={{ 'run-e183cc3e1acd': { status: 'stopped', … } }}`. Open the work block. Assert
  `interrupted` is shown and `awaiting result` is not. Fails today.
- [ ] 1.7 **UI: a closing row reads "interrupted" and is not a failure.** The same rows plus the
  closing `tool_result` (`payload.status: 'interrupted'`, `is_error: false`) before the status row.
  Assert `interrupted`, and that the work-block header shows no `failed` count
  (`AgentTimeline.tsx:601`). Fails today: it reads `completed`.
- [ ] 1.8 **UI: an unanswered call in a completed run reads "no result".** One `tool_use` with no
  result, run status `completed`. Assert `no result`. Fails today.
- [ ] 1.9 **Control: no run facts still reads "awaiting result".** A new test: one `tool_use` with no
  result anywhere in the turn, `runs={{}}`. Assert `awaiting result`. Passes today; must still
  pass. (R1 pointed at `agentTimeline.test.tsx:846-865` for this. R2: that test is
  "does not pair a tool_use with a tool_result across a block boundary"; its call *has* a result,
  in the next block, and under `wpc7-d` (i) it inverts, see 1.14.)
- [ ] 1.10 **Hub: a row between the call and the stop.** The Copilot fake emits the `tool_use`, then
  a `diagnostic` notice (what `finish()` emits for an unechoed `session.info`), then returns
  `interrupted`. Assert the order `tool_use`, `diagnostic`, `tool_result` (interrupted), `status`.
  Fails today.
- [ ] 1.11 **UI: a result in another work block pairs with its call** (per `wpc7-d` (i)). Render the
  completed run `run-08d33fa23f8e`'s rows 3-10 from the trial DB, in route order: `thinking`,
  `tool_use` `edit` (call `toolu_01MBqBcf45VUUwbngy4NitsX`), `diagnostic` (the file-created
  notice), `tool_result` for that call, then the `shell` pair, `text`, `status`, with the run
  `completed`. Assert the `edit` card reads `completed`, not `awaiting result` or `no result`, and
  the result is not rendered a second time as its own row. Fails today (`awaiting result` plus an
  orphan row).
- [ ] 1.12 **UI: the closing row lands after a notice.** Rows `thinking`, `tool_use`, `diagnostic`,
  closing `tool_result` (`payload.status: 'interrupted'`), `status` "Run stopped (exit 1).", run
  `stopped`. Assert one card reading `interrupted`, no separate result row, and no `failed` count.
  Fails today.
- [ ] 1.13 **Control: a result whose call is not in the turn still renders.** A `tool_result` with
  no matching `tool_use` in its turn still shows as its own row. Passes today; must still pass.
- [ ] 1.14 **Invert the existing cross-block test** (per `wpc7-d` (i)).
  `agentTimeline.test.tsx:846-865` pins today's per-block pairing: `tool_use` `c1`, a `text` row,
  `tool_result` `c1`, and asserts the card reads `awaiting result`. Rewrite it to assert the card
  reads `completed` and the result is not shown again as its own row. Under `wpc7-d` (iii) leave it
  as it is.
- [ ] 1.15 **Control: a second result for one call renders on its own** (R3). One `tool_use` `c1`,
  then two `tool_result` rows for `c1` (the first `completed`, the second `is_error: true`), run
  `completed`. Assert the card reads `completed` and the second result shows as its own row. This
  is what a Copilot `tool_call` carrying a terminal status followed by a terminal update would
  record. Passes today; must still pass once pairing spans the turn. Add a second case with two runs
  that each record a `tool_use` `c1`, where only the first run has a result: the second run's card
  must not read `completed`.

Existing tests that pin today's behaviour and were checked: `test_a_turn_says_how_it_ended.py`'s
stopped and failed cases filter to status rows (`_completion_rows`), so an added `tool_result` does
not break them. `test_copilot_acp_run_turn.py`'s cancel tests assert `run_turn`'s own events, which
D1 does not change. R2 read them and did not run them; IMPL confirms with a full
`pytest hub/tests/ -q`. In the UI, only the cross-block test (1.14) changes. R3: the Copilot Hub
tests need a fake that calls `kwargs["on_event"]`; `_fake_rpc_turn`
(`test_a_refused_turn_holds_the_queue.py:659`) does not, while `_fake_run_turn`
(`test_agent_trigger.py:111`) does.

## 2. Implementation

- [ ] 2.1 `hub/hub/runner_events.py`: let `tool_result_event` (`:233-253`) take an optional
  `status`, written to the payload only when given, with summary `"<tool> interrupted"` for
  `status="interrupted"`.
- [ ] 2.2 `_execute_rpc_run`: track open call ids in `_on_event` (`agent_trigger.py:3925-3948`).
  After `start_turn` returns a `TurnOutcome` that maps to `stopped` or `failed` (`:4097-4105`),
  record one closing row per open call through `_on_event`, after the status map and before the
  `async with` that commits the `Run` row (`:4115`), so the status row (`:4254-4269`) stays last
  and `run_stopped` is broadcast only after the rows exist. A raise from `start_turn` does not
  reach this point (design D1); do not add a sweep to the except paths. Catch and log any exception
  from one closing write, so it can neither drop the others nor turn the run `failed`.
- [ ] 2.3 `_execute_run`: the same around `_record_events` (`:2892-2918`), between its status map
  (`:3064-3071`) and its `Run` commit (`:3079`).
- [ ] 2.4 `AgentTimeline.tsx`: thread the run status from `runStatus` (`:281`) through `TurnBody`
  and `WorkBlockDisclosure` to `WorkRow`, and replace the suffix (`:802-808`) with D4's table.
  Per `wpc7-d` (i), resolve pairing across the turn: compute the turn's result for each call id
  once (`findPairedResult`, `agentTimelineModel.ts:79`, already takes a list), render each result
  at its call's card, hide it where it would otherwise stand alone, and drop a work block left
  empty. Count a block's failures over the results it renders (`:601`); a
  `payload.status === 'interrupted'` result is not one (already true, since it carries
  `is_error: false`).
- [ ] 2.5 Rebuild the UI bundle (`make ui` or `scripts/refresh_ui_bundle.py`) and commit
  `hub/ui/src` and `hub/hub/static/ui` together; `diff -rq hub/ui/dist hub/hub/static/ui` is clean.
- [ ] 2.6 Sync the delta into `openspec/specs/agent-stream-events/spec.md` on archive.
- [ ] 2.7 Run `pytest hub/tests/ -q`, `cd hub/ui; npx vitest run`, `npx tsc --noEmit`,
  `npm run lint`, `ruff check hub/`, `black --check hub/hub/ hub/tests/`, and
  `npx openspec validate --specs --strict`.

## 3. Live verification

- [ ] 3.1 On the work PC, on a trial Hub started from source on `:8010` (never `:8000`), with a real
  Copilot agent (GHCP licence): send a prompt that runs `Start-Sleep -Seconds 240; echo done` in
  the shell, and press Stop while it sleeps. In the trial DB (read-only), for that run:
  - `runs.status = 'stopped'`;
  - `agent_outputs` ordered by `sequence`: `tool_use`, then a `tool_result` with the same
    `call_id` and `payload.status = 'interrupted'`, then the `status` row last;
  - exactly one `tool_result` per call id.
  In the dashboard, the card reads `interrupted` live, and again after a page reload.
- [ ] 3.2 Capture the raw ACP traffic of that cancel (the `session/update` notifications after
  `session/cancel`, and the prompt response with its `stopReason`) into
  `hub/tests/fixtures/copilot_acp/turn_cancel_shell.jsonl`. Replace test 1.1's assembled sequence
  with a replay of it, and record in the round log whether Copilot sent a terminal
  `tool_call_update` after the cancel. If it did, the mapper already closes the card and WPC-7 has
  a second cause; re-open D1. If that update says `failed`, the card reads `· failed` (D5, R3);
  take that back to `wpc7-b`.
- [ ] 3.3 Open a run from before this change (`run-e183cc3e1acd` on the work-PC trial DB, served by
  an upgraded trial Hub). Its card reads `interrupted` from D4 alone. Open `run-08d33fa23f8e` too:
  its `edit` card reads `completed`, with no orphan result row (D7).
- [ ] 3.4 Codex interrupt capture. With a real Codex app-server agent, stop a turn while a
  `commandExecution` is running, and capture the notifications between `turn/interrupt` and
  `turn/completed`. Record in the round log whether an `item/completed` arrives for the item and
  with what `status`. If it arrives as `failed`, the card reads `failed` and the sweep adds
  nothing; take that back to `wpc7-b`. Update test 1.5's Codex case to replay the capture.
