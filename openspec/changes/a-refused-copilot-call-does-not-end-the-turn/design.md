# Design — A refused Copilot call does not end the turn

## Context

### What happens on the wire

The order of one refused root call comes from two sources. **No captured ACP fixture contains a
refusal** (R2). `hub/tests/fixtures/copilot_acp/` holds only `oneshot_ok.jsonl` and
`turn_write_shell_mcp.jsonl`, and every one of the latter's nine permission requests is answered
`allow_once`. That fixture fixes steps 1-3 and the shape of the `end_turn` result. Steps 4-7 come
from Copilot's own `events.jsonl` for the three runs in the proposal (timestamps UTC, as in the
DB). For `cd02df15` (`run-b1f5b4bedc18`) the tail is `permission.completed` (denied) at 09:11:20.268,
then `tool.execution_complete` (`success: false`), then `assistant.turn_end`, then
`session.usage_checkpoint`, with no further `assistant.turn_start`. Every earlier allowed call in the
same session was followed by `turn_end` **and** a new `turn_start`. The ACP-level order of steps 4-7
has not been captured on the wire.

1. Raw `tool.execution_start`, held in `calls` by `track_call` (`copilot_acp.py:369-400`) before
   anything else.
2. `session/update` with `tool_call` pending.
3. `session/request_permission`. Its params carry `sessionId`, `toolCall{toolCallId, title, kind,
   status, rawInput}` and `options`. **There is no `agentId`**, so the request alone cannot say
   whether a subagent asked.
