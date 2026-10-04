# Design — a secret split across two events is still scrubbed

Line numbers are at `HEAD` `10df5fc`. While R1 ran, the working tree held uncommitted slice 5
group A edits to `copilot_acp.py`, `runner_events.py`, `output_recording.py` and
`checkpoint_trigger.py` that move these lines. They do not change the flush structure. One
addition is noted in Context. `agent_trigger.py` and `run_secrets.py` were unmodified. Each claim
below is tagged **VERIFIED-CODE** (read at the cited line) or **INFERRED** (not read, or read only
in part; R2 must check).

## Context

### Where the exact-value scrub runs, and whether its input can be split

| # | Call site | What it scrubs | Can one value arrive in two calls? |
|---|---|---|---|
| 1 | `output_recording.py:41-42`, `record_agent_output` | each event's `content` and `payload`, before the row and before the SSE broadcast (`:111-124`, the same variables) | **Yes, for `text`/`thinking`** (below). This is F488. |
| 2 | `agent_trigger.py:2216`, `_broadcast_run_lifecycle` | a lifecycle payload (`error`, `stderr_tail`, …), one dict, before `persist_event` and broadcast | No. Each field is one string from one source. |
| 3 | `agent_trigger.py:2350`, `:2669`, `:3877`, `:3959` | `Run.error`, one string | No. |
| 4 | `agent_trigger.py:3277`, `:3288-3291`, `_await_operator_permission` | the card's `tool_name`, `tool_input`, `workspace_verdict` | No. One request. |
| 5 | `agent_trigger.py:3827`, `:3834-3846`, `_on_refusal` | the `permission_denied` event's data and its broadcast's `tool_name` | No. |

All VERIFIED-CODE. `register` has one caller, `agent_trigger.py:1616`, and it registers only
`env.get("COPILOT_PROVIDER_API_KEY")`; `forget` runs from the task's done callback (`:1670`).
VERIFIED-CODE.

**Which recorders feed site 1, and how they split model text:**

- **Copilot over ACP** (`copilot_acp.py`, `CopilotEventMapper`). Chunks of one kind are joined into
  one block. A block is emitted when the stream switches: a message chunk flushes the open thought
  (`:969-972`), a thought chunk flushes the open message (`:973-976`), and `tool_call`,
  `tool_call_update` and `plan` flush both (`:981-986`, `flush()` at `:1083-1085`).
  `finish()` flushes at prompt completion (`:1087-1094`, called at `:2466`), and `fail_turn`
  flushes before its own event (`:1915`). VERIFIED-CODE. Inside one block nothing is split: chunks
  are joined with `""` (`:1097`, `:1102`). VERIFIED-CODE.
- **Claude** (`runner_parsing.py:282-287`): each `thinking` and `text` content block of an
  assistant message is one event, whole. **Codex `exec`** (`runner_parsing.py:482-489`) and
  **Codex app-server** (`codex_appserver.py:415-429`, emitted at `:1123-1129`): each completed
  `agent_message`/`reasoning` item is one event; app-server skips `item/agentMessage/delta`
  (`:1214-1223`). VERIFIED-CODE. So the split is a property of the model's own block boundaries,
  present on every runner. Only Copilot registers a value, so only Copilot shows it.
  INFERRED: whether a Claude or Codex run can register a value at all. `env` falls back to
  `dict(os.environ)` (`agent_trigger.py:1472`). If the Hub's shell exports
  `COPILOT_PROVIDER_API_KEY` and the Claude or Codex `guard_env` does not strip it, a Claude or
  Codex run registers it too. R2: read `runner_adapters/claude.py:138` and `codex.py:264`.
- **Tool output.** Copilot records only the terminal `tool_call_update`
  (`copilot_acp.py:1039-1047`; partial updates are dropped), so one output is one event. Claude's
  `tool_result` blocks and Codex's completed items are whole too. VERIFIED-CODE. They can be **cut**
  but not split: `tool_result_event` truncates at 8 KiB before the scrub sees it
  (`runner_events.py:241-242`). A cut leaves a prefix in that row, and the rest is recorded
  nowhere. `text_event` and `thinking_event` cut the same way at 64 KiB (`:171-184`). Non-goal.
