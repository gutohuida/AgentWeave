# Design — a secret split across two events is still scrubbed

Line numbers are at `HEAD` `4c054be` (re-derived by R2; R1 cited `10df5fc`, before slice 5
group A landed). `agent_trigger.py`, `run_secrets.py`, `runner_parsing.py`,
`codex_appserver.py` and the runner adapters did not change between the two commits, so their
numbers are the same; `copilot_acp.py`, `output_recording.py` and `runner_events.py` moved. The
uncommitted `_after_open_blocks` edit (Context) adds 7 lines at `copilot_acp.py:1233`, so every
`copilot_acp.py` citation above `:1233` below is unchanged by it and every one after it moves by
+7 once it is committed; R3 re-derives them at its own `HEAD`. Each
claim is tagged **VERIFIED-CODE** (read at the cited line) or **INFERRED** (not read, or read only
in part).

## Context

### Where the exact-value scrub runs, and whether its input can be split

| # | Call site | What it scrubs | Can one value arrive in two calls? |
|---|---|---|---|
| 1 | `output_recording.py:44-45`, `record_agent_output` | each event's `content` and `payload`, before the row (`:90`) and before the SSE broadcast (`:114-127`, the same variables) | **Yes, for `text`/`thinking`** (below). This is F488. |
| 2 | `agent_trigger.py:2216`, `_broadcast_run_lifecycle` | a lifecycle payload (`error`, `stderr_tail`, …), one dict, before `persist_event` and broadcast | No. Each field is one string from one source. |
| 3 | `agent_trigger.py:2350`, `:2669`, `:3877`, `:3959` | `Run.error`, one string | No. |
| 4 | `agent_trigger.py:3277`, `:3288-3291`, `_await_operator_permission` | the card's `tool_name`, `tool_input`, `workspace_verdict` | No. One request. |
| 5 | `agent_trigger.py:3827`, `:3834-3846`, `_on_refusal` | the `permission_denied` event's data and its broadcast's `tool_name` | No. |

All VERIFIED-CODE (R2 re-grepped `run_secrets.` across `hub/hub`: these are every call).
`register` has one caller, `agent_trigger.py:1616`, and it registers only
`env.get("COPILOT_PROVIDER_API_KEY")`; `forget` runs from the task's done callback (`:1670`).
VERIFIED-CODE. The run's two closing status rows (`:3114`, `:4074`) are written inside the task,
so before `forget`. VERIFIED-CODE.

**Which runs register a value.** VERIFIED-CODE (R2; R1 had this INFERRED): not only Copilot.
`resolve_agent_env` (`launchability.py:158-180`) starts from `dict(os.environ)` when an agent has
`env_vars`, and `agent_trigger.py:1472` falls back to `dict(os.environ)` otherwise. Claude's
`guard_env` strips only an ambient `ANTHROPIC_BASE_URL` (`runner_adapters/claude.py:138-148`) and
Codex's is the identity (`runner_adapters/codex.py:264-267`). So a Claude or Codex run registers
`COPILOT_PROVIDER_API_KEY` whenever the Hub's own environment exports it or the agent's `env_vars`
set it. Scrubbing more is the safe direction, so this is not a defect, but it makes the `exec`
executor site (task 1.4) a reachable production path, not a hypothetical one.

**Which recorders feed site 1, and how they split model text:**

