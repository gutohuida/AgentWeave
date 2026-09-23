# Proposal — an `@`-mention an agent wrote reads no file

**Round 1, 2026-09-23** (day window, D-2). Finding: **F409 (A)**. Source: research candidate #1 of
`spec-queue/research/2026-09-23.md`, re-measured independently in this round.
**Round 2, 2026-09-23:** re-derived against the code. It widened the scope to the Hub's two
one-shot workers (measured to expand) and moved the D6 trigger. See design.md's Round log.
**Round 3, 2026-09-23:** re-derived again. It found a second operator message that carries agent
text, the board's Start work (design D8). It also moved D7's un-escaping of worker output out of the
prompt and into code, and made the probe's path grading symmetric. See the Round log's R3 entry.
**Nothing here is implemented yet.**

## Why

When the Hub gives a Claude agent its turn, the whole prompt goes on the command line as
`claude … -p "<prompt>"` (`hub/hub/runner_commands.py:283`). Before the model runs, the `claude` CLI
reads that text for `@path` tokens. It reads each named file and attaches it to the turn. **No tool
call is made.** So `--disallowedTools`, the default "Workspace only" posture (`manual` plus the
Hub's `--permission-prompt-tool`, `runner_commands.py:74`, `:252-258`) and the per-tool-call boundary
in `agent-run-sandboxing` never see the read.

The prompt is mostly text the operator did not write. `format_turn_prompt`
(`hub/hub/inbound_queue.py:101-130`) puts every queued entry's `content` into the turn verbatim:

- another agent's `send_message`;
- a scheduled job or loop firing, whose briefing includes task titles, descriptions, acceptance
  criteria and a prior checkpoint, and whose standing prompt an agent can author;
- a checkpoint successor's delivery;
- a delegation's task text.

An agent can therefore make another agent's turn read any file the Hub's user can read, and the
Hub records nothing.

The agent's turn is not the only `claude -p` the Hub runs **(R2)**. The **checkpoint worker**
(`worker.py:139`) gets the conversation transcript, the agent's notes and the previous
checkpoint. The **conversation titler** (`conversation_titles.py:71`) gets the opening exchange.
Neither worker has any permission posture. Measured in R2 with the Hub's own builders: both
expand an agent's `@<outside path>`, and the checkpoint worker's reply carried the file's
contents. Those contents land in a stored checkpoint, which the operator reads and the successor
agent is given. An agent can also do this to its own next turn, through an `ask_user` question
that is echoed back with the answer.

**Measured in this round**, on `claude` 2.1.280, with the probe now at
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

The upstream fix does not fit AgentWeave. On 2026-09-20, `claude-agent-sdk-python` #1269 added a
per-message `client_composed` opt-out on the stream-json input frame. **Measured in this round:**
it does stop the read. It also drops the turn's `deferred_tools_delta` and `mcp_instructions_delta`
attachments. A `client_composed` turn with the Hub's own `--mcp-config` could not name **any** of
the 27 `mcp__agentweave__*` tools, and it answered: *"No visible tools start with
`mcp__agentweave`"*. The same turn without the flag listed them. Delivering agent text that way
would cut every agent off from the Hub.

## What Changes

- **Every `@` in text the operator did not write becomes `\@` before it reaches a runner.** The
  replacement is unconditional and applies to every `@` in that text. The measured reason: the CLI
  expands an `@` only at the start of the text or after a whitespace character, and never after `\`
  (or after any of the 22 other preceding characters measured). Its whitespace set is JavaScript's, not
  Python's. **U+FEFF expands a mention and is not whitespace to Python's `\s`**, so a rule keyed to
  "an `@` after whitespace" would already leak. An `@` with `\` in front of it never expands. That
  holds whatever precedes the backslash (`\\@` is measured), and the backslash reaches the model
  unchanged (read back from the transcript).
- **`format_turn_prompt` neutralises every entry whose `origin_type` is not `operator`.** That covers
  `agent`, `job`, `checkpoint` and `divergence`, and any origin added later. Operator entries stay
  byte-identical, so the composer's `@path` picker (`hub/ui/src/lib/composerTrigger.ts:69-99`) keeps
  working.
- **`_batch_delivery_text` (`hub/hub/api/v1/questions.py:215-241`) neutralises the agent's own
  question text** inside the operator-origin entry that delivers an answer. The operator's answer is
  left as it is.
- **The turn says so, once.** When the turn's blocks contain `\@`, the preamble line gains one
  sentence. It says that an `@` in text the operator did not write is shown as `\@`, and why (design
  D6). The question echo is covered. A turn whose blocks contain no `\@` is byte-identical to today.
- **The one-shot workers neutralise their whole prompt (R2, design D7).** `build_worker_command`
  and `build_title_command` escape every `@` in the prompt, for both CLIs. **(R3)** What a worker
  returns is un-escaped in code by the exact inverse, `restore_file_mentions`. `worker._interpret`
  applies it to the parsed JSON, and the titler applies it to its output. So a stored checkpoint or
  title never carries `\@`, whatever the model writes. `_normalise` drops separators before an
  at-sign on both sides, so a changed file under `@scope/` is not graded missing, however the probe
  writes it. No template or prompt version changes.
- **The board's Start work escapes the task title (R3, design D8).** `useStartWorkOnTask` builds
  `Work on task <id>: <title>` in the browser, and it is queued as the operator. An agent can author
  the title, so its at-signs are escaped where the message is built, as the question echo's are.
- **What is stored does not change**, except in the two mixed-author strings (the question echo and
  Start work), which are escaped where they are built. Queue entries, messages, questions and jobs
  otherwise keep their text as written. Only the prompt handed to the runner differs, so the conversation view shows what was
  sent.
- **A regression probe**: `scripts/drive/d2_0923_at_mention_tokeniser.py` keeps its measured table
  and exits non-zero when a CLI upgrade changes any row. The live drive (tasks group 4) adds the
  end-to-end version: one agent's `send_message` to another, with a marker outside the workspace.
- **A new `agent-run-sandboxing` requirement**: text the operator did not write reaches a run without
  a file mention the harness would expand.

## Non-goals

- **The `client_composed` transport.** Measured to hide the Hub's MCP tools (see Why).
- **A narrower rule** that only escapes an `@` in mention position, or only a path that leaves the
  workspace. The first depends on copying the CLI's whitespace set exactly, and U+FEFF already
  breaks it. The second depends on resolving paths the way the CLI does (quoting, `~`, symlinks,
  Windows separators) at composition time. Both are wrong the day the CLI's tokeniser moves. See
  design D2.
- **Codex.** The prompt is composed before the runner is known, so Codex turns get `\@` too. That is
  harmless text. Whether `codex exec` or the app-server expands `@` is **unverified**, because Codex
  cannot be driven on this machine (it is not needed to close F409).
- **Recording that a neutralisation happened.** The stored entry already shows the original text,
  and an event per escaped `@` would mostly record email addresses.

## Impact

- `hub/hub/file_mentions.py` (new): `neutralise_file_mentions` and the D6 sentence.
- `hub/hub/inbound_queue.py`: `format_turn_prompt` neutralises non-operator blocks and adds the
  sentence.
- `hub/hub/worker.py` (`build_worker_command`, `_interpret`), `hub/hub/conversation_titles.py`
  (`build_title_command`, `generate_conversation_title`) and `hub/hub/checkpoint_generation.py`
  (`_normalise`). The templates and prompt versions do not change (R3).
- `hub/ui/src/api/tasks.ts` (`useStartWorkOnTask`), `hub/ui/src/lib/fileMentions.ts` (new), a UI
  test, and the refreshed bundle under `hub/hub/static/ui` (R3, D8).
- `hub/hub/api/v1/questions.py`: `_batch_delivery_text` escapes `row.question`.
- `hub/tests/test_inbound_queue.py`, the questions tests, `test_checkpoint_generation.py` and
  `test_title_generation.py`: new rows. Existing exact-string
  assertions whose content has no `@` do not move.
- `scripts/drive/d2_0923_at_mention_tokeniser.py` (written in R1) and
  `scripts/drive/d3_0923_worker_at_mention.py` (written in R2), both as evidence, and
  `scripts/drive/d4_0923_worker_json_escape.py` (written in R3), for how a worker answers once its
  prompt is escaped.
- `openspec/specs/agent-run-sandboxing/spec.md`: one ADDED requirement.
- **Behaviour an operator can notice:** an agent sees `\@` where a peer, a job or a task wrote `@`.
  That includes email addresses and Python decorators in a pasted snippet (design Risks). An
  operator-authored **job** prompt with a hand-typed `@path` no longer expands, because job entries
  are not operator-origin (design D3). The agent reads that file with a tool call instead, which the
  posture judges.
- **Hub restart:** the Hub part is Hub process code, not the per-run MCP server. `:8000` picks it up
  only when the operator restarts it. **The UI part (D8) is different.** It is a committed bundle, so
  it reaches `:8000` on its next browser reload, before any restart. That is harmless: until the
  Hub restarts, the agent sees an escaped title in a turn with no D6 sentence. No migration and no
  API change.
