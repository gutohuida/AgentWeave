# Proposal — an `@`-mention an agent wrote reads no file

**Round 1, 2026-09-23** (day window, D-2). Finding: **F409 (A)**. Source: research candidate #1 of
`spec-queue/research/2026-09-23.md`, re-measured independently in this round.
**Round 2, 2026-09-23:** re-derived against the code. It widened the scope to the Hub's two
one-shot workers (measured to expand) and moved the D6 trigger. See design.md's Round log.
**Round 3, 2026-09-23:** re-derived again. It found a second operator message that carries agent
text, the board's Start work (design D8). It also moved D7's un-escaping of worker output out of the
prompt and into code, and made the probe's path grading symmetric. See the Round log's R3 entry.
**Operator review, 2026-09-24:** approved with the defaults for Q1 to Q3. The Opus review then found
a bypass: a clicked `ask_user` option is echoed back unescaped. The change was sent back as REVISING.
**Round 4, 2026-09-24 (revise):** re-derived every route. D4 now neutralises an answer made of chosen
options. New D9 covers the specification-turn notice's path. New D10 covers the composer's picker
offering a path an agent named, which R4 measured to expand. The requirement no longer contradicts
Q1, and three MODIFIED deltas were added. See design.md's `## Operator review, 2026-09-24` and the
Round log's R4 entry.
**Nothing here is implemented yet.**

## Why

