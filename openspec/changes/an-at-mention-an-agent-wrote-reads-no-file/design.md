# Design — an `@`-mention an agent wrote reads no file

## Operator review, 2026-09-24

The rounds R1 to R3 were approved with their defaults for Q1 to Q3 (`spec-queue/DECISIONS.md`,
`0923-changes`). An Opus adversarial review then found a bypass
(`spec-queue/tracks/reviews/2026-09-23-changes-2026-09-24.md` §1): an `ask_user` option the operator
clicks comes back to the agent in an operator-origin message, and D4 escaped only the question. The
operator sent the change back as **REVISING** (`spec-queue/APPROVALS.md`, `## 2026-09-24`).

**R4 ran on 2026-09-24** as a revise round. It re-derived every route by which text an agent wrote
or can influence reaches a `claude -p` prompt, rather than applying the review's fixes as given. The
result, in the Round log's R4 entry:
- D4 now also neutralises an answer made of chosen options.
- New **D9** neutralises the open document's path in the specification-turn notice.
- New **D10** closes a route no round had looked at: a workspace path an agent names, offered by the
  composer's own `@` picker.
- The requirement's contradiction with Q1 is fixed.
- Three MODIFIED deltas were added (`agent-flows`, `agent-composer`, `conversation-side-panel`).

Q1 to Q3 stand as answered. **Q4 (D10) is new.**

**Citations.** From R4 on, this document cites functions, not line numbers. Line numbers drifted
between R3 and the review. The Round log's R1 to R3 entries keep the line numbers they were
written with, as a record.

**How R1 to R3 measured.** Every "measured" row was one real Haiku turn, with every file tool
disallowed, against `claude` 2.1.280. The rows are consolidated in
`scripts/drive/d2_0923_at_mention_tokeniser.py`. R4's rows were run the same way, with
`--model claude-haiku-4-5-20251001`, from `testbed/scratch/f409-r4/` (since deleted).

**How expansion was detected.** The model's reply is not used. The CLI writes a session transcript
(`~/.claude/projects/<cwd-slug>/<session_id>.jsonl`), and it contains an
`"attachment":{"type":"file"` record exactly when the harness read the file. That is deterministic.
Several unexpanded variants got a reply that called the message a prompt injection, and the reply
alone could not have told "not read" apart from "read and withheld".

## Context

### Where a prompt reaches `claude -p`

There are exactly three `"-p"` sites in `hub/hub` (`grep`, re-run in R4), and none in
`src/agentweave`:
- `runner_commands._build_claude_command`, for agent turns;
- `worker.build_worker_command`, for the checkpoint worker and its probe;
- `conversation_titles.build_title_command`, for the titler.

Nothing in `hub/hub` sends stream-json input, stdin input or `client_composed`. The Codex
app-server path is given the same `prompt` string.

**Agent turns have one composer.** `turn_scheduler` is the only caller of `trigger_agent_directly`,
and it passes `message=format_turn_prompt(selected)`. `_trigger_agent_directly` then prepends the
Hub's notices (`prompt = "\n\n".join([*notices, message])`). Every later `prompt=prompt` in
`agent_trigger.py` passes that string on to the executor or the Codex app-server. None of them
composes a new one.

**Other text-carrying flags.** Runner `flags` come from the operator's runner record. Control
overrides pass `validate_overrides`. Neither carries recorded text. The canonical context reaches the
CLI through `--append-system-prompt-file`. That context holds task titles, charters and reviews,
but R2 measured that an `@<outside path>` in that file is **not** expanded. The review measured that
an outside `@import` in the working directory's `CLAUDE.md` is not loaded under `-p` either.

**The one-shot workers.** Both put recorded text on the command line with no permission posture:
- **The checkpoint worker.** `checkpoint_generation.build_generation_prompt` interpolates the
  conversation transcript (`_transcript_since`: every inbound entry's `content`, and the agent's
  own `text` outputs), the previous checkpoint's body and the agent's `submit_checkpoint_notes`
  text. `run_worker` spawns it in a fresh temp directory. The checkpoint's probe,
  `_PROBE_PROMPT.format(rendered=render_checkpoint(checkpoint))`, interpolates the body that worker
  wrote.
- **The conversation titler.** `generate_conversation_title` formats `_PROMPT` with an excerpt of
  the opening message and the agent's first reply, and spawns it with the project directory as
  `cwd`.

**Measured in R2** (`scripts/drive/d3_0923_worker_at_mention.py`, with the argv built by the Hub's
own `build_generation_prompt`, `build_worker_command` and `build_title_command`): both workers expand
an agent's `@<outside path>`. The checkpoint worker's JSON reply carried the file's contents. So the
file's contents reach the stored checkpoint body, which the operator reads and which
`checkpoint_cutover.delivery_content` hands to the successor agent.

