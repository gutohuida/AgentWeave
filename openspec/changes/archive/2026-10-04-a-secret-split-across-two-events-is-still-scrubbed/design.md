# Design — a secret split across two events is still scrubbed

Line numbers are at `HEAD` `13f7421` (re-derived by R3, after `d08c2f5` committed
`_after_open_blocks`). R2 cited `4c054be`; R1 cited `10df5fc`. Between `4c054be` and `13f7421` only
`copilot_acp.py` moved, by +7 after `:1233`; `agent_trigger.py`, `run_secrets.py`,
`output_recording.py`, `runner_events.py`, `runner_parsing.py` and `codex_appserver.py` did not, so
their numbers are R2's. Each claim is tagged **VERIFIED-CODE** (read at the cited line) or
**INFERRED** (not read, or read only in part).

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
  `:2664`), and `fail_turn` flushes before its own event (`:2113`). Inside one block nothing is
  split: chunks are joined with `""` (`:1158`, `:1163`). VERIFIED-CODE.
  **Since group A (`4c054be`):** a message chunk equal to a pending `Error: <message>` echo returns
  `[]` before `_flush_thought()` (`:1025-1030`). The echo itself is not a boundary: it flushes
  nothing and adds to neither block. VERIFIED-CODE.
  **Raw-event cards are boundaries (committed in `d08c2f5`; R2 read the diff, R3 re-read the
  committed code).** `on_raw_event` (`:1200-1231`, `_after_open_blocks` at `:1233-1238`) wraps `session.error`,
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
  VERIFIED-CODE at `13f7421` (R3 ran the three card cases through the committed mapper).
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
- **Not a recorded run event, but a leak.** `_on_armed_raw_event` (`copilot_acp.py:2116`, the
  log call at `:2124-2130`) logs every armed `session.error` payload as `json.dumps(data)[:2000]`
  to the Hub log, with no scrub. A provider error that quotes the key puts it there.
  VERIFIED-CODE. `run_turn` (`:1960`) already holds the run's `env` (its parameter at `:1963`,
  passed as `RpcTurnRequest.env`, `agent_trigger.py:3480`), which carries `AW_RUN_ID`, so
  `run_secrets.scrub` can reach it without a new parameter. R2 recommends folding it in (D6, open
  question 3).
- **One-shots** (checkpoint, handover, title). They register nothing (`register` has one caller)
  and record no run events, so they are not on this change's path. Their input is the stored rows,
  which this change fixes. VERIFIED-CODE (R3).
- **Whitespace at an event boundary (R3).** Copilot's `thinking` content is not stripped
  (`copilot_acp.py:1157-1160`), so a thought block can end or begin with whitespace the reader
  cannot see. Claude's and Codex's text and thinking, and Copilot's text, are stripped. The two
  recorded Copilot fixtures (`hub/tests/fixtures/copilot_acp/*.jsonl`, 4 text/thinking rows) had
  none at a block edge, so it is not observed, but nothing prevents it: their thought chunks carry
  `\n\n` inside a block. D1 skips it (below). VERIFIED-CODE.

### The order the mapper emits at each boundary

VERIFIED-CODE (`copilot_acp.py:1019-1267`) and run through HEAD's mapper in R2's and R3's scratch
prototypes:

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
| text/thought → `session.error` card | `flush() + [error]` (`_after_open_blocks`, `d08c2f5`) | the next chunk opens a new block |
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

**Order and concurrency.** `emit` awaits each event in turn (`copilot_acp.py:2088-2090`), and the
reader task dispatches messages one at a time (`_read_loop`, `:1622-1648`, `_dispatch` awaited at
`:1642`; a server request is answered inline, `:1682-1693`). But `emit(mapper.finish())` (`:2664`) runs on the turn's own
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

1. `joined = tail + c.lstrip()`: whitespace at the start of `c` is skipped (R3; see step 4 for
   the end of the previous event). Mark every occurrence of every registered value in `joined`,
   longest first. Inside `c` this also covers the occurrences `record_agent_output` already
   catches.
2. **Dangling start.** For each value `v`, find the longest `k` with `m(v) <= k < len(v)` such that
   `joined.rstrip()` ends with `v[:k]`. Mark those `k` characters. `m(v) = max(1, min(8, len(v) // 2))`.
3. Replace each maximal run of marked characters that lies in `c` with one `<redacted>`, keeping
   `c`'s skipped leading whitespace and any trailing whitespace as written. Rewrite
   `content` and `payload["text"]` together (they are equal for both kinds:
   `runner_events.py:171-184`, VERIFIED-CODE). Leave `payload["truncated"]` as it is.