- **Copilot over ACP** (`copilot_acp.py`, `CopilotEventMapper`, `on_session_update` at
  `:1019-1048`). Chunks of one kind are joined into one block. A block is emitted when the stream
  switches: a message chunk flushes the open thought (`:1031`), a thought chunk flushes the open
  message (`:1035`), and `tool_call`, `tool_call_update` and `plan` flush both (`:1042-1047`,
  `flush()` at `:1144-1146`). `finish()` flushes at prompt completion (`:1148-1155`, called at
  `:2657`), and `fail_turn` flushes before its own event (`:2106`). Inside one block nothing is
  split: chunks are joined with `""` (`:1158`, `:1163`). VERIFIED-CODE.
  **Since group A (`4c054be`):** a message chunk equal to a pending `Error: <message>` echo returns
  `[]` before `_flush_thought()` (`:1025-1030`). The echo itself is not a boundary: it flushes
  nothing and adds to neither block. VERIFIED-CODE.
  **Raw-event cards are boundaries (working tree, being committed after `4c054be`; R2 read the
  diff).** `on_raw_event` (`:1200-1238` in the tree) now wraps `session.error`,
  `session.compaction_complete` and `subagent.started|completed|failed` in `_after_open_blocks`,
  which returns `flush() + events` when the raw event produced a card and `[]` untouched when it
  produced none. So "text → error card", "thought/text → compacted card" and "text →
  subagent card" close the open block **before** the card, and the text after the card is a new
  block. A value written on both sides of a `session.error` is therefore split across text, error,
  (dropped echo), text: a new F488 boundary that the tail must span (R2 prototype rows). Raw events
  that produce nothing (`assistant.usage`, the usage checkpoint, a warning/info notice held for its
  echo, a subagent's compaction) leave the blocks open. The server-status and model diagnostics
  (`_server_status`, `_model`) are **not** wrapped: they are still emitted before the block open
  at their arrival. None of these cards is `text`/`thinking`, so none moves the tail.
  VERIFIED-CODE against the working-tree diff; R3 re-checks once it is committed.
- **Claude** (`runner_parsing.py:282-288`): each `thinking` and `text` content block of an
  assistant message is one event, whole and `.strip()`ed. **Codex `exec`**
  (`runner_parsing.py:480-489`) and **Codex app-server** (`codex_appserver.py:415-429`, emitted
  at `:1128-1129`): each completed `agent_message`/`reasoning` item is one event, stripped;
  app-server skips `item/agentMessage/delta` (`:1214-1223`). VERIFIED-CODE. So the split is a
  property of the model's own block boundaries, present on every runner.
- **Tool output.** Copilot records only the terminal `tool_call_update` (`copilot_acp.py:1100-1108`;
  partial updates are dropped), so one output is one event. Claude's `tool_result` blocks and
  Codex's completed items are whole too. VERIFIED-CODE. They can be **cut** but not split:
  `tool_result_event` truncates at 8 KiB before the scrub sees it (`runner_events.py:241-242`).
  A cut leaves a prefix in that row, and the rest is recorded nowhere. `text_event` and
  `thinking_event` cut the same way at 64 KiB (`:171-184`). Non-goal.
- **Diagnostics, errors, status rows, notices.** One string each, built from one source.
  `_classify` can split one message block around a Copilot notice (`copilot_acp.py:1167-1183`)
  into text, diagnostic, text; D1's tail joins the two text parts across the diagnostic like any
  other non-text row. VERIFIED-CODE.
- **Self-report**, `POST /agents/{name}/output` (`api/v1/agents.py:3178`, call at `:3186`), with
  an optional `run_id`. Scrubbed per post. VERIFIED-CODE. Not joined (Non-goals).
- **SSE.** VERIFIED-CODE (R2; R1 had this INFERRED): the only `agent_output` broadcast in
  `hub/hub` is `output_recording.py:114-127`, which sends the already-scrubbed `content` and
  `payload`. R2 read every `sse_manager.broadcast(` in `agent_trigger.py` (15), `checkpoint_trigger.py`
  (5) and `agent_chat.py` (1): lifecycle, queue, permission, checkpoint-policy and
  conversation-title dicts. None carries a `RunEvent`'s content.
- **Readers of stored text.** VERIFIED-CODE (R2; R1 had this INFERRED): the checkpoint transcript
  (`checkpoint_generation.py:219`), checkpoint citations (`checkpoint_access.py:81`, `:235`), the
  title excerpt (`conversation_titles.py:146`) and the timeline route (`api/v1/agent_chat.py:229`)
  read `AgentOutput.content` from stored rows. If the rows are fixed, the readers are fixed.
- **Not a recorded run event, but a leak.** `_on_armed_raw_event` (`copilot_acp.py:2113-2123`)
  logs every armed `session.error` payload as `json.dumps(data)[:2000]` to the Hub log, with no
  scrub. A provider error that quotes the key puts it there. VERIFIED-CODE. `run_turn` already
  holds the run's `env` (`:1956`), which carries `AW_RUN_ID`, so `run_secrets.scrub` can reach it
  without a new parameter. R2 recommends folding it in (D6, open question 3).

### The order the mapper emits at each boundary

VERIFIED-CODE (`copilot_acp.py:1019-1260`) and run through HEAD's mapper in R2's scratch
prototype:

| Boundary | What the call that crosses it returns | When the later block appears |
|---|---|---|
| thought → message | `[thinking(T)]`, on the first message chunk | at the next switch or `finish()` |
| message → thought | `[text(M)]`, on the first thought chunk | at the next switch or `finish()` |
| message → tool_call | `[text(M), tool_use]` (+ `tool_result` if the update is already terminal) | — |
| thought → tool_call | `[thinking(T), tool_use]` (+ `tool_result`) | — |
| any → `tool_call_update` (terminal) | `flush() + [tool_result]`; non-terminal: `flush() + []` | — |
| any → plan | `flush() + [status(plan)]` (or `+ []` for an unchanged plan) | — |
| message → finish | `[text(M)]` + unechoed warning/info notices | — |
| fail_turn | `flush()` + `[event]` | — |
| text/thought → `session.error` card | `flush() + [error]` (working tree, `_after_open_blocks`) | the next chunk opens a new block |
| text/thought → `session.compaction_complete` (root) | `flush() + [status(compacted)]` | as above |
| text/thought → `subagent.started/completed/failed` | `flush() + [status(subagent_…)]` | as above |
| echo chunk of a pending `session.error` | `[]`; nothing flushed | not a boundary |
| raw event producing nothing (usage, usage checkpoint, held notice, subagent compaction) | `[]`; nothing flushed | not a boundary |
| server-status / model raw event producing a diagnostic | `[diagnostic]`; nothing flushed | the open block appears later, after it |

Invariant: at most one of `_thought`/`_message` is non-empty, because a chunk of each kind
flushes the other, and the echo drop adds to neither. So `flush()` never emits both. Copilot's
`text` content is `.strip()`ed (`:1183`); its `thinking` content is not (`:1160` tests `.strip()`
but passes `text`). Claude's and Codex's thinking is stripped (`runner_parsing.py:283`, `:488`,
`codex_appserver.py:428`). VERIFIED-CODE. The recorded strings, which are also what the reader
sees, are what the scrub joins.

**Order and concurrency.** `emit` awaits each event in turn (`copilot_acp.py:2081-2083`), and the
reader task dispatches messages one at a time (`:1615-1635`, `_dispatch` awaited; a server request
is answered inline, `:1676-1687`). But `emit(mapper.finish())` (`:2657`) runs on the turn's own
coroutine, while the reader task can still be dispatching a late notification, so two `_on_event`
calls can interleave at their `await`. `_on_event` takes its `sequence` synchronously
(`agent_trigger.py:3764-3765`) before awaiting the write (`:3766-3781`). VERIFIED-CODE. The
timeline orders by `sequence`, so `scrub_stream` must be called **in the same synchronous step as
`sequence += 1`**, with no `await` between them; then the tail follows `sequence` order whatever
order the writes commit in. `_execute_run`'s loop (`:2836-2856`) is sequential. `pre_turn_events`
(`:3854-3855`) and the surface renderer (`:3526-3531`) reach the same `_on_event`. VERIFIED-CODE.

## Decisions

### D1 — Carry a tail across the run's recorded text, and redact across the boundary

`run_secrets` keeps, for each run with registered values, `tail`: the last `L - 1` characters of
the run's recorded `text`/`thinking` content, joined in recording order, where `L` is the length
of the longest registered value. For each new `text` or `thinking` event with content `c`:

1. `joined = tail + c`. Mark every occurrence of every registered value in `joined`, longest
   first. Inside `c` this also covers the occurrences `record_agent_output` already catches.
2. **Dangling start.** For each value `v`, find the longest `k` with `m(v) <= k < len(v)` such that
   `joined` ends with `v[:k]`. Mark those `k` characters. `m(v) = max(1, min(8, len(v) // 2))`.
3. Replace each maximal run of marked characters that lies in `c` with one `<redacted>`. Rewrite
   `content` and `payload["text"]` together (they are equal for both kinds:
   `runner_events.py:171-184`, VERIFIED-CODE). Leave `payload["truncated"]` as it is.
4. `tail = joined[-(L - 1):]`, built from the **unredacted** text, so that a value split three ways
   is still found.

Other kinds pass through unchanged and leave `tail` as it is. So the tail spans tool cards (D2),
errors, diagnostics and status rows. A run with nothing registered returns the event unchanged and
creates no state. `forget` drops the tail with the values, so the state lives exactly as long as
the run's task and holds at most `L - 1` characters per running run (the values themselves are
already held whole in `_by_run`).