- **Diagnostics, errors, status rows, notices.** One string each, built from one source.
  `_classify` can split one message block around a Copilot notice (`copilot_acp.py:1106-1122`).
  A value would have to contain the notice text to span that split. VERIFIED-CODE.
- **Self-report**, `POST /agents/{name}/output` (`api/v1/agents.py:3186`), with an optional
  `run_id`. Scrubbed per post. VERIFIED-CODE. Not joined (Non-goals).
- **SSE.** The broadcast in `record_agent_output` sends the already-scrubbed `content` and
  `payload` (`output_recording.py:111-124`). Lifecycle and card broadcasts send their scrubbed
  dicts. VERIFIED-CODE. INFERRED: no other path broadcasts raw model text. R2 should grep
  `sse_manager.broadcast` for anything carrying a `RunEvent`'s content outside
  `record_agent_output`.
- **Readers of stored text** (timeline route, checkpoint transcript, title excerpt) read the
  stored rows. INFERRED from slice 5 D7's statement. If the rows are fixed, the readers are fixed.
- **Not a recorded run event, but a leak.** `copilot_acp.py:1922-1934` logs every armed
  `session.error` payload whole to the Hub log. A provider error that quotes the key puts it there.
  VERIFIED-CODE that it is unscrubbed. Out of scope here. R2 should decide whether to file it.
- Working-tree note: the uncommitted group A edit makes a message chunk equal to a pending
  `Error: <message>` echo return `[]` **before** `_flush_thought()`. Such a chunk is not a
  boundary. Every other path is unchanged.

### The order the mapper emits at each boundary

VERIFIED-CODE (`copilot_acp.py:965-1104`), and run through the working-tree mapper in a scratch
script (output under D1):

| Boundary | What the call that crosses it returns | When the later block appears |
|---|---|---|
| thought → message | `[thinking(T)]`, on the first message chunk | at the next switch or `finish()` |
| message → thought | `[text(M)]`, on the first thought chunk | at the next switch or `finish()` |
| message → tool_call | `[text(M), tool_use]` (+ `tool_result` if the update is already terminal) | — |
| thought → tool_call | `[thinking(T), tool_use]` (+ `tool_result`) | — |
| message → finish | `[text(M)]` + unechoed notices | — |
| fail_turn | `flush()` + `[event]` | — |

Invariant: at most one of `_thought`/`_message` is non-empty, because a chunk of each kind flushes
the other. So `flush()` never emits both. `text` content is `.strip()`ed (`:1122`). `thinking`
content is not stripped (`:1099` tests `.strip()` but passes `text`). VERIFIED-CODE. The recorded
strings, which are also what the reader sees, are what the scrub must join.

Every event of one run is recorded in emission order, one at a time: `emit` awaits each event in
turn (`copilot_acp.py:1890-1892`), `_on_event` awaits its write (`agent_trigger.py:3763-3779`),
and `_execute_run`'s loop awaits each one (`:2836-2852`). VERIFIED-CODE. `pre_turn_events` and the
surface renderer reach the same `_on_event` (`:3854`, `:3526-3531`). VERIFIED-CODE.

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

Other kinds pass through unchanged and leave `tail` as it is. So the tail spans tool cards (D2).
A run with nothing registered returns the event unchanged and creates no state.

Prototype (scratch only, against the working-tree `CopilotEventMapper`, value `plainproxykey123`,
`m = 8`). Each row shows the recorded content today, then with D1:

| Case | Rows (kind: today → D1) |
|---|---|
| thought → message | thinking: `I will use plainproxy` → `I will use <redacted>`; text: `key123 now.` → `<redacted> now.` |
| message → tool_call → message | text: `Key: plainproxy` → `Key: <redacted>`; tool_use `ls`; text: `key123 done` → `<redacted> done` |
| message → thought, split at 5 | text: `plain` → `plain`; thinking: `proxykey123 hmm` → `<redacted> hmm` |
| message → finish, dangling | text: `the key starts plainproxyk` → `the key starts <redacted>` |
| three-way | thinking `x plain` → unchanged; text `proxy` → `<redacted>`; thinking `key123 y` → `<redacted> y` |
| false positive | thinking: `Let me explai` → unchanged (`plai` is 4 characters, below `m`); text: `n this.` → unchanged |

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
  `RpcTurnRequest`). Claude and Codex have the same block boundaries.