4. `tail = joined.rstrip()[-(L - 1):]`, built from the **unredacted** text, so that a value split
   three ways is still found, and with trailing whitespace removed, so that whitespace at an event
   boundary never breaks a join.

**Why whitespace at a boundary is skipped (R3).** The reader cannot see it: a thought row ending in
`plainproxy\n\n` and a reply row starting `key123` read as the key. Copilot does not strip its
`thinking` content (Context), so without the skip such a pair is not joined and neither the
completion nor the dangling start is found, and the whole value stays visible. R3 measured it:
with a newline appended at random event ends, D1 without the skip left up to the whole value
visible (16 of 16 characters of `plainproxykey123`, 29 of 29 of an `sk-ant-api03-` key) in about
4% of random splits; with the skip, at most `m - 1`, always a prefix. Whitespace inside an event is
not skipped: a value split by a space inside one event is a non-goal, as before.

**The cost of the skip (review).** A registered value that itself **contains** whitespace is not
joined when an event boundary falls on that whitespace: with `plain proxykey123` registered,
`use plain ` + `proxykey123 now` is joined as `use plainproxykey123 now`, which does not contain
the value, and both rows are stored as written (measured, `scratchpad/f488rev/adv.py`). Split
anywhere else (`plainpr` + `oxy key123`) it is caught. API keys contain no whitespace, and the
only value registered today is `COPILOT_PROVIDER_API_KEY`, so this is a stated non-goal (proposal,
spec), not a fix.

Other kinds pass through unchanged and leave `tail` as it is. So the tail spans tool cards (D2),
errors, diagnostics and status rows. A run with nothing registered returns the event unchanged and
creates no state. `forget` drops the tail with the values, so the state lives exactly as long as
the run's task and holds at most `L - 1` characters per running run (the values themselves are
already held whole in `_by_run`).

**Tail lifetime across runs (review).** The tail is per run and in-process. A conversation's next
run (a resumed Copilot or Claude session, a queued follow-up) has a new `run_id`, registers again
and starts with an empty tail, and a Hub restart drops every tail with `_by_run`. So a value split
between the last text of one run and the first text of the next is not joined, although the
timeline shows the two rows together. A model turn does not end mid-token and resume it in the next
turn in any observed transcript; the residual is named, not fixed. A late `scrub_stream` call after
`forget` finds nothing registered and creates no state (R3).