**The review measured that `--tools ""`** (the titler's argv since F195) **still expands.** Removing
tools does not remove attachment.

### Who writes what an agent turn delivers

`format_turn_prompt` labels each entry by `origin_type`:
- `operator` becomes "Operator";
- `job` becomes "Scheduled job";
- anything else becomes `Agent "<origin_agent>"`.

It then appends `entry.content` unescaped. `origin_agent` is an agent name, which
`AGENT_NAME_RE` confines to `[a-zA-Z0-9_-]`, so the label itself cannot carry an at-sign.

**Every `new_entry` call site** (R4 re-ran the `grep`; `InboundQueueEntry` is constructed nowhere
else):

| origin_type | Function | Content, and who authored it |
|---|---|---|
| `operator` | `agent_trigger.trigger_agent` (`POST /agent/trigger`, operator credential only) | `body.message`. From the composer, it is the operator's text. From the new-conversation surface, it is the operator's opening sentence. **From the board's Start work** (`useStartWorkOnTask`), it is `` `Work on task ${taskId}: ${title}` ``, composed in the browser, and an agent can author `title` (`create_task`). See D8 |
| `operator` | `messages.create_message_for_actor`, when `by_operator` (no run bound) | the operator's chat text |
| `operator` | `questions.deliver_batch_if_complete` | `_batch_delivery_text`: **the agent's question**, plus the answer. **R4:** when the operator clicked options, the answer is `labels.join(', ')`, and **the labels are the agent's text** (D4) |
| `agent` | `messages.create_message_for_actor` | another agent's `send_message` |
| `agent` | `agents.request_agent` | the delegation's task text, from the spawning agent |
| `job` | `scheduler` job firing (`_do_fire_job`) and loop staging (`_stage_selection`) | `f"{briefing}\n{job.message}"`. The briefing (`_compose_loop_briefing`) interpolates the loop's purpose, the claimed task's title, description and acceptance criteria, and a prior checkpoint. `job.message` comes from the operator, or from an agent when `allow_agent_jobs` is on |
| `checkpoint` | `checkpoint_cutover.cut_over` | `delivery_content(checkpoint)`, built from the agent's `submit_checkpoint_notes` |
| `checkpoint` | `checkpoint_trigger.consider` | the fixed `_NOTES_REQUEST` (Hub text) |
| `divergence` | `run_divergence._queue_response` | `_response_prompt` or `_failed_review_prompt`. Both are Hub text that interpolates `task.title`, which an agent can author |

`origin_type == "operator"` is trustworthy. An agent reaches the queue only through a run credential
(`agent_auth.py`). `create_message_for_actor` marks a message as the operator's only when no run is
bound. `POST /agent/trigger` and `PATCH /questions/{id}` both depend on `get_project`, which accepts
only an operator credential. So a run cannot post an entry as the operator, and it cannot answer a
question. `new_entry` accepts a closed set of five origins. An approved change,
`evidence-is-decided-after-the-run-that-recorded-it` (B5), adds a sixth, `evidence`.

**Three operator-origin paths carry agent text** (R4's count; R3's was two):
- the question echo (D4), in both its halves;
- Start work (D8);
- **(R4)** any operator message whose `@path` the composer's picker completed to a path an agent
  named (D10).

**A pre-existing mislabel, out of scope here:** `format_turn_prompt` has no label for `checkpoint`
or `divergence`, so both fall through to `Agent "None"`. Filed as F410.

### The notices

`_trigger_agent_directly` prepends up to three notices:
- `access_path_notice` interpolates only the resolved access path, which is Hub-chosen.
- `auto_snapshot_notice` interpolates nothing.
- `spec_turn_notice` interpolates `path`, twice, when the open document is still unwritten. Once it
  is inside a backtick span, and once inside a quoted `path='…'` argument.

That `path` is the controlling operator entry's `spec_document`, and it names a Hub document row.
R2 held that an agent cannot choose such a path. **R4 found that it can** (see D9).
`validate_spec_path` allows spaces and at-signs in a segment. Adoption (`spec_adoption.adopt`) mints
a row for any on-disk file whose path passes it, and an agent with a write tool can create
`spec/a @/home/u/notes/x.html` in its workspace.

### What the operator relies on

The composer's `@` trigger inserts `formatMention('path', value)`, which is `@` plus
`quoteMentionValue(value)`. It quotes the value when it contains whitespace. The value comes from
`GET /workspace/paths`, which is `workspace_paths.list_workspace_paths`:
`git ls-files --cached --others --exclude-standard`. **That includes untracked files**, so it lists
any file an agent created in the project directory. The files tab's "Insert into composer"
(`FileTab`, through `ConversationView.insertIntoComposer`) inserts the same `formatMention`. The
`$` skill trigger uses the same listing and the same quoting. The CLI's expansion of the inserted
token is what makes the picker attach the file.

The two answer surfaces never send a mixed answer:
- `AgentOutputPanel.answerPendingQuestion` sends `labels = typed ? [] : chosen` and
  `answer = typed || labels.join(', ')`.
- `AnswerForm.handleSubmit` omits `labels` when text was written.

So from the app, `answer_labels` is non-empty exactly when the answer is the joined labels. The API
(`QuestionAnswer`) accepts both fields at once, and it does not check labels against the question's
options.

A **typed** answer comes from the conversation's Composer, so the D10 picker applies to it, or from
`AnswerForm`'s plain textarea, which has no picker. The Composer's draft is restored only from what
the operator typed (`composerDrafts`). No surface pre-fills the composer or an answer with agent
text, other than the picker and "Insert into composer" (D10).

A **blocking** answer that its asker is still waiting for goes back as the `ask_user` tool result, not
as queued input (`answer_question` skips `deliver_batch_if_complete` while `_asker_still_waiting`).
A tool result never reaches argv. Only the queued delivery is a `-p` route.

### What the tokeniser does

Measured (`E` = the file was attached):

| Text before the path | E | | Text before the path | E |
|---|---|---|---|---|
| `@<abs>` (after a space) | **E** | | `\@<abs>` | — |
| `@../secret/secret.txt` | **E** | | `\\@<abs>` | — |
| `@"<abs>"` | **E** | | `ops\@example.com and \@<abs>` | — |
| `@C:\…\secret.txt` | **E** | | `@ <abs>`, `@@<abs>` | — |
| newline, tab, U+00A0, U+3000 or U+2028, then `@` | **E** | | U+200B or U+2060, then `@` | — |
| **U+FEFF**, then `@` | **E** | | `＠<abs>` (U+FF20) | — |
| inside a ```` ``` ```` fence, after `> ` | **E** | | `` `@ ``, `"@`, `(@`, `x@` | — |
| `@<abs>.` (trailing dot) | **E** | | `:` `,` `;` `=` `[` `{` `<` `'` `\|` `*` `-` `/` `_` `1` `#` `!` then `@` | — |

A relative `@inside.txt` of a file in the working directory also expands (**E**). That is harmless,
because the agent can read it anyway, but it shows expansion is not limited to absolute paths.

**R4's rows**, the same method, in the shapes the Hub actually composes:

| R4 row | Prompt shape | E |
|---|---|---|
| `label_answer` | `Operator (hop 0):\nQuestion: Which key should I use?\n\nAnswer: Use @<abs>` | **E** |
| `label_answer_escaped` | the same, `Answer: Use \@<abs>` | — |
| `multi_label_answer` | `Answer: Keep it, Use @<abs>` (a multi-select join) | **E** |
| `batch_label_answer` | the batch form, `1. Which?\n   Answer: Use @<abs>` | **E** |
| `picker_quoted_nested` | `please look at @"x @<abs>" now` (a picked path with a space) | **E** |
| `picker_unquoted_bom` | `please look at @x<U+FEFF>@<abs> now` (no `\s`, so not quoted) | **E** |
| `picker_quoted_slash_at` | `please look at @"x y/@<abs>" now` | — |
| `spec_notice_path` | `` This document (`spec/a @<abs>`) … pass `path='spec/a @<abs>'` `` | **E** |
| `spec_notice_path_escaped` | the same with `\@` | — |

**`client_composed`**, measured with the Hub's own `--mcp-config` (the canonical `mcp_server.py`,
`HUB_URL` pointed at a dead port, no tool called):