- **Scrub inside `record_agent_output` (rejected).** It is the one funnel, but
  `_record_observation` re-invokes it on `database is locked` (`agent_trigger.py:2257-2275`,
  VERIFIED-CODE). A stateful scrub there would add the same text to `tail` twice and could match a
  value across an event and its own retry. Task 1.5 pins this.
- **Scrub at read time in the timeline route (rejected).** The SSE broadcast has already gone out,
  and the stored rows still hold the halves.

### D4 — The threshold *m*

`m(v) = max(1, min(8, len(v) // 2))`. A dangling start shorter than `m` is shown. That is at most
7 characters, and less than half of a short value. For `sk-ant-api03-…` keys those 7 characters are
`sk-ant-`, which is public. A start of `m` or more characters is redacted whatever follows. The
false positive is prose that ends with the first 8 characters of the key, or the first half of a
short one. For a provider key that happens only when the model is quoting the key. The operator
can choose a different *m* (open question 1).

### D5 — F278's `_redaction_for` and this change do not interact

`redact_secrets` (with F278's `_redaction_for`, `runner_events.py:78-96`) is called by
`tool_use_event` (`:212`), `tool_result_event` (`:241`) and `diagnostic_event` (`:283`, `:294`),
and by `scheduler.py`'s loop summaries. It is never called by `text_event` or `thinking_event`
(`:171-184`). VERIFIED-CODE at `HEAD`. The working tree adds `error_event`'s message. D1 touches
only `text` and `thinking`, so the two passes never act on the same string. Both write the same
`<redacted>` marker. Where both act on a tool string, the pattern pass runs first, in the builder,
and the exact pass runs at record. The pattern pass only ever removes characters, so it cannot
create a whole value that the exact pass would then miss. At most, it can turn a value the exact
pass would have caught whole into a fragment it does not catch. That happens only for a value
partly matched by a pattern rule, such as `abc.` followed by 32 base64 characters, where `abc.`
survives. INFERRED to be harmless: a fragment, the case F278's D4 already noted. R2 should check
it against a real key shape.

## What each caller returns when this raises

`scrub_stream` does `str` concatenation, `find`, `endswith` and slicing on a `RunEvent` whose
`content` is a `str` (`runner_events.py:147-168`), and copies the event with a new payload dict. It
cannot raise on that input. If it did, it would raise inside `_on_event` or `_execute_run`'s loop,
outside `_record_observation`. The run would then fail through the executor's own `except`, as an
unexpected recording error does today. The implementation must not wrap it in a broad `except`
that records the unscrubbed event instead.

## Open questions for the operator

1. **No hold (D1, recommended), or hold?** D1 can show up to 7 characters of a key at a boundary
   (less than half of a short one), and never delays anything. Holding shows no fragment, but can
   hide a thought and the tool cards after it until the next text closes. A different *m* is the
   middle ground.
2. **Joining across tool cards (D2)**: recommended yes. It costs nothing under D1.
3. **The `session.error` log line** (`copilot_acp.py:1922-1934`): file it as its own finding, or
   fold it into this change?
4. **Ordering with slice 5.** This change adds to `agent-stream-events` and does not depend on slice
   5's `runner-registry` delta archiving first. It does depend on `run_secrets` existing, and it
   does (committed).

## Round log

- **R1 (2026-10-04, subagent of the interactive session):** explored at `10df5fc` and proposed.
  Read all five `run_secrets.scrub` call sites, the three runners' text emission, and every
  `CopilotEventMapper` flush path. Ran D1 in a scratch prototype over the real mapper. Found two
  things outside the finding: the unscrubbed `session.error` log line, and that a Claude or Codex
  run may register an ambient key (INFERRED). Neither is fixed here. For R2: everything tagged
  INFERRED, and the working tree's group A edits once they land. Checked late in R1:
  `_execute_rpc_run` is both Copilot's executor (`agent_trigger.py:3548`) and Codex app-server's
  (`:2612-2614`, `transport.kind == "rpc"`). VERIFIED-CODE.