Prototype (R2, scratch only, re-run independently against HEAD `4c054be`'s `CopilotEventMapper`,
value `plainproxykey123`, `m = 8`, each event then passed through today's `run_secrets.scrub`).
Each row shows the recorded content today, then with D1. R1's six rows reproduce exactly. R3
re-implemented D1 from this text (`scratchpad/f488r3/proto.py`) and ran it over `13f7421`'s mapper:
every R1/R2 row below reproduces, the card rows through the committed `_after_open_blocks`:

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
| (R3) thought ending in whitespace → message | thinking `I will use plainproxy\n\n` → `I will use <redacted>\n\n`; text `key123 now.` → `<redacted> now.` (without the skip: both unchanged, the whole key visible) |
| (R3) message → thought starting with whitespace | text `Key: plainpr` → unchanged; thinking `\n oxykey123 hmm` → `\n <redacted> hmm` (without the skip: unchanged) |

**The leak bound holds.** VERIFIED by prototype: per occurrence, at most `m - 1` (≤ 7) of the
value's characters stay visible, all at its start, and only when the rest arrives in later
`text`/`thinking` events. R3 re-measured it with its own implementation
(`scratchpad/f488r3/bound.py`, 40 000 random splits into up to six `text`/`thinking` events with
tool rows between, per value set): the worst case was exactly `m - 1` for `plainproxykey123` (7), an
`sk-ant-api03-` key (7), `test` and `abcde` (1), `aaaaabzzzzzzzzz` (6) and a 16+12 pair (7), and
the visible part was a prefix in every trial; with boundary whitespace inserted, the same only
with step 1's skip (above). Once the visible prefix, accumulated over any number of events,
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
- **Other over-redaction (review), all cosmetic and toward hiding.** Prose ending on a key's public
  prefix of `m` or more characters loses it: with an `sk-proj-…` key registered, `OpenAI keys start
  with sk-proj-` → `OpenAI keys start with <redacted>` (8 characters, `m = 8`). A self-overlapping
  value can mark characters past its own end: with `abababababababab` registered, a text
  `x abababababababab` then `ab yes` stores `x <redacted>` and `<redacted> yes`, because an
  occurrence shifted by two crosses into the next event. Neither shows any of the value; both
  remove a few characters of ordinary text. Measured, `scratchpad/f488rev/adv.py`.

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

### D6 — The `session.error` log line is scrubbed too (R2; open question 3, DECIDED: folded in)

`_on_armed_raw_event` logs `json.dumps(data, default=str)[:2000]` (`copilot_acp.py:2124-2130`).
Pass `data` through `run_secrets.scrub(env.get("AW_RUN_ID"), data)` **before** `json.dumps` and
before the `[:2000]` cut (a cut first would leave a prefix the exact match cannot see). `env` is
`run_turn`'s own parameter (`:1963`) and the trigger sets `AW_RUN_ID` (`agent_trigger.py:1474`)
before registering.

**If that scrub raised (R3).** It cannot on `data`, which is JSON-decoded (`dict`, `list`, `str`,
numbers, `bool`, `None`; `_scrub` handles each). But the log call sits *before*
`mapper.on_raw_event` (`:2135`), so a raise there would leave `on_notification` and be swallowed at
`:1679`, dropping the `session.error` card, the echo registration and `mapper.root_error` with it:
the turn could then end `completed` though Copilot reported an error. So the scrub-and-log is the
one place where a raise must not propagate: on a raise the line is logged **without** its payload
(`payload=<unavailable>`), never with the unscrubbed one, and the raw event goes on to the mapper.
This is a log line, not a record, so the rule below against a broad `except` does not apply to it. One line and one `caplog` test; same guarantee family as D7 of slice 5, and
the log is where an operator pastes from when reporting a failure. If the operator declines, it
is filed as its own finding instead.

### D7 — `register` strips each value (review)

`register` keeps each value exactly as resolved (`run_secrets.py:24-29`, VERIFIED-CODE: `{value
for value in values if value}`, no strip). A key pasted into an agent's `env_vars` or the Hub's
environment with a trailing newline or space (`plainproxykey123\n`) is registered with it, and the
model, which writes the key without it, is never matched: `use plainproxykey123 now` passes `scrub`
unchanged today, and passes D1 too (measured, `scratchpad/f488rev/adv.py`). Whether the child CLI
strips the value before using it is INFERRED; it does not matter, since the model's text is what
the scrub reads. So `register` keeps `value.strip()` for each value, and the raw value as well when
it differs (it can still appear as written, in a lifecycle `stderr_tail` say), and drops a value
that strips to empty (a whitespace-only value would otherwise replace every run of spaces). The
longest-first order and `L` are computed over the kept set. One line in `register`; test 1.1's strip
row.

### Non-goals and residuals (design-side; the proposal's Non-goals list them too)

- **A value containing whitespace, split at that whitespace** (D1, *The cost of the skip*).
- **A value split across two runs** (D1, *Tail lifetime across runs*).
- **Inside one event**: Codex app-server joins a reasoning item's summary and content parts with a
  space (`codex_appserver.py:426-428`, VERIFIED-CODE), so a value split across two parts reads as
  `plainproxy key123` inside one `thinking` event. That is a fragment inside an event, not at a
  boundary, and stays out of scope.
- **Content an agent writes through the Hub's MCP tools.** `send_message`, `ask_user`, task
  updates, checkpoint notes, evidence and spec documents are stored by their own routes
  (`api/v1/agent_actions.py`, `tasks.py`, `spec.py`, …), none of which calls `run_secrets`
  (VERIFIED-CODE: `run_secrets` is imported only by `output_recording.py` and `agent_trigger.py`).
  An agent that pastes its key into a message or a spec document stores it whole. That is not a
  split, and not this change; it is filed as its own finding.

## What each caller does when `scrub_stream` raises

`scrub_stream` does `str` concatenation, `find`, `endswith` and slicing on a `RunEvent` whose
`content` is a `str` (`runner_events.py:147-168`), and copies the event with a new payload dict. It
cannot raise on that input. If it did, every path fails closed, never recording the unscrubbed
event. R2 corrected R1, which said the run always fails; it does not on Copilot's notification path
(VERIFIED-CODE):

- **Copilot, an event emitted while handling a notification** (every `session/update` and armed
  raw event, including `fail_turn`, whose two callers are in `_on_armed_raw_event`, `:2150`,
  `:2158`): the raise leaves `_on_event`, `emit` and `on_notification` and is caught at
  `copilot_acp.py:1676-1680`, logged as "handling copilot notification … failed". That event and
  the rest of that notification's events are dropped; the mapper has already flushed the block, so
  the dropped text is gone, not recorded later. The turn goes on.
- **Copilot, the hub-server-unverified diagnostic** (`:2243`) inside `answer_permission`: caught at
  `:2273`, and the permission request is answered with a rejection.
- **Copilot `finish()`** (`:2664`), **`pre_turn_events`** (`agent_trigger.py:3854-3855`) and
  **Codex app-server** (`codex_appserver.py:1129`): propagate to `_execute_rpc_run`'s
  `except (Exception, asyncio.CancelledError)` (`agent_trigger.py:4093`); the run fails.
- **`exec` (Claude, Codex `exec`)**: `_flush_line` → `_execute_run`'s except (`:3164`); the run
  fails.

The implementation must not wrap the call in a broad `except` that records the unscrubbed event
instead. A raise leaves `tail` as it was, because it is assigned last (D1 step 4).

**What the HTTP routes return (R3).** No route calls `scrub_stream`. The trigger route
(`POST .../agent/trigger`) returns once the run's task is created (`agent_trigger.py:1620-1670`);
`pre_turn_events`, the RPC callbacks and the `exec` loop all run inside that task, so a raise there
changes the run's outcome as above, never the route's response. `POST /agents/{name}/output`
(`api/v1/agents.py:3178`) is not changed (Non-goals).

## Open questions for the operator

All three were **DECIDED by the operator on 2026-10-04** (`spec-queue/APPROVALS.md`, "APPROVED,
fold the log in"): (1) no hold, `m = min(8, len // 2)` with no floor; (2) join across tool and
other cards; (3) D6 folded in, with its guard. The questions are kept below as they were asked.

1. **DECIDED 2026-10-04: no hold; `m = min(8, len // 2)`, no floor.** **No hold (D1, recommended), or hold; and *m*?** D1 can show up to 7 characters of a key at a
   boundary (less than half of a short one), and never delays anything. Holding shows no
   fragment, but can hide a thought and the tool cards after it until the next text closes. For
   very short registered values (a proxy's `test`), D1's dangling rule also garbles event ends
   (D4); a floor of 4 avoids that at the cost of showing up to 3 characters of such a value. R2
   recommends `m` as written, because a short value is already garbled everywhere by today's pass.
   **R3 concurs: no hold, `m` as written, no floor.** R3 measured the bound independently (D1:
   worst case exactly `m - 1`, always a prefix) and found that holding would also have to hold a
   thought across `_after_open_blocks` cards and permission waits, which D3 already rejects. The
   floor's only gain is fewer `<redacted>` marks at event ends for a 4- to 7-character key, which is
   already garbled inside every event; showing 3 of its 4-7 characters is the worse trade.
2. **DECIDED 2026-10-04: yes, join across tool and other cards.** **Joining across tool cards (D2)**: recommended yes. It costs nothing under D1. **R3 concurs,
   and adds that it is no longer optional for the raw-event cards:** since `d08c2f5`, an error,
   compaction or subagent card closes the open block, so a value the model writes across a
   `session.error` is split by the Hub itself, not by the model; a join that stopped at cards would
   leave that split, which the mapper creates, unhandled.
3. **DECIDED 2026-10-04: fold it in (D6, with the guard).** **The `session.error` log line**: R2 recommends folding it in (D6, tasks 1.7 and 2.4); the
   alternative is filing it as its own finding. **R3 concurs: fold it in**, with D6's guard so a
   raise cannot drop the error card. It is one call on the same registry, the payload is exactly
   the provider error that quotes a key, and the log is what an operator pastes into a report.
The pre-approval review (round log) left questions 1-3 and their recommendations unchanged; the
operator then decided all three as recommended (above).

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
- **R3 (2026-10-04, subagent of the interactive session):** a second independent re-derivation at
  `13f7421` (`d08c2f5`'s `_after_open_blocks` committed). Re-grepped `run_secrets.` (unchanged:
  the five sites, one `register`, one `forget`), every `record_agent_output(` and
  `text_event(`/`thinking_event(` caller in `hub/hub`, both executor sites and every Copilot
  emission path; re-implemented D1 from the text alone (`scratchpad/f488r3/proto.py`) and ran it
  over the committed mapper; measured the bound by random splits (`bound.py`, `bound_pad.py`); ran
  the two recorded Copilot fixtures through the mapper (`fixtures_ws.py`). The design survives;
  one defect in D1 itself. Corrections:
  1. **D1 could not fire on a Copilot thought that ends or begins with whitespace.**
     `_flush_thought` does not strip (`copilot_acp.py:1157-1160`); every other text kind is
     stripped. With a newline at the boundary, `joined` holds `plainproxy\n\nkey123`: neither the
     completion nor the dangling start matches, and the whole key stays visible. Measured: D1 as
     R2 left it showed up to 16/16 and 29/29 characters in about 4% of random padded splits.
     Fixed: D1 steps 1, 2 and 4 skip whitespace at an event boundary (kept as written in the
     output); with it the worst case is `m - 1`, always a prefix. Not seen in the two recorded
     fixtures (4 rows), but nothing prevents it. New D1 rows, spec scenario, tests 1.1/1.2, a
     test-guide mutation and a drive case.
  2. **Task 1.5 could not fail on the placement it guards.** Raising the lock at session creation,
     or from a wrapper before the real `record_agent_output` runs (the F359 tests' pattern), never
     runs the in-function code on the failed attempt, so a stream scrub wrongly placed inside
     `record_agent_output` would pass. Now the lock is raised at the real function's `commit`.
     The prototype confirms the wrong placement then stores the retried row as `key123 now.`.
  3. Task 1.2's fake must return a **completed** outcome: a failed one is retried as new runs
     (the existing test's own comment, `test_copilot_byok_env.py:969`). Its "two consecutive
     rows" assertion missed the tool-card case (the text rows are not consecutive); it now joins
     all `text`/`thinking` rows by `sequence`.
  4. D6's raise path: the log call sits before `mapper.on_raw_event` (`:2135`), so a raise there
     would be swallowed at `:1679` with the error card, the echo registration and `root_error`,
     and the turn could end `completed`. D6, task 2.4 and test 1.7 now log without the payload on
     a raise and go on; never the unscrubbed payload.
  5. Task 2.2: the scrubbed event is bound to the write's lambda as a default argument at both
     sites, so a retry reuses it and nothing scrubs twice (`_on_event` reads `event` from its
     closure today).
  6. Added what the routes return: no HTTP route calls `scrub_stream`; the trigger route returns
     once the task exists, so a raise changes the run's outcome, never a response. Added that a
     raise leaves `tail` unchanged (assigned last), and that a notification-path drop loses the
     already-flushed block for good (still fail-closed).
  7. Re-derived every `copilot_acp.py` citation at `13f7421` (`finish()` call `:2657` → `:2664`;
     `fail_turn` flush `:2106` → `:2113`; `emit` `:2081-2083` → `:2088-2090`; reader
     `:1615-1635` → `_read_loop` `:1622-1648`; notification catch `:1670-1673` → `:1676-1680`;
     server request inline `:1676-1687` → `:1682-1693`; unverified diagnostic `:2236` → `:2243`,
     caught `:2266` → `:2273`; log line `:2117-2123` → `:2124-2130`; `run_turn`'s `env` `:1956` →
     `:1963`). Every other file's numbers checked unchanged (`git diff --stat 4c054be 13f7421 --
     hub/hub` touches only `copilot_acp.py`).
  8. Concurrency and lifetime re-checked and hold: `_on_event` takes `sequence` synchronously
     (`agent_trigger.py:3764-3765`); `forget` runs from the done callback (`:1670`) after every
     in-task write, including both closing status rows; a late call after `forget` creates no
     state. One-shots register nothing and record no run events (Context).
  9. Residuals named in Non-goals: Codex app-server joins a reasoning item's parts with a space
     inside one event (`codex_appserver.py:428`); the 200-character non-JSON stdout quotes
     (`copilot_acp.py:1639`, `codex_appserver.py:800`) are not scrubbed.
  10. Spec wording: "half the value's length" now says "rounded down", matching `len(v) // 2`.
  Recommendations on the open questions: (1) no hold, `m` as written, no floor; (2) join across
  cards, now required for the raw-event cards the mapper itself creates; (3) fold the log line in,
  with the guard.
- **Pre-approval review (Opus), 2026-10-04:** an adversarial review of the change and D1-D6 with its
  own measurement script (`scratchpad/f488rev/adv.py`, over R3's `proto.py`); applied by a
  subagent at `9e9bb83` (`git diff --stat 13f7421 9e9bb83 -- hub/hub` is empty, so every line
  number above stands). Each finding was re-measured before it was written down
  (`scratchpad/f488rev/subm.py`, `order.py`). Changes:
  1. **Test 1.2 could pass with a broken join** (should-fix, confirmed). At every split of *m* or
     more, the dangling-start rule alone redacts the first half, and with the tail dropped the rows
     become `I will use <redacted>` / `key123 now.`, whose concatenation no longer spells the key.
     1.2 now asserts every row's exact `kind` and `content`, and runs each boundary case (tool,
     error, compaction, subagent, whitespace) also at 7|9 (`plainpr` + `oxykey123`), plus a three-way
     case at 3|4|9; expected rows listed in the task. The test guide's "drop the tail → every row of
     1.2 fails" was not quite true even then: the one-event message→finish row cannot fail on it.
     Corrected to "every multi-event row".
  2. **`register` does not strip** (should-fix, confirmed at `run_secrets.py:27`). New D7: keep the
     stripped value and the raw one, drop an empty one. Task 2.1, test 1.1's strip row, a test-guide
     mutation, a spec scenario.
  3. **A value containing whitespace is not joined at that whitespace** (should-fix, confirmed:
     `plain proxykey123` split at its space is stored unredacted). Stated in D1, the design's new
     Non-goals list, the proposal's Non-goals and the spec requirement.
  4. **Test 1.8's mutation was vacuous** (should-fix, confirmed, and the suggested replacement
     corrected). "Move the call after the first `await`" puts it after the write, which every test
     catches, not 1.8 specifically. The reviewer's alternative, `await asyncio.sleep(0)` before the
     scrub, is not detectable by any test: asyncio resumes ready tasks FIFO, so the scrubs still run
     in `sequence` order (`order.py`: sync and `sleep(0)` keep order). The usable mutation is the
     scrub moved into the write closure, which a test reverses by holding the first call's
     `_record_observation` before it invokes the closure (`order.py`: reversed). 1.8 rewritten that
     way, at the 7|9 split so only the tail can redact.
  5. **Notes recorded** (confirmed): over-redaction by a key's public prefix (`sk-proj-`) and by a
     self-overlapping value, cosmetic and toward hiding (D4); the Codex app-server reasoning-part
     join (`codex_appserver.py:426-428`) stays a non-goal; the tail's lifetime across runs and a
     restart (D1); content written through MCP tools is not covered by `run_secrets` at all
     (Non-goals; to be filed as its own finding by the coordinator).
  Open questions 1-3 unchanged and still the operator's: recommended no hold, `m = min(8, len // 2)`
  with no floor; join across cards; fold the log line in with D6's guard.

- **Drive, task 3.4 (2026-10-04, at `fee17dc`).** Source Hub on port 8031 with a fresh database
  (`testbed/drive1004-f488/f488.db`), the real Copilot CLI on an Anthropic provider runner whose
  base URL is a local fake (`testbed/drive1004-f488/fake_provider.py`), key
  `plainsplitkey20261004x` split 10|12 (`plainsplit` | `key20261004x`), each block streamed as two
  deltas. Stored `agent_outputs` rows, by `sequence`:

  | Agent / run | seq | kind | content |
  |---|---|---|---|
  | s1 thought→text, `run-ba84a58e3805` | 1 | thinking | `I will use <redacted>` |
  | | 2 | text | `<redacted> now.` |
  | | 3 | status | `Run completed (exit 0).` |
  | s2 text→tool→text, `run-d58b4a5acf3c` | 1 | text | `Key: <redacted>` |
  | | 2 | tool_use | `Print hello` |
  | | 3 | tool_result | `shell completed` |
  | | 4 | text | `<redacted> done` |
  | | 5 | status | `Run completed (exit 0).` |
  | s3 thought ending `\n\n`→text, `run-8f9cfac967cd` | 1 | thinking | `I will use <redacted>\n\n` |
  | | 2 | text | `<redacted> now.` |
  | | 3 | status | `Run completed (exit 0).` |

  The full key, `plainsplit` alone and `key20261004x` alone each appear 0 times in `agent_outputs`,
  `event_logs`, `runs.error`, `permission_requests`, the project SSE stream (11 `agent_output`
  frames, identical to the rows), the three `GET .../agent/<agent>/chat` responses and the Hub log.
  s3's thinking row keeps its blank line as written, as D1 step 4 requires.