| Frame | file attached | `mcp__agentweave__*` in the deferred-tools listing | Model could name the Hub's tools |
|---|---|---|---|
| plain stream-json user frame | yes | 27 tools (81 name hits) | yes, it listed them |
| `"client_composed": true` | **no** | **0** | **no**: *"No visible tools start with `mcp__agentweave`"* |

The attachments that remained under `client_composed` were `instructions`, `session_context`, `date`
and `prompt_snapshot`. The ones dropped were `environment`, `model`, `deferred_tools_delta`,
`deferred_tools_record`, `mcp_instructions_delta`, `skill_listing` and `total_tokens_reminder`.

## Decisions

### D1 — Neutralise at composition, by origin; do not change the transport

Put the fix in `format_turn_prompt`, where the origin of each block is still known. By the time
`_build_claude_command` appends `["-p", prompt]`, the prompt is one flat string, and nothing can tell
the operator's `@` from a peer's.

Rejected: shape (a) of the research file, stream-json input with `client_composed` on agent frames.
It works for the file read, and it blinds the agent to the Hub. The measured table above is the
reason. Another variant would send a plain frame first (the Hub preamble) and a composed frame
second. R1 did not measure it: a second frame on stdin is a second user message, and possibly a
second turn. It would also change how every Claude run is spawned in order to fix one tokeniser.

### D2 — Escape every `@`, unconditionally: `text.replace("@", "\\@")`

Three rules were considered:

1. **Mention position only** (`(?<!\S)@`). This depends on matching the CLI's whitespace set.
   Measured: U+FEFF expands a mention, and Python's `\S` counts it as non-space, so this rule leaks
   today.
2. **Only paths that leave the workspace.** This needs the CLI's path resolution copied at compose
   time: `@"…"` quoting, `~`, Windows separators, symlinks inside the workspace that point out, and
   `@server:resource` MCP mentions. Each one is a place to be wrong. Leaving in-workspace mentions
   expandable also buys nothing, because the agent can read those files with a tool.