When the Hub gives a Claude agent its turn, the whole prompt goes on the command line as
`claude … -p "<prompt>"` (`runner_commands._build_claude_command`). Before the model runs, the
`claude` CLI reads that text for `@path` tokens. It reads each named file and attaches it to the turn.
**No tool call is made.** So `--disallowedTools`, the default "Workspace only" posture (`manual` plus
the Hub's `--permission-prompt-tool`) and the per-tool-call boundary in `agent-run-sandboxing` never
see the read.

The prompt is mostly text the operator did not write. `format_turn_prompt` (`hub/hub/inbound_queue.py`)
puts every queued entry's `content` into the turn verbatim:

- another agent's `send_message`;
- a scheduled job or loop firing, whose briefing includes task titles, descriptions, acceptance
  criteria and a prior checkpoint, and whose standing prompt an agent can author;
- a checkpoint successor's delivery;
- a delegation's task text.

Some operator messages carry agent text too:
- the answer to an agent's question, which restates the question and, when the operator clicked an
  option, the option's text;
- the board's Start work, which quotes the task's title.

An agent can therefore make another agent's turn, or its own next turn, read any file the Hub's user
can read, and the Hub records nothing.

The agent's turn is not the only `claude -p` the Hub runs **(R2)**. The **checkpoint worker**
(`worker.build_worker_command`) gets the conversation transcript, the agent's notes and the previous
checkpoint. The **conversation titler** (`conversation_titles.build_title_command`) gets the opening
exchange. Neither worker has any permission posture, and the titler's `--tools ""` was measured not
to stop expansion. Measured in R2 with the Hub's own builders: both expand an agent's
`@<outside path>`, and the checkpoint worker's reply carried the file's contents into what becomes
the stored checkpoint.

**Measured in R1**, on `claude` 2.1.280, with the probe now at
`scripts/drive/d2_0923_at_mention_tokeniser.py`:

- A marker file sat outside a scratch working directory. The prompt had the Hub's exact inbound-queue
  shape:
  `[AgentWeave inbound queue — …]\n\nAgent "reviewer-1" (hop 1):\nplease look at @<abs path> …`.
  Every file tool was disallowed (`Read,Bash,Glob,Grep,Edit,Write,WebFetch,Task,NotebookEdit`).
  The turn returned the marker with **0 tool calls**. The CLI's own session transcript recorded an
  `"attachment":{"type":"file"}` for it.
- `@../secret/secret.txt` (a relative traversal), `@"<path>"` and a backslash-separated path expand
  the same way. So do an `@` at a line start, after a tab, after a no-break space, inside a fenced
  code block, and after `> `.

**Measured in R4**, the same way: a question echo whose answer is a clicked option
(`Answer: Use @<abs>`) expands, in the single, multi-select and batch forms. The specification-turn
notice's path expands. A composer mention of a workspace path an agent named, `@"x @<abs>"`, expands
the inner path.

The upstream fix does not fit AgentWeave. On 2026-09-20, `claude-agent-sdk-python` #1269 added a
per-message `client_composed` opt-out on the stream-json input frame. **Measured in R1:** it does
stop the read. It also drops the turn's `deferred_tools_delta` and `mcp_instructions_delta`
attachments. A `client_composed` turn with the Hub's own `--mcp-config` could not name **any** of
the 27 `mcp__agentweave__*` tools. Delivering agent text that way would cut every agent off from the
Hub.

## What Changes

- **Every `@` in text the operator did not write becomes `\@` before it reaches a runner.** The
  replacement is unconditional and applies to every `@` in that text. The measured reason: the CLI
  expands an `@` only at the start of the text or after a whitespace character, and never after `\`.
  Its whitespace set is JavaScript's, not Python's, and **U+FEFF expands a mention while not being
  whitespace to Python's `\s`**. So a rule keyed to "an `@` after whitespace" would already leak.
- **`format_turn_prompt` neutralises every entry whose `origin_type` is not `operator`.** That covers
  `agent`, `job`, `checkpoint`, `divergence` and any origin added later (B5's `evidence` included),
  because the test is `origin_type != "operator"` and is not made per origin. Operator entries stay
  byte-identical, so the composer's `@path` picker keeps working. A job's firing is neutralised as a
  whole, even when the operator wrote its message (Q1, accepted).
- **The question echo neutralises the agent's text in both halves (R4).** `_batch_delivery_text`
  neutralises the question. It also neutralises the answer **whenever the operator chose offered
  options** (`answer_labels` non-empty), because the option text is the agent's. An answer the
  operator typed is left as it is. An answer that carries both is neutralised whole.
- **The turn says so, once.** When the turn's blocks contain `\@`, the preamble line gains one
  sentence saying that an `@` in text the operator did not write is shown as `\@`, and why (design
  D6). A turn whose blocks contain no `\@` is byte-identical to today.
- **The one-shot workers neutralise their whole prompt (R2, design D7).** `build_worker_command` and
  `build_title_command` escape every `@` in the prompt argument, for both CLIs. What a worker returns
  is un-escaped in code by the exact inverse, `restore_file_mentions`. `worker._interpret` applies it
  to the parsed JSON, and the titler applies it to its output. `_normalise` drops separators before an
  at-sign on both sides, so a changed file under `@scope/` is not graded missing.
- **The board's Start work escapes the task title (R3, design D8).** Kept with the title (Q3,
  accepted).
- **The specification-turn notice escapes the open document's path (R4, design D9)** and carries the
  D6 sentence when it did. An adopted document's on-disk path can hold an at-sign.
- **The composer does not offer a mention that would carry a second one (R4, design D10).** The
  `@`/`$` pickers and the files tab's "Insert into composer" no longer offer a value with an at-sign
  anywhere but at its start or directly after `/`. `packages/@scope/x` stays offered.
- **What is stored does not change**, except in the two mixed-author strings (the question echo and
  Start work), which are escaped where they are built.
- **A regression probe**: `scripts/drive/d2_0923_at_mention_tokeniser.py` keeps its measured table,
  gains R4's rows, and exits non-zero when a CLI upgrade changes any row.
- **Specs:** one ADDED `agent-run-sandboxing` requirement. MODIFIED: `agent-flows` (a review
  firing's loop message is delivered with its words unchanged and its at-signs neutralised),
  `agent-composer` (*Trigger result sources*) and `conversation-side-panel` (*A file can be inserted
  into the composer…*).

## Non-goals

- **The `client_composed` transport.** Measured to hide the Hub's MCP tools (see Why).
- **A narrower rule** that only escapes an `@` in mention position, or only a path that leaves the
  workspace. See design D2.
- **Codex.** The prompt is composed before the runner is known, so Codex turns get `\@` too. That is
  harmless text. Whether `codex exec` or the app-server expands `@` is **unverified**.
- **Recording that a neutralisation happened.** The stored entry already shows the original text.
- **Refusing at-signs in spec paths.** D9 escapes at the notice instead (design D9).

## Impact

- `hub/hub/file_mentions.py` (new): `neutralise_file_mentions`, `restore_file_mentions` and the D6
  sentence.
- `hub/hub/inbound_queue.py`: `format_turn_prompt`.
- `hub/hub/api/v1/questions.py`: `_batch_delivery_text` escapes `row.question`, and `row.answer` when
  `row.answer_labels` is non-empty.
- `hub/hub/launchability.py`: `spec_turn_notice` (D9).
- `hub/hub/worker.py` (`build_worker_command`, `_interpret`), `hub/hub/conversation_titles.py`
  (`build_title_command`, `generate_conversation_title`) and `hub/hub/checkpoint_generation.py`
  (`_normalise`). The templates and prompt versions do not change.
- **UI:** `hub/ui/src/lib/fileMentions.ts` (new: `neutraliseFileMentions`, `isSafeMentionValue`),
  `hub/ui/src/api/tasks.ts` (`useStartWorkOnTask`), `hub/ui/src/lib/composerTriggerSources.ts`
  (`resolveTriggerResults`), `hub/ui/src/components/spec/FileTab.tsx`,
  `hub/ui/src/components/agents/Composer.tsx` (the insert effect), their UI tests, and the refreshed
  bundle under `hub/hub/static/ui`.
- Tests: `hub/tests/test_inbound_queue.py`, the questions tests, `test_checkpoint_generation.py`,
  `test_title_generation.py`, the launchability tests, and the UI tests.
- `scripts/drive/d2_0923_at_mention_tokeniser.py` (gains R4's rows), and the R2 and R3 probes as
  evidence.
- `openspec/specs/`: one ADDED requirement in `agent-run-sandboxing`, and MODIFIED requirements in
  `agent-flows`, `agent-composer` and `conversation-side-panel`.
- **Behaviour an operator can notice:**
  - An agent sees `\@` where a peer, a job or a task wrote `@`, including email addresses and
    decorators.
  - An operator-authored **job** prompt's hand-typed `@path` no longer expands.
  - A clicked option containing an at-sign shows `\@` in the chat's echo.
  - The picker no longer offers a path such as `notes@home.md`.
- **Hub restart:** the Hub part is Hub process code. `:8000` picks it up only when the operator
  restarts it. **The UI part (D8, D10) is different.** It is a committed bundle, so it reaches `:8000`
  on its next browser reload, before any restart. That is harmless. Until the Hub restarts, the
  agent sees an escaped Start work title in a turn with no D6 sentence, and the picker stops offering
  a few paths. No migration and no API change.