Prototype (R2, scratch only, re-run independently against HEAD `4c054be`'s `CopilotEventMapper`,
value `plainproxykey123`, `m = 8`, each event then passed through today's `run_secrets.scrub`).
Each row shows the recorded content today, then with D1. R1's six rows reproduce exactly:

| Case | Rows (kind: today → D1) |
|---|---|
| thought → message | thinking: `I will use plainproxy` → `I will use <redacted>`; text: `key123 now.` → `<redacted> now.` |
| message → tool_call → message | text: `Key: plainproxy` → `Key: <redacted>`; tool_use `ls`, tool_result unchanged; text: `key123 done` → `<redacted> done` |
| message → thought, split at 5 | text: `plain` → `plain`; thinking: `proxykey123 hmm` → `<redacted> hmm` |
| message → finish, dangling | text: `the key starts plainproxyk` → `the key starts <redacted>` |
| three-way | thinking `x plain` → unchanged; text `proxy` → `<redacted>`; thinking `key123 y` → `<redacted> y` |
| false positive | thinking: `Let me explai` → unchanged (`plai` is 4 characters, below `m`); text: `n this.` → unchanged |
| (R2) whole value in one event | text `k=plainproxykey123!` → `k=<redacted>!` (today's pass already does this) |
| (R2) text → `session.error` card → echo → text (working-tree mapper) | text `a plainpro` → `a <redacted>`; error `boom` unchanged; text `xykey123 b` → `<redacted> b` |
| (R2) thought → compacted card → text | thinking `use plainproxy` → `use <redacted>`; status unchanged; text `key123 now` → `<redacted> now` |
| (R2) text → subagent_completed card → text | text `k plainproxy` → `k <redacted>`; status `explore finished` unchanged; text `key123 z` → `<redacted> z` |
| (R2) text → `assistant.usage` (no card) → text | **one** text `k plainproxykey123 z` → `k <redacted> z` (today's pass already does this) |
| (R2) 7-character leak | text `starts plainpr` → unchanged; thinking `oxykey123 end` → `<redacted> end` |
| (R2) two values, 16 and 12 chars | thinking `a plainprox` → `a <redacted>`; text `ykey123 and shortsec` → `<redacted> and <redacted>`; thinking `ret9 z` → `<redacted> z` |
| (R2) value with a self-overlapping start, `aaaaabzzzzzzzzz` | thinking `x aaaaaaaa` → unchanged; text `aabzzzzzzzzz y` → `<redacted> y` |

**The leak bound holds.** VERIFIED by prototype: per occurrence, at most `m - 1` (≤ 7) of the
value's characters stay visible, all at its start, and only when the rest arrives in later
`text`/`thinking` events. Once the visible prefix, accumulated over any number of events,
reaches `m`, the current event's part is redacted (three-way row). A remainder that arrives in a
tool row is not joined (D2) and stays as written there.

### D2 — What is joined: `text` and `thinking`, across everything else

A reader of the timeline reads a thought, a reply, and the reply after a tool card as one piece of
prose. The finding asks for both the thought→message and the message→tool_call boundaries. Since
D1 holds nothing back, joining across a tool card costs nothing. Tool inputs and outputs are not
joined. Each is one string from one source, and a value split between prose and a tool's JSON is
not a reading anyone does.

### D3 — Why nothing is held back, and the rejected alternatives

- **Hold the earlier event until the next text decides (rejected, see open question 1).** This is
  the only design under which no fragment is ever visible. It has two costs. First, the Copilot
  mapper hands a block over only when the next one closes. So a thought whose last character
  matches the first character of a key (any thought ending in `s`, for an `sk-` key) would be
  held, with every tool card behind it, until the next text block closes. That can be the length
  of a long tool run, or an operator's wait on a permission card whose context is the held text.
  Second, every exit path of both executors has to release what it is holding, or the text is
  lost. A threshold makes holds rare, but then a short dangling start is visible anyway, which is
  D1's result with extra machinery.
- **Hold back the trailing `L - 1` characters of each block and prepend them to the next (the
  finding's first suggestion; rejected).** The next block can be a different kind, so held thought
  text would be shown inside the reply. When nothing completes, the held characters have to be
  shown somewhere, either glued onto the next block or as an extra row of their own (a thought
  split into `Let me look at the file` and `s`).
- **Redact only the completing part in the later event, with no dangling-start rule (rejected).**
  It is simpler, but the earlier event keeps up to `len(v) - 1` characters of the key. The repro's
  split would still show `plainproxy`.
- **Scrub inside `CopilotEventMapper` (rejected).** The mapper would see chunk boundaries, but it
  covers one runner and needs the secret passed into it (another in-memory copy, on
  `RpcTurnRequest`). Claude and Codex have the same block boundaries, and Claude and Codex runs
  can register a value too (Context).
- **Scrub inside `record_agent_output` (rejected).** It is the one funnel, but
  `_record_observation` re-invokes the same `write` closure on `database is locked`
  (`agent_trigger.py:2257-2275`, VERIFIED-CODE: up to three attempts, delays 0.5 s and 2 s at
  `:2239`). A stateful scrub there would add the same text to `tail` up to three times and could
  match a value across an event and its own retry. Task 1.5 pins this. At the executor, a write
  dropped after its last retry (`:2265-2274`) has still advanced the tail; the only effect is that
  the next event may be redacted against text the timeline never stored, which errs toward
  hiding.
- **Scrub at read time in the timeline route (rejected).** The SSE broadcast has already gone out,
  and the stored rows still hold the halves.

### D4 — The threshold *m*

`m(v) = max(1, min(8, len(v) // 2))`. A dangling start shorter than `m` is shown. That is at most
7 characters, and less than half of a short value. A start of `m` or more characters is redacted
whatever follows. R2 measured the false positives through the prototype:

- **`sk-ant-api03-…` keys** (`m = 8`). An event ending in `sk-ant-` (7 characters) is **not**
  touched. An event ending in `sk-ant-a` or the public `sk-ant-api03-` is: `keys look like
  sk-ant-api03-` → `keys look like <redacted>`. That is prose ending on a quoted key prefix, which
  is acceptable.
- **Short values** (`m = 2` for a 4- or 5-character value). A localhost proxy may accept any key,
  and `register` keeps any non-empty value (`run_secrets.py:28-33`). With `test` registered, every
  text event ending in `te` loses it: `I will complete` → `I will comple<redacted>`. That is new
  damage at event ends only. Today's exact pass already rewrites every whole occurrence anywhere
  (`run pytest` → `run py<redacted>`), so a short value garbles the timeline with or without this
  change. A floor (`m = max(4, …)`) would trade that for showing up to 3 characters of a 4- to
  7-character value. Open question 1.

### D5 — F278's `_redaction_for` and this change do not interact

`redact_secrets` (with F278's `_redaction_for`, `runner_events.py:78-116`) is called by
`tool_use_event` (`:212`), `tool_result_event` (`:241`), `diagnostic_event` (`:302`, `:313`),
`error_event` (`:329`) and `status_event`/`error_event` facts (`_fact_values`, `:266`), and by
`scheduler.py`'s loop summaries. It is never called by `text_event` or `thinking_event`
(`:171-184`). VERIFIED-CODE at `4c054be`. D1 touches only `text` and `thinking`, so the two passes
never act on the same string. Both write the same `<redacted>` marker. R1's INFERRED residual,
checked against real key shapes (R2, VERIFIED-CODE against `_SECRET_VALUE_RE`, `:70-73`):
`sk-ant-api03-…` and `sk-proj-…` keys are matched whole by `sk-[A-Za-z0-9_=-]+`, and a 32+
character hex or base64 key whole by the entropy alternative, so the exact pass has nothing left
to miss. Only a key with a separator outside `[A-Za-z0-9+/=_-]` (a dotted JWT, say) can be cut
into pieces the exact pass no longer sees as one value, and then only in tool, diagnostic and
error rows, which D1 does not join.

### D6 — The `session.error` log line is scrubbed too (R2, recommended; open question 3)

`_on_armed_raw_event` logs `json.dumps(data, default=str)[:2000]` (`copilot_acp.py:2117-2123`).
Pass `data` through `run_secrets.scrub(env.get("AW_RUN_ID"), data)` **before** `json.dumps` and
before the `[:2000]` cut (a cut first would leave a prefix the exact match cannot see). `env` is
`run_turn`'s own parameter (`:1956`) and the trigger sets `AW_RUN_ID` (`agent_trigger.py:1474`)
before registering. One line and one `caplog` test; same guarantee family as D7 of slice 5, and
the log is where an operator pastes from when reporting a failure. If the operator declines, it
is filed as its own finding instead.

## What each caller does when `scrub_stream` raises

`scrub_stream` does `str` concatenation, `find`, `endswith` and slicing on a `RunEvent` whose
`content` is a `str` (`runner_events.py:147-168`), and copies the event with a new payload dict. It
cannot raise on that input. If it did, every path fails closed, never recording the unscrubbed
event. R2 corrected R1, which said the run always fails; it does not on Copilot's notification path
(VERIFIED-CODE):

- **Copilot, an event emitted while handling a notification** (every `session/update` and armed
  raw event, including `fail_turn`): the raise leaves `_on_event`, `emit` and `on_notification` and
  is caught at `copilot_acp.py:1670-1673`, logged as "handling copilot notification … failed".
  That event and the rest of that notification's events are dropped; the turn goes on.
- **Copilot, the hub-server-unverified diagnostic** (`:2236`) inside `answer_permission`: caught at
  `:2266`, and the permission request is answered with a rejection.
- **Copilot `finish()`** (`:2657`), **`pre_turn_events`** (`agent_trigger.py:3854-3855`) and
  **Codex app-server** (`codex_appserver.py:1129`): propagate to `_execute_rpc_run`'s
  `except (Exception, asyncio.CancelledError)` (`agent_trigger.py:4093`); the run fails.
- **`exec` (Claude, Codex `exec`)**: `_flush_line` → `_execute_run`'s except (`:3164`); the run
  fails.

The implementation must not wrap the call in a broad `except` that records the unscrubbed event
instead.

## Open questions for the operator

1. **No hold (D1, recommended), or hold; and *m*?** D1 can show up to 7 characters of a key at a
   boundary (less than half of a short one), and never delays anything. Holding shows no
   fragment, but can hide a thought and the tool cards after it until the next text closes. For
   very short registered values (a proxy's `test`), D1's dangling rule also garbles event ends
   (D4); a floor of 4 avoids that at the cost of showing up to 3 characters of such a value. R2
   recommends `m` as written, because a short value is already garbled everywhere by today's pass.
2. **Joining across tool cards (D2)**: recommended yes. It costs nothing under D1.
3. **The `session.error` log line**: R2 recommends folding it in (D6, tasks 1.7 and 2.4); the
   alternative is filing it as its own finding.
4. **Ordering with slice 5** (for information). This change adds to `agent-stream-events` and does
   not depend on slice 5's `runner-registry` delta archiving first. It does depend on `run_secrets`
   existing, and it does (committed).

## Round log

- **R1 (2026-10-04, subagent of the interactive session):** explored at `10df5fc` and proposed.
  Read all five `run_secrets.scrub` call sites, the three runners' text emission, and every
  `CopilotEventMapper` flush path. Ran D1 in a scratch prototype over the real mapper. Found two
  things outside the finding: the unscrubbed `session.error` log line, and that a Claude or Codex
  run may register an ambient key (INFERRED). Neither is fixed here. For R2: everything tagged
  INFERRED, and the working tree's group A edits once they land. Checked late in R1:
  `_execute_rpc_run` is both Copilot's executor (`agent_trigger.py:3548`) and Codex app-server's
  (`:2612-2614`, `transport.kind == "rpc"`). VERIFIED-CODE.
- **R2 (2026-10-04, subagent of the interactive session):** an independent re-derivation at
  `4c054be` (group A landed). Re-grepped every `run_secrets.` call, re-read every mapper path, and
  re-ran D1 in a fresh scratch prototype (`scratchpad/f488r2/proto.py`) over HEAD's mapper with
  five added cases. The design survives. Corrections:
  1. All `copilot_acp.py`, `output_recording.py` and `runner_events.py` line numbers re-derived
     (e.g. `on_session_update` `:965-988` → `:1019-1048`; `finish()` call `:2466` → `:2657`; the
     log line `:1922-1934` → `:2113-2123`; record scrub `:41-42` → `:44-45`; `diagnostic_event`'s
     `redact_secrets` `:283/:294` → `:302/:313`, plus `error_event` `:329` and `_fact_values` `:266`).
  2. Group A, now committed: the dropped echo chunk is not a boundary for either block (it returns
     before `_flush_thought`). Mid-round, the coordinator reported a further mapper change in the
     working tree (`_after_open_blocks`): a raw event that produces a card (`session.error`,
     root `session.compaction_complete`, `subagent.*`) now flushes the open blocks first, so each
     of those is a new boundary the tail must span; R2 read the diff and ran the three cases
     through the working-tree mapper. Server-status and model diagnostics still do not flush.
     All added to the boundary table, with `tool_call_update` and `plan` rows R1 left implicit;
     task 1.2 feeds the new boundaries.
  3. "What each caller returns when this raises" was wrong for Copilot: on the notification path a
     raise is swallowed at `copilot_acp.py:1670-1673` and the notification's events are dropped,
     not the run failed; inside `answer_permission` it rejects the request. Every path still fails
     closed. Section rewritten per path.
  4. INFERRED → VERIFIED-CODE: a Claude or Codex run does register an ambient or `env_vars`
     `COPILOT_PROVIDER_API_KEY` (`launchability.py:158-180`, `claude.py:138-148`,
     `codex.py:264-267`, `agent_trigger.py:1472`, `:1616`). Task 1.4 tests a reachable path.
  5. INFERRED → VERIFIED-CODE: no broadcast but `output_recording.py:114-127` carries model text;
     the four readers of stored text read `AgentOutput.content` (cited).
  6. New: concurrency. `finish()`'s emit and a late notification can interleave in `_on_event`;
     `scrub_stream` must be called in the same synchronous step as `sequence += 1`. Added to D1's
     context and task 2.2, with a test (1.8).
  7. New: D4's false positives measured. `sk-ant-` (7) is untouched; `sk-ant-api03-` is redacted;
     a 4-character value (`m = 2`) garbles event ends (`comple<redacted>`). Folded into open
     question 1, not changed unilaterally.
  8. D5's INFERRED residual checked against real key shapes: none for `sk-…` or 32+ character
     keys.
  9. The retry claim re-verified (`:2257-2275`, three attempts); added that a write dropped after
     its retries has still advanced the tail, which errs toward hiding.
  10. The `session.error` log line verified unscrubbed; R2 recommends folding it in as D6 (tasks
      1.7, 2.4), still the operator's call (open question 3).