3. **Every `@`.** This depends on one measured fact: the character before a neutralised `@` is
   always the inserted `\`, and a `\` before `@` blocks expansion whatever precedes it (`\\@` and
   `ops\@x and \@<abs>` are measured). It needs no mirror of the tokeniser.

Rule 3 is chosen. It costs readability: `a@b.com` reaches the agent as `a\@b.com`, and a decorator in
a pasted snippet as `\@pytest.fixture`. See Risks. **Q2 accepted this.**

### D3 — Every origin except `operator` is neutralised, including `job`

The rule is default-deny, and it is written as one test over the origin, not as a branch per origin:
`content if entry.origin_type == "operator" else neutralise(content)`. **(R4)** That form matters to
B5's `evidence-is-decided-after-the-run-that-recorded-it`, which adds an `evidence` origin with its
own label branch in `format_turn_prompt`. Because the neutralise test is `origin_type != "operator"`
and sits outside the label branches, the new origin is neutralised with no edit here. An
implementation that moved the call into each label branch would silently exempt it. Task 1.1's
unknown-origin row pins the form. Whichever of the two changes lands second keeps that form.
(`evidence` content is Hub text naming an evidence id and a commit, so neutralising it costs
nothing.)

`job` is neutralised as a whole, even when the operator wrote `job.message`. **Q1 accepted this.**
The reasons:
- The entry's content is the Hub briefing, with agent-authored task fields interpolated, joined to
  `job.message` in one string at both firing sites.
- Exempting operator-authored jobs would mean escaping field by field at both sites and trusting
  `created_by_run_id`.
- What is lost is small. The job editor has no `@` picker. A hand-typed `@path` in a job prompt still
  names the file, and the agent reads it with a tool call that the posture judges, which is how the
  boundary is meant to work.

**R4:** the requirement now says this. R3's requirement said "Text the operator wrote SHALL reach
the run unchanged", which Q1 makes false for a job message. The sentence is now limited to what the
operator writes to an agent directly: the composer, the chat, and a typed answer. A scheduled job's
firing is named as neutralised as a whole, and a scenario pins it.

### D4 — The question echo neutralises the question and any answer made of chosen options (R4)

`_batch_delivery_text` builds `Question: {q}\n\nAnswer: {a}` for one question, and a numbered list
for several. Both forms interpolate `row.question` and `row.answer`.

- **`row.question`** is the agent's (`ask_user`). It is neutralised in both forms.
- **`row.answer`** is neutralised in both forms **whenever `row.answer_labels` is non-empty**, and
  is left alone when it is empty.

**Why the answer too (R4, the review's HIGH item).** `ask_user` requires options. The tool tells
the agent that "the label is what comes back to you". The app answers a clicked option with
`answer = labels.join(', ')`. So an option labelled `Use @/home/u/.ssh/id_rsa`, once clicked and
delivered as queued input, attaches the file on the agent's next turn. That was measured in R4, in
the exact echo shape, for a single choice, a multi-select join and the batch form (Context, R4
rows). An agent can reach a file outside the posture's view through its own text, which is what D4
exists to prevent.

**Why `answer_labels` is the signal, and why the whole answer.**
- From the app, labels are non-empty exactly when the answer *is* the joined labels (Context). No
  surface sends typed text and labels together.
- A direct API caller can send both. That caller holds the operator's key, so the text is still the
  operator's. But the Hub cannot tell which part of `answer` is the labels. The labels are not
  checked against the options, and a label may itself contain `, `.
- So the **mixed case is neutralised whole**. The cost falls only on a caller no product surface
  is: an operator who scripts an answer with both fields and an `@path` in the typed part loses its
  expansion.
- Neutralising `answer` whenever it *contains* a label was rejected. It needs substring matching on
  agent text, and it fails open the first time the join changes.

**The typed answer stays unchanged.** It is the operator's text, and in the conversation it is
written in the Composer, whose `@` picker must keep working. Could an agent get text into a typed
answer?
- The Composer draft is only ever what the operator typed.
- `AnswerForm` is a plain textarea.
- No surface pre-fills either one with agent text.
- The one channel is the picker offering an agent-named path, which D10 closes for every composer
  message, answers included.

**The hazard is limited to queued delivery.** A blocking answer that its asker is still waiting
for is returned as a tool result and never reaches argv. The neutralisation is applied where the
echo is composed, so it covers every route that delivers one: the answer, the decline that
completes a batch, and the expiry report. All three go through `deliver_batch_if_complete`.

**Consequence (R2, and wider since R4).** The echo is escaped where it is composed, because by the
time the turn is composed the two halves are one string. So the *stored* entry content carries `\@`
in the question and, when an option was chosen, in the answer. The chat view renders stored content,
so the operator sees `\@` in the echo. The `Question` row keeps `question`, `answer` and
`answer_labels` as recorded. The same trade was accepted in R2.

### D5 — Stored text is untouched

The chat renders queue entries from stored `content` (`api/v1/agent_chat.py`). Neutralising at write
time would put `\@` in the operator's view of a peer's message, and it would corrupt round-trips (a
checkpoint's notes read back by `read_checkpoint`). Only the runner prompt changes.

The two exceptions are the mixed-author strings, which are escaped where they are composed and
stored that way:
- the question echo (D4);
- the board's Start work message (D8).

### D6 — Say so once, in the queue preamble

When the composed blocks contain the two characters `\@` anywhere, `format_turn_prompt` adds one
sentence after the preamble line: *"In text the operator did not write, every at-sign is shown with
a backslash before it, so that the text cannot make your harness attach a file; the original has no
backslash."*

Without it, the agent sees an unexplained backslash. With it, the agent knows the text is quoted
content and not an escape to reproduce. The sentence is Hub text, so it is not itself neutralised.
It spells the character as "at-sign" and uses no literal `@`, so it has nothing to expand.

**The trigger is "the blocks contain `\@`" (R2).** It catches the question echo and Start work, which
are escaped before `format_turn_prompt` runs, inside `operator` entries that it passes through.
**(R4)** It also catches an echo whose answer was an option. Its only other effect: an operator who
types `\@` themselves also gets the sentence, which is still true and harmless. A turn whose blocks
contain no `\@` is byte-identical to today.

The constant lives beside `neutralise_file_mentions` in `hub/hub/file_mentions.py`, so D7 and D9 can
use it too.

### D7 — The one-shot workers neutralise their whole prompt (R2, revised in R3)

`worker.build_worker_command` and `conversation_titles.build_title_command` apply
`neutralise_file_mentions` to the entire `prompt` they are given, in both the `claude` and the
`codex` branch, before placing it in argv.

- **The whole prompt, not per interpolation.** No worker has a use for expansion. Every byte after
  the fixed template is recorded text, the operator's included, and no composer picker feeds a
  worker. The three templates (`_GENERATION_PROMPT`, `_PROBE_PROMPT`, the titler's `_PROMPT`)
  contain no at-sign, and a test pins that, so neutralising the whole string never alters Hub text.
- **At the builder.** There is one builder per spawn kind. The two checkpoint kinds share
  `build_worker_command`, and any future worker prompt gets the same treatment without having to opt
  in.
- **Only the prompt argument.** The titler already passes `--tools ""`. The review measured that
  flag, and it does not stop expansion, so D7 is still needed for the titler. B7's
  `worker-spend-counts-against-the-budget` may add flags to either builder. D7 changes only the
  prompt element, and task 1.7 asserts on that element alone, so other flags do not disturb it.
- **Codex too**, for D3's reason. Whether `codex exec` expands `@` is unverified, and `\@` is
  harmless text.
- **The module.** `neutralise_file_mentions`, `restore_file_mentions` and the D6 sentence go in a new
  `hub/hub/file_mentions.py`. They do not go in `inbound_queue.py`, so `worker.py`,
  `conversation_titles.py` and `launchability.py` do not import queue code for a string function.

**What a worker returns is un-escaped in code, not by asking the model (R3).**
- `restore_file_mentions(text)` is the exact inverse, `text.replace("\\@", "@")`. For any text `T`,
  `restore(neutralise(T)) == T`, including a `T` that already contained `\@`.
- `worker._interpret` applies it to every string in the parsed JSON payload, recursively, **before**
  `output_model.model_validate`. That is one place for both checkpoint kinds and any later worker.
  **(R4)** B7's worker changes keep both command builders and `_interpret`. Whichever of the two
  changes lands second must keep `restore_file_mentions` ahead of `model_validate` in `_interpret`.
- `generate_conversation_title` applies it to the CLI's output before `title_from_output`.
- `_GENERATION_PROMPT` is unchanged, and `CHECKPOINT_PROMPT_VERSION` stays `checkpoint/1`.

**The probe's path comparison is insensitive to the escape on both sides (R3).** After it maps `\`
to `/`, `_normalise` drops any run of separators directly before an at-sign
(`re.sub(r"/+@", "@", …)`). It is applied to both the envelope and the answers.
`packages/@scope/x`, `packages/\@scope/x`, `node_modules\@types\x` and a leading `\@scope/x` all
compare equal to the envelope's form.

### D8 — The board's Start work neutralises the task title where it composes the message (R3)

`useStartWorkOnTask` posts `` message: `Work on task ${taskId}: ${title}` `` to `POST /agent/trigger`,
which queues it as an `operator` entry. D3 passes operator entries through untouched, and `title` can
be an agent's (`create_task`). The fix is
`` `Work on task ${taskId}: ${neutraliseFileMentions(title)}` ``, with `neutraliseFileMentions` in a
new `hub/ui/src/lib/fileMentions.ts`. It carries a comment naming `hub/hub/file_mentions.py` as the
rule it mirrors. The stored message shows `\@`. D6 fires, and the `Task` row keeps its title.
**Q3 accepted this default** (keep the title, escaped).

Rejected: string surgery in the Hub on a message it did not compose.

### D9 — The specification-turn notice neutralises the open document's path (R4)

`spec_turn_notice` applies `neutralise_file_mentions` to `path` at both interpolations. When that
changed the path, it appends the D6 sentence as the notice's last line. Measured in R4: an at-sign
path in the notice's exact shape expands, and the escaped form does not.

**Why it is reachable.** R2 held that an agent cannot mint a document path with an at-sign:
- `create_spec_document` takes no path.
- `rename_spec_document` derives the path through `slugify`, which is `[a-z0-9-]`.

Both still hold. But `validate_spec_path` allows spaces and at-signs, and adoption
(`spec_adoption.adopt`) mints a row for any on-disk file that passes it. An agent with a write tool
can create `spec/a @/home/u/notes/x.html` in the workspace. Once it is adopted and opened while
unwritten, the notice names `@/home/u/notes/x.html` in mention position. The reach is narrow (the
target must be a `.html` file), and the fix is cheap.

**Why the sentence goes in the notice.** The notices are prepended in `_trigger_agent_directly`,
outside `format_turn_prompt`. D6's trigger reads only the queue blocks, so it would not see an
escaped path. The notice also tells the agent to pass the path to `submit_spec_document`. An agent
told what the backslash means passes the original path.

Rejected: refusing at-signs in `validate_spec_path`. That would change which on-disk corpora can be
adopted. It would also leave the notice relying on a validator that the next change to adoption
could loosen.

### D10 — The composer does not offer a mention that carries a second mention (R4)

The `@` picker, the `$` skill picker and the files tab's "Insert into composer" do not offer a value
that holds an at-sign anywhere other than at its start or directly after a `/`.

A new `isSafeMentionValue(value)` in `hub/ui/src/lib/fileMentions.ts` decides this. It is used:
- by `resolveTriggerResults`, for `path` and `skill` results;
- by `FileTab`, which hides its insert action;
- by `Composer`'s insert effect, which ignores a request for an unsafe path, as a second guard.

**The route.** The picker lists `git ls-files --cached --others --exclude-standard`, so it includes
any untracked file an agent created. An agent that creates `x @/home/u/.ssh/id_rsa` in the project
directory (the directories `x @`, `home`, `u`, `.ssh`, then a file) makes the picker offer that
path. `formatMention` quotes it: `@"x @/home/u/.ssh/id_rsa"`. **Measured in R4:** the inner
`@/home/…` expands. The quoting does not shield it. The unquoted form expands too, with U+FEFF in
place of the space, since U+FEFF is not `\s`. So an operator message, or a typed answer, that picks
that file attaches a file outside the workspace. The operator sees a path that looks like a
workspace file.

**Why an allow rule, and why this one.** D2's argument applies: a rule keyed to "an at-sign after
whitespace" would have to mirror the CLI's whitespace set, and U+FEFF already breaks it. The allow
rule rests on measured rows only:
- `/` then `@` does not expand (R1's table, and R4's `picker_quoted_slash_at`).
- `@@` does not expand (R1).

So `packages/@scope/x.ts` and `node_modules/@types/y` stay offered. `notes@home.md` is no longer
offered. That is a small loss: the operator can still type the path.

**Why not escape instead.** A mention exists to be expanded. Escaping the inner at-sign would also
change the name of the file the operator meant.

**Why the UI, not the listing.** The file tree uses the same `GET /workspace/paths`. Filtering there
would hide a strangely named file from the operator, which is the opposite of what they need.

This is a UI change, in the same bundle refresh as D8.

## Risks

- **An agent copies `\@` into a file.** A peer's message with a decorator or an email reaches the
  agent as `\@…`, and an agent pasting a snippet verbatim could write the backslash. D6 mitigates
  this by naming the notation once per turn. The residual risk is real and low.
- **The CLI changes its tokeniser.** Suppose a future CLI treats `\@` as an escape for a literal `@`
  and expands whatever follows. `\\@` would still be blocked, but `\@` would not. The probe's
  `escaped` and `escaped_twice` rows exist to catch this. D10 likewise rests on the `/`-before-`@`
  row. The probe needs a real Haiku turn per row, so it is not a CI test. It is a drive step to
  rerun after a CLI upgrade (task 3.2).
- **A worker reply that is not valid JSON because of the escape (R3).** `\@` is not a legal JSON
  string escape. In 9 Haiku worker turns (`scripts/drive/d4_0923_worker_json_escape.py`), every
  copied at-sign came back as the legal `\\@`. If another model does otherwise, the failure is loud
  (an `unparseable` checkpoint), not a wrong stored body.
- **The mixed answer (R4).** A scripted API answer that sends both `labels` and different `answer`
  text has its typed part neutralised too. No app surface sends it.
- **Tool results.** Text an agent reads back through a tool (`read_checkpoint`, `get_answer`,
  `list_tasks`) is a tool result, not prompt input, and never reaches argv. R4 did not measure
  whether the harness scans tool results for mentions. Every measured expansion is of `-p` text, and
  the Hub puts no tool result into a prompt.

## Open Questions

Q1 to Q3 were answered on 2026-09-24 (`DECISIONS.md` `0923-changes`) with the defaults:
- **Q1:** an operator-authored job prompt loses expansion (D3).
- **Q2:** `a\@b.com` is accepted (D2).
- **Q3:** Start work keeps an escaped title (D8).

4. **Q4 (D10, R4):** keep the composer picker fix in this change (the default), or file it as its
   own finding? **Recommended: keep it here.** It is the same F409 route, which is agent-chosen text
   reaching a `-p` prompt as a mention, and it is the one hole in D4's "a typed answer is the
   operator's". It costs one predicate in the same new UI file and the same bundle refresh.
   Splitting it would ship F409 as "fixed" with a measured bypass still open.

## Round log

- **R1, 2026-09-23:** explored and proposed. Every tokeniser and `client_composed` claim above was
  measured in this round. The research file's claim that the Hub never sends `client_composed` was
  checked: `grep` for `input-format`, `stream-json` input and `client_composed` in `hub/hub` finds
  none. The research file's recommended shape (a) was **rejected on measurement** (D1). The fallback
  shape (b) was **narrowed to "every `@`"** because the U+FEFF row broke the mention-position rule.
- **R2, 2026-09-23 (day window, D-3):** a fresh comparison against the code. I read every site
  again, starting from `grep` rather than from R1's table. Nine results:
  - **R2-1, scope: R1's "one choke point" held for agent turns only.** `grep '"-p"'` finds three
    spawn sites, not one. The checkpoint worker and the conversation titler put recorded agent text
    on `claude -p` with no posture at all. **Measured to expand**, and the checkpoint worker's reply
    carried the file's contents into what becomes the stored checkpoint
    (`scripts/drive/d3_0923_worker_at_mention.py`, twice). Added D7, a Context section, a second
    requirement paragraph with two scenarios, and tasks 1.7 to 1.10, 2.3a and 4.2a.
  - **R2-2, a regression D7 would have caused and now avoids.** The probe copies file paths
    "exactly as written", and `_normalise` turns `\` into `/`. So a changed file under `@scope/`
    would have been graded missing and invented, and the checkpoint marked `failed`. D7 undoes the
    escape in the answers first (task 1.9). The residual Windows-separator case is in Risks.
  - **R2-3, the D6 trigger moved.** R1's "`format_turn_prompt` inserted a backslash" never fires
    for the question echo. D4 escapes it upstream, inside an `operator` entry. The trigger is now
    "the blocks contain `\@`" (task 1.3a).
  - **R2-4, D5 was not quite true.** The question echo's *stored* content carries `\@`, and the
    chat renders stored content (`api/v1/agent_chat.py:205`). This is stated in D4 and accepted.
  - **R2-5, notices closed.** `access_path_notice` and `auto_snapshot_notice` interpolate nothing.
    `spec_turn_notice` interpolates only the operator entry's `spec_document`, and an agent cannot
    mint a path containing an at-sign. Details are in Risks, third bullet.
  - **R2-6, divergence is agent text.** `task.title` is interpolated. D3 already covered it, and the
    table row is corrected.
  - **R2-7, the context file is not a vector.** `--append-system-prompt-file` with an
    `@<outside path>` in mention position was measured: no attachment. It is left alone.
  - **R2-8, trust and tests.** `/agent/trigger` accepts only an operator credential. `new_entry`'s
    origin set is closed. No test in `test_inbound_queue.py`, `test_delivery_attempts.py`,
    `test_checkpoint_generation.py`, `test_title_generation.py` or the questions tests puts an
    at-sign in content these composers would change, so no existing exact-string assertion is
    expected to move. Line numbers were corrected (`scheduler.py:3157`, `:3660-3668`,
    `agent_chat.py`'s path). Out of scope: `checkpoint`/`divergence` blocks are labelled
    `Agent "None"`, filed as **F410**.
  - **R2-9, tokeniser rerun:** **41/41 rows match** (exit 0, fresh marker) on `claude` 2.1.280. D2 stands.
  - `openspec validate --strict`: valid after these edits. **R3 must not start from these notes.**
- **R3, 2026-09-23 (day window, D-4):** a second fresh comparison. The proposal and D1-D7 were read
  as the claims under test. R2's Round log was not read until R3-1 to R3-4 had been found. I started from `grep` for every `"-p"`, `exec` and stdin write in
  `hub/hub` and `src/agentweave`, then every `origin_type=` site, then every browser-composed
  `message:` template in `hub/ui/src`. Four results:
  - **R3-1, a second operator-origin entry carries agent text (new D8).** The board's Start work
    posts `` `Work on task ${taskId}: ${title}` `` as the operator (`tasks.ts:455`), and an agent
    can author the title. R1 and R2 both held that only the question echo mixes authors; neither
    looked at what the browser composes. Fixed at composition in the UI, D4's pattern. The
    alternative is Q3. New tasks 1.11, 2.3b and 4.2b. This makes the change a UI change (bundle
    refresh).
  - **R3-2, D7's "stored output carries no `\@`" was a SHALL enforced only by a prompt rule.**
    Replaced by `restore_file_mentions`, the exact inverse, applied in `worker._interpret` to the
    parsed payload and to the titler's output. The template rule and the `checkpoint/2` bump are
    dropped. **Measured** (`scripts/drive/d4_0923_worker_json_escape.py`, 9 Haiku turns, `claude`
    2.1.280): generation stored 0 `\@` both with R2's rule and without it (3/3 each), so the rule
    bought nothing observable, and it would have made the inverse lossy. Task 1.10 is rewritten.
  - **R3-3, the probe's grading made symmetric.** Measured: Haiku copied `packages/\@scope/...`
    verbatim in 2 of 3 probe runs. Today's `_normalise` fails those. R2's answers-only undo and
    R3's symmetric rule both pass them, but only the symmetric rule also passes the
    Windows-separator form. R2 had accepted that residual; it is now closed. Task 1.9 is widened.
  - **R3-4, a risk checked and not observed.** `\@` is an illegal JSON escape, and
    `extract_json_object` returns `None` on a raw `\@` inside a string (run in R3). In all 9 turns
    Haiku emitted `\@`, the legal form. Recorded in Risks as loud-if-it-happens.
  - **Held, re-derived rather than re-read:**
    - The agent-turn choke point. `trigger_agent_directly` has one caller, `turn_scheduler.py:408`.
    - Exactly three `"-p"` sites. No SDK spawn. The CLI package's subprocess calls carry no prompt
      (`docker`, a browser, PowerShell, `mcp list`).
    - D2's inverse property. `\@` in the original goes out as `\@` and restores to `\@`.
    - D3's default-deny over the five origins.
    - D6's trigger. It now also fires for D8.
  - `openspec validate --strict`: valid after these edits.
- **R4, 2026-09-24: revise after the operator's review.** The inputs were review §1 and the
  operator's REVISING row. Q1 to Q3 stand. The round did not start from the review's fixes. It
  started from `grep`, for every `"-p"`, every `new_entry` and `InboundQueueEntry(`, every
  `origin_type="operator"`, every browser `POST /agent/trigger`, every writer of the composer's
  text, and every notice in `_trigger_agent_directly`. The claim under test was that every place
  agent text reaches a prompt is covered.

  Measured with 9 real Haiku turns (`--model claude-haiku-4-5-20251001`, `claude` 2.1.280). They ran
  from `testbed/scratch/f409-r4/`, which was deleted after, along with its session transcripts. The
  rows are in Context, "R4's rows".

  Per review item:
  - **R4-1, HIGH, the clicked option. It holds, and it is wider than the review said.**
    - The code: `answerPendingQuestion` and `AnswerForm.handleSubmit` send
      `answer = labels.join(', ')` with `labels` set, and `answer_question` stores both.
      `_batch_delivery_text` interpolates `row.answer` raw in both forms.
    - Measured: the single-choice echo, a multi-select join and the **batch** form each expand. The
      review showed the single form only. The escaped echo does not expand.
    - Changed: D4 now neutralises `row.answer` whenever `answer_labels` is non-empty, in both
      forms.
    - **The mixed case** (labels plus other text) cannot come from the app, since both surfaces
      drop the labels when text is typed. The API accepts it, though, and does not check labels
      against the options. Resolved: **neutralise the whole answer**. Substring matching on agent
      text was rejected.
    - **The exemption checked.** Could an agent get text into what the operator "types"? The draft
      store, `AnswerForm` and every composer prefill were read, and none carries agent text. The
      exception is the picker, which is R4-7.
    - Only queued delivery is a `-p` route. A blocking answer returns as a tool result.
    - Tests: 1.6 is rewritten with the labels, typed and mixed rows, and 1.3a gains an
      option-answer row. Drive 4.2c is new. The requirement's scenario is split three ways.
  - **R4-2, MEDIUM, `agent-flows` "delivered unchanged". It holds.**
    - D3 neutralises every `job` entry, and a review firing's loop message is inside one. The
      requirement "A review firing's briefing is a review briefing" says "SHALL NOT be rewritten"
      and "delivered unchanged".
    - Added a MODIFIED delta. The words are not rewritten, and the one change delivery makes is the
      neutralisation, which the requirement points to. The stored message keeps the text. A
      scenario was added.
    - **The grep beyond it.** `openspec/specs/` was searched for "unchanged", "verbatim", "exactly
      as", "as written", "not be rewritten", "restat…", "inline", "Work on task", "Question:",
      option and label wording, the notice's path, and "mention". Nothing else this change makes
      false was found. `agent-loops` "the briefing includes it in full" is about the stored briefing,
      which D5 leaves whole. `agent-capability-plane`'s batch delivery says "each with its answer",
      and an escaped answer is still its answer. The run-task-binding Start work requirement names no
      wording.
    - D10 needed two MODIFIED deltas of its own: `agent-composer` *Trigger result sources* and
      `conversation-side-panel` *A file can be inserted into the composer…*. Neither is strictly
      falsified by a filter, but each now states the exception rather than implying that every
      listed file is offered.
  - **R4-3, MEDIUM, the ADDED requirement contradicts Q1. It holds.**
    - "Text the operator wrote SHALL reach the run unchanged" is false for an operator-written job
      message under Q1.
    - The sentence is now "What the operator writes to an agent directly": the composer, the chat,
      and a typed answer. A paragraph and a scenario state that a job's firing is neutralised as a
      whole.
  - **R4-4, LOW, citations. They hold.** Context and Decisions were rewritten to cite functions.
    The proposal, tasks and test guide were swept too. R1 to R3's log entries keep their line
    numbers as a record.
  - **R4-5, LOW, test 1.7 and `--tools ""`. It holds.** 1.7 now asserts on the prompt element alone,
    the one after `-p` for Claude and the last for Codex, so the titler's `--tools ""` and any flag
    B7 adds do not disturb it. D7 states the review's measurement that `--tools ""` still expands.
  - **R4-6, LOW, `spec_turn_notice` `path`. It holds, and it is now D9.**
    - R2 had closed it on the belief that an agent cannot mint an at-sign path.
      `create_spec_document` and `rename_spec_document` still cannot. But `validate_spec_path`
      allows at-signs and spaces, and `spec_adoption.adopt` mints rows for on-disk files an agent
      could have written.
    - Measured: the notice's exact shape expands, and the escaped form does not.
    - D9 neutralises `path` at both interpolations, and the notice carries the D6 sentence itself,
      because D6's trigger reads only the queue blocks. Test 1.12.
  - **R4-7, NEW: the composer's picker offers a path an agent named.** No round and no review had
    looked here.
    - `list_workspace_paths` includes untracked files, and `formatMention` quotes a value that
      contains whitespace.
    - Measured: `@"x @<abs>"` expands the inner path. So does the unquoted U+FEFF form. `@"x
      y/@<abs>"` does not.
    - This is also the one way agent text can get into a typed answer, so R4-1's exemption depended
      on closing it.
    - D10 is an allow rule built on measured rows: an at-sign only at the start or after `/`. It is
      applied in `resolveTriggerResults`, `FileTab` and the Composer's insert effect. It adds
      test 1.13 and Q4.
  - **R4-8, the default-deny form, for B5.** D3 now says that the neutralise test is
    `origin_type != "operator"`, outside the label branches, so B5's `evidence` origin is covered
    with no edit. Task 1.1's unknown-origin row pins the form. *This change cannot edit B5's
    documents. The orchestrator should add the matching sentence to
    `evidence-is-decided-after-the-run-that-recorded-it`.*
  - **R4-9, the B7 ordering.** D7 and task 2.3a state that whichever of this change and B7's worker
    change lands second keeps `restore_file_mentions` ahead of `model_validate` in `_interpret`.
  - **R4-10, the other routes, re-derived and held:**
    - three `-p` sites, and one agent-turn composer;
    - the context file (R2's measurement) and runner flags, neither of which carries recorded text;
    - `origin_agent`, which is confined by `AGENT_NAME_RE`;
    - the delegation, job, loop-briefing, divergence and checkpoint entries, all non-operator;
    - the two Hub-only notices;
    - the titler and the checkpoint worker, covered by D7;
    - the Codex app-server, which gets the same prompt;
    - B3's full-names change, which adds no at-sign.
    - The UI composes one message around agent text, Start work (D8). The other callers of
      `/agent/trigger` send what the operator typed.
  - `openspec validate an-at-mention-an-agent-wrote-reads-no-file --strict`: valid after these
    edits.