4. The Hub's answer, sent by `permission_answer` (`:863-875`): `{"outcome": {"outcome": "selected",
   "optionId": <reject_once>}}`.
5. Raw `permission.requested` and `permission.completed`.
6. `tool_call_update` failed, then raw `tool.execution_complete` with `{success: false, error:
   {code: "rejected", message: "The user rejected this tool call."}}`.
7. For a root call, nothing further from the model: `assistant.turn_end`, a usage checkpoint, then
   the `session/prompt` result `{"stopReason": "end_turn", "usage": {…}}`.

**The `end_turn` in step 7 is inferred, not observed (R2).** No record of these runs holds the ACP
stop reason: `events.jsonl` has no such field, `hub.log` has no per-run lines, and `runs` has no
column. It follows from Copilot's code. In 1.0.83 (the global npm package, whose ACP adapter is
readable JavaScript in `app.js`), the `session/prompt` handler returns `"end_turn"` whenever
`session.send` completes, and returns `"cancelled"` only when a `session/cancel` cleared the pending
prompt. It never returns `max_tokens`, `max_turn_requests` or `refusal`, although its type union
lists them. In 1.0.94-3 the adapter moved into `prebuilds\win32-x64\runtime.node`, which contains
`stopReason` and `end_turn` but not `max_turn_requests`, which is consistent. **Consequence:** on
Copilot the stop reason does not discriminate. After a refusal it is `end_turn`, exactly as after a
turn the agent finished. D2's refusal record is the only discriminator, and D1 is diagnostics, not
detection.

The decision to stop is made in Copilot's own runtime (the 1.0.94-3 Rust `runtime.node`). Its SDK
types say the `agentStop` hook fires only at a natural stop that "was not aborted or blocked by a
rejected tool" (`types.d.ts:1338-1345`). The Hub never sends `session/cancel` after a refusal. The
only sender is `send_cancel` (`:2226`), reached from Stop, the turn timeout and `fail_turn`. Nor
does it close stdin; `session.close()` runs in `run_turn`'s `finally` (`:2739`) after the prompt
returns.

R2 read the 1.0.83 adapter directly. Its permission mapper turns `reject_once` and `reject_always`
into `{kind: "reject"}` with no `feedback`, and ACP's selected outcome carries only `optionId`, so
the protocol has no field a reason could travel in. Copilot then logs the refusal as
`denied-interactively-by-user`: to Copilot's runtime it is an interactive user's Deny. Its
behaviour for that is to stop and wait for the user's next instruction. The follow-up prompt of D3
is that instruction.

### Subagents differ

A refusal answered for a call **inside** Copilot's `task` tool ends only the subagent. Copilot then
completes the root `task` call ("Agent completed but produced no response.") and the parent model
carries on (`run-b175c9ffa621`, session `c5e3a780`). The subagent's raw events carry the envelope
`agentId` and `data.parentToolCallId`. The mapper already tells them apart with `_is_subagent(params,
data)` (`:928`). `CallFacts` (`:346-362`) does not record it, and `track_call` is handed `data` only.

### What the turn returns today

`_await_prompt` (`:2742-2837`) works out the status in this order:
1. `forced_failure`;
2. `interrupted` or `cancelled`, both reported as `interrupted`;
3. `failure`, which is a raise or a timeout;
4. `root_error`;
5. `ledger.refused`, a quota refusal;
6. `completed`.

The status order needs no change. `stop_reason` is read at `:2808` only to test for `cancelled`.

The usage ledger keeps the last `session/prompt` result's `usage` (`copilot_usage.py:291-293`: "last
result in the process wins"). Its preferred figure is the per-call sum, and premium requests come
from the session-cumulative checkpoint. Both already span every prompt in the turn (D5). So does
the prompt result itself (R3): its `usage` is cumulative within the process (VERIFIED-LOCAL in
`2026-10-02-a-copilot-run-shows-its-credits` design, table row 22 and D3 "Cumulative"), and a
continuation runs in the same process. Last-wins is therefore already right for a continued turn.

`mapper.finish()` (`:1190`) flushes buffered text, emits pending notices, and emits the review-agents
report once. Calling it before a continuation would split the timeline and send the report early.

### What already reaches the operator

- The judge's refusal: a `permission_denied` event (`decided_by: "runtime"`) through `on_refusal`.
- The operator's Deny: the card's own row.
- A task run that ended without finishing its task: a divergence from `evaluate_run_end`
  (`agent_trigger.py:4214`), seen for `run-b1f5b4bedc18`.
- A chat run: nothing. Its last visible row is the refused tool card, then "Run completed (exit 0)."

### Claude, the parity target

`approve_tool_call` denies with `{"behavior": "deny", "message": "Denied: <reason>."}`
(`mcp_server.py:3757`). The model receives the reason as the tool result and continues in the same
turn. The same is true of a Claude operator Deny. Copilot cannot be given a reason inside the refused
call. The nearest equivalent the Hub controls is the next prompt.

R2 confirmed this from code only: there is no `interrupt` flag on the deny, and `_ask_operator`'s
refusal returns a reason too. It was not re-driven live. Codex does not share the bug either.
`codex_appserver.py:17-22` records a live check in which `{"decision": "decline"}` gave "no file, no
protocol error, and a normal turn continuation", and `_FAILED_ITEM_STATUSES` includes `"declined"`.
The change is therefore correctly Copilot-only.

## Decisions

### D1 — The stop reason is logged and recorded on every Copilot turn

`_await_prompt` logs `stopReason` at info, with the run id and the prompt's ordinal (first or
continuation). `TurnOutcome` gains `stop_reason: Optional[str] = None`, holding the **last** prompt's
reason. A new helper, `_runtime_turn_fields(outcome)` in `agent_trigger.py`, returns
`{"stop_reason": …, "ended_on_refusal": …, "refusal_continuations": …}`. It omits keys that are
`None`, zero or `False`, as `_runtime_failure_fields` (`:2288`) omits its own. It is merged into
every terminal lifecycle broadcast and into the closing status row's payload. The helper lives in
the executor tail that Copilot and Codex share, so it works from facts any runner may lack.

*Rejected: a `Run.stop_reason` column.* That needs a migration, and nothing queries it yet. The
payload is persisted with the event and the row.
*Rejected: logging only.* `hub.log` rotates, and the drive needed the reason in the DB to answer
"why did this run end".

**R2: what D1 is for, and what it breaks.** On Copilot the value is always `end_turn` or
`cancelled` (Context), so D1 tells the operator only that the runtime returned normally. It is
diagnostics, not detection. It has one cost R1 did not count. `TurnOutcome` is a `@dataclass`
compared by value, and `hub/tests/test_copilot_acp_run_turn.py` asserts
`outcome == TurnOutcome(session_id=…, status=…, error=None)` 14 times (two of them `interrupted`).
Each one whose
prompt returns a result will now see `stop_reason="end_turn"` and fail. Update them to name the
field (task 1.12). Do **not** declare the field `compare=False`: that would hide it from every
equality test.

### D2 — "Ended on a refusal" is detected from the Hub's own answers, not guessed from silence

- **Recording.** In `answer_permission` (`:2376`), when the answer is a refusal, `state["last_refusal"]`
  is set to `{tool_call_id, label, reason, decided_by}`. Here `decided_by` is `"hub"` (judge, posture
  rule, spec-turn rule) or `"operator"` (a card denied). The operator path today collects no reason.
  Its reason is the fixed "the operator did not approve it", or the operator's typed reason if the
  card ever carries one.
  **R3:** `request_approval` (`agent_trigger.py:3398`, `_await_operator_permission`) returns one
  `bool`. It is `False` for a Deny, for an expired card and for a timed-out wait alike, so the Hub
  cannot say "denied" truthfully. The wording is therefore neutral ("did not approve"), not
  "denied". When `request_approval` is `None`, `answer_permission` refuses with
  `asked_operator=True` although no card was shown. That refusal is recorded with
  `decided_by="hub"` and the reason "no operator channel", not as the operator's.
- **Parent or subagent.** A refusal is recorded only for a parent-level call. That is read from
  `calls[tool_call_id]`. `CallFacts` gains `subagent: bool`, set by `track_call` from
  `data.parentToolCallId` or, once `track_call` is passed the envelope, `params.agentId`, the same
  test `_is_subagent` makes. A call with no start in `calls` counts as **parent**. That is safe: the
  ACP wire order puts the start first (the `ACPProcess` docstring, `:1638`), and a missing start
  would at worst give a continuation that was not needed.
- **Clearing.** The record is cleared by later root activity, on the wire after the answer: any
  `agent_message_chunk`, or a root raw `tool.execution_start` whose id differs. The refused call's
  own `tool_call_update` and `tool.execution_complete` do not clear it. Subagent activity does not
  clear it either, since it cannot follow a root refusal in the same prompt.
  **"Last", exactly (R3).** `ACPProcess`'s read loop (`:1741-1800`) dispatches each line inline, in
  wire order, and awaits each handler. The prompt result resolves `prompt_task` from the same loop,
  so every line before the result line has been handled when `_await_prompt` sees the result. "Last"
  means last in that wire order, before the result. Exactly two things clear the record:
  - a root `agent_message_chunk` the mapper **keeps**:   `_chunk_text` not blank after
      `strip()` (`_classify` drops a blank message), and not a `session.error` echo dropped by
      `_error_echoes`. An echo or a blank chunk is not the agent answering;
  - a root raw `tool.execution_start` whose `toolCallId` differs from the record's.

  Nothing else clears it: not `agent_thought_chunk`, `plan` or `usage_update`, not the refused
  call's own updates, and not any line after the result (handled concurrently with the decision, so
  never considered). Consequences:
  - **Several refusals in one prompt**: each overwrites the record. The continuation names only the
    last one, which is the one that ended the turn.
  - **Parallel root calls**: A is refused, B started before the answer and completed after it, and
    then `end_turn`. B's start came before A's answer, so it does not clear. D2 fires, which is
    right: the agent was told nothing about A.
  - **A refusal, then an allowed root call, then `end_turn`**: the allowed call's start clears the
    record. No follow-up is sent.
  - **The agent acknowledged the refusal in text and stopped**: its chunk clears the record, and no
    follow-up is sent. This is the spec delta's scenario "A refusal the agent answered is not
    continued". It cannot fire on such a turn.
  - **A subagent's refused call**: never recorded (`subagent` flag), so it can neither set nor
    replace a root record.
- **Acting.** The turn acts only when all of these hold: the prompt returned `stopReason ==
  "end_turn"`, the record is set, and none of `interrupted`, `cancel_sent`, `forced_failure`,
  `failure`, `root_error` or `ledger.refused` is set.

*Rejected: "the turn produced no text".* A turn may write text and then make the refused call. The
signal is what came last, not whether text exists.
*Rejected: reading the raw `assistant.turn_end`.* It is not in `COPILOT_RAW_EVENTS` (`:97-120`), it
fires for every turn, and the Hub cannot read a reason from it.
*Rejected: classifying from the permission request.* It carries no `agentId`.

### D3 — Option (a): one bounded continuation prompt in the same session

When D2 fires, and the operator chose (a) or (c), the Hub sends a follow-up `session/prompt` in the
same ACP session. Its text block, in the Hub's voice:

> The Hub refused your last tool call (`<label>`): <reason>. It did not run. Continue the task
> another way, or call ask_user if you cannot.

For an operator refusal, the first sentence is "The operator did not approve your last tool call
(`<label>`)." (R3: not "denied"; see D2.)

- **Bound.** `REFUSAL_CONTINUATIONS_PER_TURN = 1` (`wpc1-c`). The record from the first prompt is
  cleared before the continuation is sent. If the continuation also ends on a refusal, no further
  prompt is sent, and D4's diagnostic says why.
- **Time.** The continuation uses whatever is left of the turn's `turn_timeout` deadline, not a new
  one. On expiry it sends `session/cancel` exactly as the first prompt does.
- **Stop.** `check_interrupt()` runs before sending. Nothing is sent if the turn is interrupted, if
  a cancel was already sent, or if the turn has a forced failure. A Stop during the continuation is
  handled by the existing poll loop: `session/cancel`, then `interrupted`.
- **Shape.** `_await_prompt` is split into `_send_and_wait(blocks, deadline)`, which returns the raw
  result and its failure, and one tail. The tail runs `ledger.observe_prompt_result` for each prompt,
  then `mapper.finish()` **once**, after the last prompt, then the existing status order. The
  timeline therefore reads as one turn: the refused card, a continuation notice (D4), then the
  agent's reply.
- **What feeds the tail (R3).** "The existing status order" must not read the continuation's own
  transport failure, or D7's "the first outcome stands" is contradicted: a continuation timeout
  would set `failure` and the tail would return `failed`. So:
  - The continuation's `failure` (raise, process exit, timeout) does **not** feed the status. It
    becomes `copilot.refusal_continuation_failed` (D7), subject to `wpc1-h`.
  - It **does** feed `close_forced`. The continuation's `cancel_sent_at`, or a `None` prompt
    result, force-closes the session exactly as on the first prompt. A shell the continuation
    started may still be running, and a graceful close would wait on it.
  - `interrupted`, `forced_failure`, `root_error` and `ledger.refused` set during the continuation
    **do** feed the status, as for any prompt. A Stop, an escalation, a root `session.error` or a
    quota refusal during the continuation is a real outcome of the turn.
  - `stop_reason` is the last prompt's that returned a result.
- **Order of events (R3).** First prompt's lines handled in wire order → result line resolves
  `prompt_task` → the poll loop of `_await_prompt` sees it → `ledger.observe_prompt_result` →
  the D2 gate (stop reason, record, flags) → `check_interrupt()` → diagnostic → clear record →
  second `session/prompt` → its lines → its result → the tail: `finish()` once, status, return →
  `run_turn`'s `finally` closes the session → only then the executor tail (`agent_trigger.py:4214`):
  `evaluate_run_end`, the terminal lifecycle broadcast, the closing status row. What can interleave:
  - **Stop** (`agent_trigger.py:2155-2163`): polled by `check_interrupt` after every armed
    notification, after each `answer_permission`, every `POLL_SECONDS` in the wait, and once more
    at the gate. A Stop that lands after the last poll and before the result is today lost: the
    turn returns `completed`. Under D3 the gate's `check_interrupt()` catches it: it sends
    `session/cancel`, sets `interrupted`, and nothing is sent. The outcome is `interrupted`,
    force-closed. That is a behaviour change on refused turns only, and it is the right one.
  - **A Stop while the operator's card is pending**: `answer_permission` is awaiting the card, the
    read loop is blocked, and the poll still runs `check_interrupt`, which sends `session/cancel`.
    The card resolves `False` later and the record is set, but `interrupted` gates D2. No
    continuation.
  - **Hub shutdown** (`main.py:487-489`): `terminate_all_active_runs()` first adds every running run
    to `_stop_requested`, then `_settle_background_runs()` cancels the run's task. The first step
    is seen as a Stop by the next poll. The second raises `CancelledError` into `run_turn` at
    whatever `await` it is in: inside either prompt's wait, at the gate, or in a diagnostic `emit`.
    `CancelledError` is a `BaseException`. It is **not** absorbed by D7, it propagates exactly as
    it does during the first prompt today, `run_turn`'s `finally` still closes the session, and
    `_execute_rpc_run` marks the run failed and re-raises (its comments). No continuation is sent
    after it, `copilot.refusal_continuation_failed` is not emitted for it, and `mapper.finish()`
    does not run on it, as today.
  - **ask_user**: see "No second actor" below.
  - **A cost or budget pause**: there is none. Nothing but the Stop route and
    `terminate_all_active_runs` adds to `_stop_requested`, and no budget check runs inside
    `run_turn`. The continuation's premium request is counted after the fact (D5).
- **Visibility.** Before sending, the turn emits an info diagnostic `copilot.refusal_continued`,
  naming the call and the reason, so the operator sees why the agent went on (`wpc1-e`).
- **No second actor (R2).** The continuation runs inside the same `run_turn`, the same ACP session
  and the same `Run`. Nothing else can act on the run while it is in flight:
  - `evaluate_run_end` is called only after `start_turn` returns (`agent_trigger.py:4214`). It sees
    the run once, after the continuation. If the continuation finished the task,
    `run_advanced_its_task` holds and no divergence is raised.
  - The divergence policies act only from `evaluate_run_end`. `surface`, the default, starts
    nothing. `retry` and `escalate` queue one response run through `_queue_response` and
    `schedule_agent` (`run_divergence.py:917-920`). `schedule_agent` refuses while the agent has a
    `running` run (`turn_scheduler.py:313-318`), so any queued input waits for this run to end.
  - **There is no "dropped task" sweeper.** `run-b1f5b4bedc18`'s divergence `div-d3199cf88f80` was
    `policy=surface`, `outcome=surfaced`, and started nothing. The next run on that task,
    `run-87919e9b45ca`, delivered a **new operator message** (`entry-61faf255cfd8`, 09:12:38, in a
    new conversation `conv-1111f5224059`, `divergence_source_run_id` NULL). So the task cannot run
    twice from one refusal: once by the continuation and once by a sweeper.
  - A Stop that lands between `check_interrupt()` and the send is seen by the next poll of the
    continuation's own wait. That poll sends `session/cancel` and yields `interrupted`, exactly as
    for a Stop during the first prompt. A Stop is never lost, only acted on up to `POLL_SECONDS`
    later.
  - A pending blocking `ask_user` cannot coexist with D2 firing. The question is a root MCP tool
    call, so its start clears any earlier record, and a blocking question waits inside that call,
    not at the turn's end. If the turn ends with the question unanswered, `evaluate_run_end` parks
    the task on it as today.
  - **A non-blocking `ask_user` (R3)** (`mcp_server.py:452`, `blocking=False`) returns at once, so
    its question can still be pending when a later root call is refused and D2 fires. The
    continuation is then sent with the question open. That is acceptable: the agent can poll
    `get_answer`, and the continuation tells it to ask, not to stop asking. Nothing in the gate
    reads pending questions, and it should not.

*Rejected: feedback inside the refusal.* ACP's `reject_once`, `reject_always` and `cancelled` all
reach Copilot as a reject with no feedback. Copilot 1.0.83's adapter ignores `_meta`, and the native
1.0.94 runtime exposes no ACP field for it.
*Rejected: a Copilot `agentStop` or `permissionRequest` hook.* That is forbidden by *No Copilot hook
decides a call or a turn*, and Copilot runs `agentStop` precisely **not** after a rejected tool.
*Rejected: Copilot's native autopilot continuation (1.0.94).* The Hub could neither bound it nor
give it the reason, and it changes how every turn ends, not only refused ones.
*Rejected: leaving the turn and putting the reason in the next queued input.* A chat run has no next
input, and the task run's divergence path already does the equivalent, but late.

### D4 — Option (b): a turn that a refusal ended says so

When D2 fires and no continuation is sent, the turn emits a warning diagnostic
`copilot.turn_ended_on_refusal`. Reasons not to send: the operator chose (b) only, the bound was
reached, or the continuation could not be built. The diagnostic carries `{tool_call_id, label,
reason, decided_by, continuations}`. `TurnOutcome.ended_on_refusal = True` and D1's helper puts it
on the lifecycle payload. The run's status stays `completed`: the agent did not fail, and
`failed` would page the operator for a decision that worked as designed.

For a task run, `evaluate_run_end` already raises the divergence. It gains the refusal as context,
so its surfaced message says "the turn ended on a refused call: <label> — <reason>" rather than only
that the task was dropped. `evaluate_run_end(run_id)` reads the refusal from the run's own record;
its signature does not change.
**R3: which record.** R1 said "the run's last `permission_denied` event". That is the wrong gate:
- `_on_refusal` (`agent_trigger.py:3965`) persists `permission_denied` only for **Hub** refusals,
  subagent ones included. An operator's refusal is a `PermissionRequest` row, not that event, so it
  would be missed.
- A run whose last refusal the agent answered, or whose continuation succeeded, or whose last
  refusal was a subagent's, still has a `permission_denied` event, and would be described as ended
  on a refusal when it was not.
- `evaluate_run_end` is shared with Claude and Codex runs, which also persist refusals.

So it reads the D4 fact instead: the run's own `copilot.turn_ended_on_refusal` or
`copilot.refusal_continuation_failed` diagnostic, which carries the label and reason. With neither,
the message is today's. It cannot read `ended_on_refusal` off the lifecycle payload: the terminal
broadcast comes **after** `evaluate_run_end` (`agent_trigger.py:4214-4245`). The diagnostic is
written during the turn, as an output row with the run's id, through `_on_event`
(`agent_trigger.py:3924-3945`), so it is already there.

*Rejected: marking the run `failed` or a new status.* It would be a new value in every consumer of
run status, and the refusal is not a failure.
*Rejected: setting the task to `revision_needed`.* That is a reviewer's verdict, and the divergence
policy already owns what happens to a dropped task.

### D5 — Option (c): both, and the accounting

(c) is D3 with D4 as its fall-through. The premium request a continuation costs is real and is
counted:
- The turn's `turn_usage` row already comes from the session checkpoint difference, so it includes
  the continuation without change.
- There is one `CopilotUsageLedger` per `run_turn` (`copilot_usage.py:184-185`), so its per-call
  sum (`_calls_sample`) already spans both prompts. `_finish` (`:329-351`) prefers that sum unless
  the prompt-result total is larger.
- `observe_prompt_result` (`:291-293`) keeps only the last prompt's `usage`. **R3: that is already
  correct, and it does not change.** R1 said the fallback "would count the continuation alone" and
  proposed summing. But the prompt result's `usage` is cumulative within the process, and the
  continuation runs in the same process (Context; the credits change's VERIFIED-LOCAL row 22: "two
  later slash prompts returned the same totals"; its D3: "the later cumulative result would already
  include the earlier one. So the ledger keeps the later result and never adds the two together").
  Summing would count the first prompt twice. Worse, `_finish` (`:329-351`) takes the larger of the
  per-call sum and the prompt-result total, so the doubled result would beat a correct per-call sum
  on **every** continued turn, not only on the fallback. Task 1.13 becomes a control that pins
  last-wins, and 2.C.4 is dropped. Live check 3.1 compares the continuation's prompt-result total
  with the per-call sum, since the cumulative behaviour across two **model** prompts in one process
  is inferred from slash prompts, not measured.
- Premium requests come from the session-cumulative `session.usage_checkpoint`, settled by
  `settle_copilot_credits`, so they include the continuation without change.
- `refusal_continuations` on the lifecycle payload lets the spend view say which requests were
  continuations.

How that count is *shown* belongs to `copilot-spend-is-counted-in-its-own-units`. This change only
guarantees the number is not lost.

### D6 — The "no backstop" requirement gains a bounded carve-out

*No Copilot hook decides a call or a turn* (`agent-run-sandboxing`) says a forced continuation is a
backstop the design deliberately has none of, and that "a turn that ends without asking has ended".
A continuation under D3 is not a hook, but it does make a turn continue. The requirement is modified
(spec delta) to say that a turn Copilot's runtime ended because a refusal with no feedback blocked
it was not ended by the agent. It also allows the Hub's own bounded follow-up prompt, which carries
the refusal's reason. The ban on hooks, on trusting the workspace, and on continuing a turn the agent
ended for any other reason is unchanged. **This is contingent on `wpc1-f`.** If the operator picks
(b) only, the MODIFIED block is dropped from the delta before the change is archived.

**How this differs from the retired backstop (R2).** CLAUDE.md says operator-in-the-loop "has
deliberately no backstop", and migration `0082` dropped the detector that read a turn's trailing
prose and guessed whether it was a question. The carve-out is a different kind of thing, on three
counts:
- **What it reads.** The detector read the agent's own text and judged its intent. D2 never reads
  text. It fires on a fact the Hub itself recorded: the Hub's or the operator's `reject_once` was
  the last root event before the prompt returned. This is the "structured state, never prose"
  principle that `note_turn_that_produced_nothing` (`run_divergence.py:630`) already follows.
- **Whose decision it overrides.** The detector second-guessed a turn the agent ended. Here the
  agent did not end the turn. Copilot's runtime stopped it because of the Hub's own answer, which
  the protocol stripped of its reason.
- **What it says.** The detector asked the agent to go on. The continuation delivers the one fact
  that was lost, the reason, and leaves the choice to the agent, including `ask_user`. It runs at
  most once.

A turn that ends with a question in prose, and no refusal, is still over. A turn that ends after a
refusal and then agent text is also still over (D2's clearing rule).

### D7 — What each call returns or does when what it calls raises

| Call | Raises / fails | Result |
|---|---|---|
| Continuation `session/prompt` (`_send_and_wait`) | `CopilotACPError`, `AppServerError`, process exit, `asyncio.TimeoutError` | The **first** prompt's completed outcome stands. A warning diagnostic `copilot.refusal_continuation_failed` and a log line are emitted, `ended_on_refusal = True`, and `refusal_continuations = 1`. The run is not turned `failed` by a step the Hub added. **R3:** this failure does not feed the status (D3, "What feeds the tail"), but it does feed `close_forced`, so the session is force-closed. Whether this still holds once the continuation has produced output is `wpc1-h`. |
| Continuation result carries a quota error | `ledger.refused` is set | Unchanged rule: the turn fails as quota-refused. That is real and the operator must see it. Quota means `errorType == "quota"` and `errorCode == "quota_exceeded"` in the error's `data` (`copilot_usage.py`, `_observe_error`); any other `data` is the first row. |
| A root `session.error` during the continuation (R3) | `mapper.root_error` set | `failed`, as for any prompt (status order step 4). Not the first row: a root error is the runtime's own report, not the Hub's step failing. |
| Hub shutdown or task cancellation during the continuation, at the gate, or in a diagnostic `emit` (R3) | `asyncio.CancelledError` (a `BaseException`) | **Not absorbed.** It propagates out of `run_turn` exactly as during the first prompt today. `run_turn`'s `finally` closes the session, `_execute_rpc_run` marks the run failed and re-raises. No continuation is sent after it, no `copilot.refusal_continuation_failed` is emitted, and `mapper.finish()` does not run. Every `except` the change adds catches `Exception`, never `BaseException`. |
| Continuation hits the turn deadline | timeout | `session/cancel` as today, then as the row above. |
| Building the continuation text (label or reason missing or odd) | any `Exception` | Suppressed. No continuation is sent, and D4's `copilot.turn_ended_on_refusal` is emitted. |
| `emit(diagnostic)` for D3 or D4 | raises | Under `contextlib.suppress(Exception)`, like the other turn-level diagnostics. It never changes the outcome. |
| Stop between the prompts | `interrupted` set | Nothing is sent. The outcome is `interrupted`. **R3:** this includes a Stop that landed after the first prompt's last poll and before its result, which today yields `completed`. The gate's `check_interrupt()` sends `session/cancel`, so the session is force-closed. |
| `mapper.finish()` (R3) | — | Runs exactly once on every path that **returns** an outcome: completed, a failed continuation, interrupted, forced failure, root error, quota. It runs zero times on `CancelledError`, as today. It never runs between the prompts. |
| `_runtime_turn_fields` on `run_stopped` (R3) | — | Reached. The terminal `_broadcast_run_lifecycle` call (`agent_trigger.py:4229`) is shared by `run_completed`, `run_stopped` and `run_failed`, so an interrupted Copilot turn carries its `stop_reason` (`"cancelled"`, or none if the prompt never returned). |
| `on_refusal` / `on_decision` | raise | Already suppressed (`:2397-2424`). The refusal record in `state` is written before them, so it survives. |
| `_runtime_turn_fields` | outcome lacks the attributes (Codex) | `getattr(..., None)`, so the keys are omitted. It never raises. R3 checked Codex's `TurnOutcome` (`codex_appserver.py`): `thread_id`, `status`, `error`, `exit_code`, `stderr_tail`. None of the three names, so a Codex payload is unchanged. Claude's PTY/pipe path passes no `TurnOutcome` there. |
| `evaluate_run_end` reading the refusal | DB error | It keeps its current behaviour: the divergence is raised without the refusal context. |
| Continuation `session/prompt` raises anything else (R2) | any other `Exception` | The same as the first row. `_await_prompt` already turns an unexpected exception into a failure (`:2791-2795`, "an unexpected error"), and the continuation does the same. **Test consequence:** the fake raises `AssertionError("script exhausted …")` on an unscripted `session/prompt`, and that is absorbed too. So a pinned test that meets an unscripted continuation does **not** go red. It goes on passing with a `copilot.refusal_continuation_failed` diagnostic and a warning log. Task 1.12 must therefore update each such test deliberately; it cannot rely on a failure to find them. |

## Risks / Trade-offs

- **The continuation costs money.** It is one more premium request times the multiplier, once per
  refused-and-ended turn. A tight bound (1) keeps it predictable, and the operator decides
  (`wpc1-d`).
- **The operator's Deny may mean "stop".** Continuing after it is Claude parity, but an operator
  who denies to end the turn would need Stop. See `wpc1-b`.
- **Clearing on text is conservative.** A turn that says "I'll try something else" and then stops is
  treated as not ended on a refusal. That case was not observed, and it would still be honest output.
- **Copilot may change.** If a later Copilot continues after a rejected tool by itself, D2 never
  fires, because an `agent_message_chunk` clears the record, and nothing breaks.
- **Tests that pin today's behaviour** script a reject then `_END_TURN` with nothing after. Under (a)
  they meet a second `session/prompt` their fake cannot answer. Each needs a scripted second
  response, or a judgement that it tests something else (tasks 1.12).
- **WPC-2's false positives** made one of the three observations. Fixing the judge reduces how often
  this fires, but does not remove the need: real refusals end the turn too.

## Round log

- **R1 (2026-10-12)**:
  - Traced every path after a reject. The Hub sends no cancel and does not close stdin; the end is
    Copilot-native.
  - Read the three runs in the DB and Copilot's `events.jsonl`. The stop reason is `end_turn`.
    *(R2: inferred from Copilot's code, not read from any record; see Context.)*
  - Found the subagent and parent split, and that the request carries no `agentId`.
  - Found that the task run was surfaced as a divergence, and that `observe_prompt_result` is
    last-wins.
  - Found the conflict with *No Copilot hook decides a call or a turn*.
- **R2 (2026-10-12, work PC)**: an independent re-derivation from the code, the trial DB, Copilot's
  `events.jsonl` for `cd02df15`, `af71334e` and `c5e3a780`, and the Copilot 1.0.83 `app.js` and
  1.0.94-3 `runtime.node`. **The argument holds, and Copilot ends the turn.** The Hub sends no cancel
  after a reject: `send_cancel` is reached only from Stop, the timeout and `fail_turn`, and
  `answer_permission` calls only suppressed callbacks. Corrections:
  - **Medium.** The fixture cited for the refused wire order has no refusal; all nine of its
    requests are allowed. Steps 4-7 rest on `events.jsonl`, and the ACP order of those steps is
    uncaptured. Fixed in Context and in tasks 1 / 1.12.
  - **Medium.** The pinned list in 1.12 missed
    `test_full_access_never_sets_allow_all_and_judges_execute_as_workspace` (`:1666`). It also
    missed that D1 alone breaks up to 14 `outcome == TurnOutcome(...)` assertions, and that
    unscripted continuations are absorbed by D7, so the pinned tests stay green rather than going
    red. Fixed in D1, D7 and 1.12.
  - **Low-medium.** "The stop reason is `end_turn`" was never observed. It is inferred from
    Copilot's adapter, which returns `end_turn` for every normal completion, so the stop reason
    cannot discriminate. D2's record is the only discriminator. Fixed in Context and D1;
    `wpc1-g` added.
  - **Low.** The proposal said `run-87919e9b45ca` "continued the task". It was a new operator
    message in a new conversation; the `surface` divergence started nothing, and no sweeper
    exists. Fixed in the proposal and in D3.
  - **Added.** The race analysis in D3 (same run, `evaluate_run_end` after the turn, one running
    run per agent, Stop polled); the no-backstop distinction in D6; the Codex evidence beside
    Claude's; Copilot's `denied-interactively-by-user` semantics; the `wpc1-b` counterpoint.
  - **Confirmed.** No path after a reject cancels, closes or kills. The subagent refusal in
    `c5e3a780` ended only the subagent, and a later root refusal ended the turn. The SDK cites are
    valid for 1.0.94-3 (`types.d.ts:1337-1345`, `:975`). The six pinned tests R1 named exist at
    the stated lines.
- **R3 (2026-10-12, work PC)**: a fresh comparison against the code at `6208e9a5`
  (`copilot_acp.py` `ACPProcess` read loop `:1741-1800`, `answer_permission`, `_await_prompt`,
  `run_turn`'s `finally`; `agent_trigger.py` Stop `:2155-2204`, `_await_operator_permission` `:3398`,
  `_on_refusal` `:3965`, `_on_event` `:3924`, executor tail `:4094-4262`; `main.py:487-489`;
  `copilot_usage.py`; `mcp_server.py` `approve_tool_call`, `_ask_operator`, `ask_user`; the fake ACP
  harness). **The core argument holds.** Corrections:
  - **High.** D5's ledger change was wrong. The prompt result's `usage` is cumulative within the
    process (VERIFIED-LOCAL in the credits change), and the continuation is in the same process, so
    summing double-counts the first prompt. `_finish` takes the larger total, so the doubled figure
    would win on every continued turn. Last-wins stays. 2.C.4 is dropped and 1.13 is a control.
    `wpc1-d` is reworded and the proposal is corrected.
  - **Medium.** Hub shutdown: `CancelledError` was not covered. D7 now says it is not absorbed,
    propagates as today, and runs no `finish()`. A test (1.15) and a scenario were added.
  - **Medium.** D3's "existing status order" contradicted D7: a continuation timeout would have
    returned `failed`. D3 now says what feeds the tail: transport failure feeds `close_forced` and
    not the status, while Stop, escalation, root error and quota do feed it. 1.9 and 1.10 assert a
    forced close, and a root-error row and variant were added.
  - **Medium, new open question `wpc1-h`.** Is a continuation that fails *after* producing output
    still `completed`?
  - **Low-medium.** The operator wording was false for an expired or timed-out card, because
    `request_approval` returns one bool. It is now "did not approve". With no operator channel,
    `decided_by` is `"hub"`.
  - **Low-medium.** D4/2.D.2 gated on "the last `permission_denied` event". That misses operator
    refusals and misfires on runs that answered or continued, and on Claude and Codex. It now reads
    the D4 diagnostic row.
  - **Low.** The Stop race: a Stop after the last poll and before the result yields `completed`
    today, and `interrupted` under D3. Specified, and test 1.14 was added.
  - **Low.** "Last" is now defined exactly against the wire order (D2): kept (non-blank) chunks only;
    parallel calls; several refusals; acknowledge-and-stop never fires. Test 1.16 (parallel calls)
    and 1.5's variants (a question in text; a blank chunk) were added.
  - **Added.** The order of events and what can interleave (D3). A non-blocking `ask_user` can be
    pending while a continuation is sent. There is no budget pause. Spec scenarios were added for
    the Stop race, a shutdown during the follow-up, a turn that ends on a question (no follow-up),
    and a session error during the follow-up. The carve-out now states that the agent's text never
    decides whether a turn continues.
  - **Confirmed.**
    - The carve-out fires only on a structured, Hub-recorded answer, at most once, and never reads
      prose.
    - No continuation can follow `cancel_sent`.
    - `_runtime_turn_fields` is reached on `run_stopped` and cannot change a Codex payload (its
      `TurnOutcome` has none of the names).
    - Claude's deny is `{"behavior":"deny","message":…}` with no interrupt flag (code only; not
      driven).
    - The tests in §1 fail today, except the marked controls (1.13 is now one). 1.15 fails today
      only because no continuation is sent; it guards the implementation. The ACP order of steps
      4-5 is still uncaptured.

## Open questions for the operator

### wpc1-a — Which fix: continue, make visible, or both?

Options: (a) continue only; (b) visible only; (c) both.
**Recommend (c).** (a) alone still ends silently once the bound is reached. (b) alone leaves a
Copilot agent less capable than a Claude one in the same posture, and the operator would have to
re-prompt by hand after every judge refusal.
*If (a):* drop D4's diagnostic and the `ended_on_refusal` field, keeping D1.
*If (b):* drop D3 and the MODIFIED requirement, keeping D1 and D4.

### wpc1-b — Does an operator Deny continue too?

Options: continue with "The operator did not approve …" (Claude parity; R3: not "denied", which an
expired or timed-out card would make false); end the turn as today, but visibly
(D4); or add a second card button, "Deny and stop".
**Recommend continue now, and consider "Deny and stop" later.** Claude continues after a Deny, and an
operator who wants the turn over already has Stop.
*Counterpoint (R2, changed):* Copilot records the Hub's reject as `denied-interactively-by-user`.
Copilot's own behaviour for a human's Deny is to stop and wait for that human's next instruction,
so for the operator path today's ending matches Copilot's native intent. It goes wrong only because
the Hub's card offers no next-instruction box in the same run. The recommendation stands, for
Claude parity, but this makes "end the turn, visibly" a reasonable choice for operator Denies.
*Otherwise:* D2 records only `decided_by == "hub"` refusals, and test 1.3 becomes a control.

### wpc1-c — How many continuations per turn?

Options: 1, 2, or a per-agent setting.
**Recommend 1.** Each is billable, and an agent refused twice in a row is better handed to the
operator (D4) than retried.
*Otherwise:* change the constant. Test 1.8's bound moves with it.

### wpc1-d — How is the continuation counted?

Options: on the same turn's usage row; a separate usage row; or not billed in the Hub's view.
**Recommend the same row, with `refusal_continuations` on the payload.** The per-call sum, the
process-cumulative prompt result and the session checkpoint already include the continuation, so
nothing is added together by hand (R3: D5's summing was wrong and is dropped).
*Otherwise:* a separate row needs `copilot-spend-is-counted-in-its-own-units` to add one, and
splitting the cumulative figures moves there.

### wpc1-e — How visible is a continuation?

Options: a timeline diagnostic only; a diagnostic plus a banner on the run; nothing.
**Recommend the diagnostic only.** It sits beside the refused card, and a banner is louder than an
expected recovery needs.
*Otherwise:* a banner is a UI task and needs the UI bundle refresh.

### wpc1-f — May the "no backstop" rule be relaxed for this one case?

Options: yes, with the bounded carve-out in the spec delta; or no, which means (b) only.
**Recommend yes.** The rule exists so that an agent that chose to stop is not pushed on. Here the
agent did not choose: Copilot stopped it because the Hub's refusal could carry no reason. The
carve-out keeps hooks banned and is bounded to the Hub's own refused call.
*Otherwise:* `wpc1-a` is forced to (b).

### wpc1-g — Keep D1's `stop_reason` on the payload? (new, R2)

On Copilot the stop reason is always `end_turn`, or `cancelled` after a Stop or timeout (Context).
It cannot tell a finished turn from a refused one, so D1 adds a field that, today, never varies.
Options: keep it on the lifecycle payload and log it; log it only; drop D1.
**Recommend keep it, as R1 proposed.** It is cheap, needs no migration, and is the only record
that would show a future Copilot starting to return `max_turn_requests` or `refusal`. The cost is
updating up to 14 `TurnOutcome` equality assertions (D1).
*If log only:* drop `TurnOutcome.stop_reason` and test 1.11's `stop_reason` key; tests 1.1 and
2.A.2 keep only the log line.
*If drop:* remove D1, the first ADDED requirement, 1.1 and 2.A.

### wpc1-h — A continuation that fails after it produced output (new, R3)

D7 keeps the first prompt's `completed` when the continuation fails. That is right when the
continuation failed before it did anything: the turn is what it was. It is less clearly right when
the continuation had already streamed text or run tools, then timed out or lost its process. The
run would then be `completed` with half a reply, while the same failure on a first prompt is
`failed`. A root `session.error` or a quota refusal in the continuation already gives `failed`
(D7), so the rule is asymmetric either way.
Options: (1) always keep the first outcome (R1/R2's rule); (2) keep it only if the continuation
produced no output (no kept `agent_message_chunk`, no root `tool.execution_start`), and otherwise
fail as any prompt does; (3) always fail.
**Recommend (2).** Before output, the Hub's own step failing should not fail the run. After output,
the turn is the agent's again, and a transport failure in it is a real failure the operator must
see.
*If (1):* no change. *If (2):* `_send_and_wait` reports whether it produced output, D7's first row
splits, and test 1.9 gains an after-output variant expecting `failed`. *If (3):* D7's first row
becomes `failed`, and the spec scenario "A follow-up that fails leaves the turn as it was" is
rewritten.
